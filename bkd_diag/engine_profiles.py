from __future__ import annotations

import re
from dataclasses import dataclass, field

from .kwp import decode_negative
from .reporting import Reporter
from .utils import ascii_runs, fmt


@dataclass(frozen=True)
class EngineProfile:
    """Small ECU-family profile for Engine 01 KWP behaviour.

    This is intentionally much smaller than a Ross-Tech label database.  It only
    captures things this project has directly observed/proven, such as which
    ReadDTC variant an ECU family accepts.  Adding support for another ECU should
    normally mean adding one EngineProfile entry and a capture note, not editing
    transport/protocol code.
    """

    key: str
    name: str
    family: str
    part_prefixes: tuple[str, ...] = field(default_factory=tuple)
    component_contains: tuple[str, ...] = field(default_factory=tuple)
    primary_dtc_read: tuple[int, ...] = (0x18, 0x02, 0xFF, 0x00)
    fallback_dtc_reads: tuple[tuple[int, ...], ...] = field(default_factory=tuple)
    notes: str = ""

    def dtc_read_sequence(self) -> list[tuple[int, ...]]:
        seen: set[tuple[int, ...]] = set()
        out: list[tuple[int, ...]] = []
        for req in (self.primary_dtc_read, *self.fallback_dtc_reads):
            req = tuple(x & 0xFF for x in req)
            if req and req not in seen:
                out.append(req)
                seen.add(req)
        return out


@dataclass
class EngineIdentity:
    responses: dict[int, bytes] = field(default_factory=dict)
    text_runs: list[str] = field(default_factory=list)
    text: str = ""
    normalized: str = ""
    part_number: str = ""
    component: str = ""


@dataclass
class EngineDtcReadResult:
    profile: EngineProfile
    identity: EngineIdentity
    response: bytes
    command: tuple[int, ...]
    attempts: list[tuple[tuple[int, ...], bytes]] = field(default_factory=list)


ENGINE_PROFILES: tuple[EngineProfile, ...] = (
    EngineProfile(
        key="bkd_edc16",
        name="BKD / EDC16",
        family="Bosch EDC16 diesel",
        part_prefixes=("03G906016",),
        component_contains=("EDC", "BKD"),
        primary_dtc_read=(0x18, 0x02, 0xFF, 0x00),
        notes="Development ECU path: 03G 906 016 AJ / BKD EDC16.",
    ),
    EngineProfile(
        key="med9_5_10",
        name="MED9.5.10 petrol",
        family="Bosch MED9 gasoline",
        part_prefixes=("03C906056",),
        component_contains=("MED9",),
        primary_dtc_read=(0x18, 0x00, 0xFF, 0x00),
        notes="Captured on a PQ35/Mk5 Golf MED9.5.10 ECU; VCDS used 18 00 FF 00 for DTC read.",
    ),
)

UNKNOWN_ENGINE_PROFILE = EngineProfile(
    key="unknown_kwp",
    name="unknown KWP Engine 01",
    family="unknown",
    primary_dtc_read=(0x18, 0x02, 0xFF, 0x00),
    fallback_dtc_reads=((0x18, 0x00, 0xFF, 0x00),),
    notes="Conservative read-only fallback: try BKD/EDC16 DTC read, then the MED9-observed variant only if unsupported.",
)

# VCDS-observed useful identity IDs for TP2.0/KWP Engine 01.
# 0x90 can carry VIN, so profile matching does not require it.
ENGINE_PROFILE_IDENT_IDS: tuple[tuple[int, float], ...] = (
    (0x9B, 10.0),  # software/component text on BKD and MED9 captures
    (0x91, 6.0),   # HW/supplier or part-like identity
    (0x86, 6.0),   # serial/component identity seen on MED9 capture
)

_PART_RE = re.compile(r"(03[A-Z]906[0-9]{3}[A-Z]{0,3})")


def _normalise(text: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", text.upper())


def _pretty_part(part: str) -> str:
    part = _normalise(part)
    if len(part) >= 9:
        return " ".join(filter(None, [part[0:3], part[3:6], part[6:9], part[9:]]))
    return part


def collect_engine_identity(ecu, reporter: Reporter | None = None) -> EngineIdentity:
    """Read a small identity set and return text suitable for profile matching.

    This is read-only.  It deliberately avoids 1A 90/VIN because part/component
    matching is enough for the currently known profiles.
    """

    identity = EngineIdentity()
    for local_id, timeout in ENGINE_PROFILE_IDENT_IDS:
        try:
            resp = ecu.kwp_request(
                [0x1A, local_id],
                timeout=timeout,
                max_pending=160,
                expected_prefixes=[bytes([0x5A, local_id]), b"\x7F\x1A"],
                strict_expected=True,
            )
        except Exception as exc:
            if reporter:
                reporter.detail(f"Engine profile ident 1A {local_id:02X} failed/ignored: {exc}")
            continue

        identity.responses[local_id] = resp
        neg = decode_negative(resp)
        if neg:
            if reporter:
                _, code, name = neg
                reporter.detail(f"Engine profile ident 1A {local_id:02X}: negative 0x{code:02X} {name}")
            continue

        payload = resp[2:] if len(resp) >= 2 and resp[0] == 0x5A else resp
        runs = ascii_runs(payload, min_len=4)
        identity.text_runs.extend(runs)

    identity.text = " | ".join(identity.text_runs)
    identity.normalized = _normalise(identity.text)

    m = _PART_RE.search(identity.normalized)
    if m:
        identity.part_number = _pretty_part(m.group(1))

    for run in identity.text_runs:
        up = run.upper()
        if "EDC" in up or "MED" in up or "MOTRONIC" in up or "SIMOS" in up:
            identity.component = run.strip(" \x00\xff()")
            break

    return identity


def resolve_engine_profile_from_identity(identity: EngineIdentity) -> EngineProfile:
    norm = identity.normalized
    for profile in ENGINE_PROFILES:
        for prefix in profile.part_prefixes:
            if _normalise(prefix) and _normalise(prefix) in norm:
                return profile
        for needle in profile.component_contains:
            if _normalise(needle) and _normalise(needle) in norm:
                return profile
    return UNKNOWN_ENGINE_PROFILE


def is_subfunction_not_supported(resp: bytes) -> bool:
    return len(resp) >= 3 and resp[0] == 0x7F and resp[1] == 0x18 and resp[2] in (0x11, 0x12)


def read_engine_dtcs_with_profile(ecu, reporter: Reporter, announce: bool = True) -> EngineDtcReadResult:
    """Resolve Engine 01 profile and perform the matching read-only DTC read.

    Unknown ECUs use a conservative fallback: try the BKD/EDC16 request first;
    only if the ECU says the ReadDTC subfunction is unsupported do we try the
    MED9-observed 18 00 FF 00 variant.
    """

    identity = collect_engine_identity(ecu, reporter=reporter)
    profile = resolve_engine_profile_from_identity(identity)

    if announce:
        reporter.info(f"Engine profile: {profile.name}")
        if identity.part_number:
            reporter.info(f"Engine identity part: {identity.part_number}")
        if identity.component:
            reporter.info(f"Engine identity component: {identity.component}")
        if profile.key == UNKNOWN_ENGINE_PROFILE.key:
            reporter.warn("Engine identity did not match a known profile; using read-only fallback DTC strategy.")

    attempts: list[tuple[tuple[int, ...], bytes]] = []
    last_resp = b""
    last_cmd: tuple[int, ...] = tuple()

    for idx, req in enumerate(profile.dtc_read_sequence()):
        last_cmd = req
        if announce:
            reporter.info(f"DTC read command: {fmt(req)}")
        resp = ecu.kwp_request(
            list(req),
            timeout=6.0,
            max_pending=160,
            expected_prefixes=[b"\x58", b"\x7F\x18"],
            strict_expected=True,
        )
        attempts.append((req, resp))
        last_resp = resp

        if is_subfunction_not_supported(resp) and idx + 1 < len(profile.dtc_read_sequence()):
            if announce:
                reporter.warn(f"DTC read {fmt(req)} not supported by this ECU; trying next profile variant.")
            continue
        return EngineDtcReadResult(profile=profile, identity=identity, response=resp, command=req, attempts=attempts)

    return EngineDtcReadResult(profile=profile, identity=identity, response=last_resp, command=last_cmd, attempts=attempts)


def engine_profile_lines() -> list[str]:
    lines = [
        "Engine profile resolver",
        "",
        "Profile matching is intentionally small and evidence-based.",
        "Add a new EngineProfile when a VCDS/ODIS capture proves a different ECU family needs a different read-only DTC strategy.",
        "",
        "Known profiles:",
    ]
    for profile in ENGINE_PROFILES:
        lines.append(f"  {profile.key}: {profile.name}")
        lines.append(f"    family:       {profile.family}")
        lines.append(f"    match parts:  {', '.join(profile.part_prefixes) or '-'}")
        lines.append(f"    match text:   {', '.join(profile.component_contains) or '-'}")
        lines.append(f"    DTC read:     {fmt(profile.primary_dtc_read)}")
        if profile.fallback_dtc_reads:
            lines.append("    fallbacks:    " + "; ".join(fmt(req) for req in profile.fallback_dtc_reads))
        if profile.notes:
            lines.append(f"    notes:        {profile.notes}")
    lines.append("")
    lines.append(f"Unknown fallback DTC reads: {'; '.join(fmt(req) for req in UNKNOWN_ENGINE_PROFILE.dtc_read_sequence())}")
    return lines

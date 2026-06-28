from __future__ import annotations

from .dtc import DtcDatabase, print_dtc_response
from .kwp import decode_negative
from .reporting import Reporter
from .utils import ascii_runs, fmt
from .tp20 import TP_CHANNEL_TEST_RESPONSE_VCDS_MODULE
from .vehicle_profile import ModuleProfile, find_module


# VCDS traces for 03/08/17/19/44/46 show these IDs being useful on
# non-engine modules. Engine ident still uses 0x90/0x9C in the dedicated
# engine path.
IDENT_REQUESTS = [
    ("ECU identity extended", [0x1A, 0x9B]),
    ("HW / supplier identity", [0x1A, 0x91]),
]

OPTIONAL_IDENT_REQUESTS = [
    ("Gateway/installed-list style identity", [0x1A, 0x9F]),
    ("Additional identity", [0x1A, 0x9A]),
    ("VIN / chassis identity", [0x1A, 0x90]),
    ("ECU identity extra", [0x1A, 0x9C]),
]

PROVEN_DTC_READ = [0x18, 0x02, 0xFF, 0x00]
ROUTINE_B8_READ = [0x31, 0xB8, 0x00, 0x00]
OPTIONAL_DTC_READS = [
    ("Read DTCs mode 18 00 FF 00", [0x18, 0x00, 0xFF, 0x00]),
]

# Module-specific VCDS-style preambles observed in the splitter captures.
# These are read-only service requests used before VCDS asks for DTCs.
# 31 B8 00 00 is kept as an opaque VCDS-observed read/status request.
VCDS_DTC_PREAMBLE_BY_ADDRESS: dict[str, list[tuple[str, list[int], float]]] = {
    "03": [
        ("VCDS preamble: 1A 9B", [0x1A, 0x9B], 40.0),
        ("VCDS preamble: 31 B8 00 00", ROUTINE_B8_READ, 12.0),
        # v0.3.13 proved ABS 1A 9B and 31 B8 are now aligned. The original
        # VCDS capture then asked 1A 91 before the eventual DTC read, so try
        # it again now that late 1A 9B payloads are drained correctly.
        ("VCDS preamble: 1A 91", [0x1A, 0x91], 20.0),
    ],
    "08": [
        ("VCDS preamble: 1A 9B", [0x1A, 0x9B], 18.0),
        ("VCDS preamble: 31 B8 00 00", ROUTINE_B8_READ, 10.0),
        ("VCDS preamble: 1A 91", [0x1A, 0x91], 10.0),
    ],
    "17": [
        ("VCDS preamble: 1A 9B", [0x1A, 0x9B], 18.0),
        ("VCDS preamble: 31 B8 00 00", ROUTINE_B8_READ, 10.0),
        ("VCDS preamble: 1A 91", [0x1A, 0x91], 10.0),
    ],
    "19": [
        ("VCDS preamble: 1A 9B", [0x1A, 0x9B], 18.0),
        ("VCDS preamble: 31 B8 00 00", ROUTINE_B8_READ, 10.0),
        ("VCDS preamble: 1A 9A", [0x1A, 0x9A], 12.0),
        ("VCDS preamble: 1A 91", [0x1A, 0x91], 12.0),
        # v0.3.11 live gateway showed 1A 9F can close the channel when used
        # here. VCDS uses 1A 9F in its earlier gateway/default-screen passes,
        # but it is not required for read-DTC, so the active DTC workflow stops
        # after the safe observed IDs above.
    ],
    "44": [
        ("VCDS preamble: 1A 9B", [0x1A, 0x9B], 18.0),
        ("VCDS preamble: 31 B8 00 00", ROUTINE_B8_READ, 10.0),
        ("VCDS preamble: 1A 91", [0x1A, 0x91], 10.0),
    ],
    "46": [
        ("VCDS preamble: 1A 9B", [0x1A, 0x9B], 45.0),
        # v0.3.15 keeps this close to VCDS again. The transport layer now
        # drains/ignores late 5A identity fragments instead of mistaking them
        # for the next request's response.
        ("VCDS preamble: 31 B8 00 00", ROUTINE_B8_READ, 12.0),
        ("VCDS preamble: 1A 9A", [0x1A, 0x9A], 18.0),
        ("VCDS preamble: 1A 91", [0x1A, 0x91], 12.0),
    ],
}

# VCDS usually sends a few tester-side A3 channel tests before DTC read.
VCDS_PRE_DTC_KEEPALIVES = {
    # ABS VCDS trace sends a long tester-side A3 idle run between 1A 91 and
    # DTC read. The channel-test exchange is transport housekeeping, not a
    # diagnostic service. Other modules either do not need it or are already
    # proven without it.
    "03": 0,
    "08": 0,
    "17": 0,
    "19": 0,
    "44": 0,
    "46": 0,
}

# Some modules emit late identity payloads after a 1A request. 46 in
# particular can send several separate 5A 9B chunks. Drain longer there.
VCDS_EXTRA_DRAIN_BY_ADDRESS = {
    "03": (0.40, 8),
    # Central Convenience can emit many one-byte 5A fragments and several
    # identity records after one 1A 9B. Drain passively until quiet; do not
    # send more 1A 9B requests to drain it.
    "46": (0.45, 220),
}


def resolve_module_profile(module_key: str) -> tuple[int, ModuleProfile | None]:
    """Resolve a VCDS address/name to the TP2.0 logical address.

    Important: on this PQ35 vehicle, several VCDS addresses do not match the
    TP2.0 logical byte seen in the setup packet. For example VCDS address 17
    Instruments opens TP2.0 logical 0x07, and address 46 Central Convenience
    opens logical 0x21.
    """
    module = find_module(module_key)
    if module:
        if module.diag_logical_address is not None:
            return module.diag_logical_address & 0xFF, module
        try:
            return int(module.address, 16) & 0xFF, module
        except ValueError:
            pass

    key = module_key.strip().lower()
    if key.startswith("0x"):
        return int(key, 16) & 0xFF, None
    return int(key, 16) & 0xFF, None


# Backwards-compatible name used by older CLI code.
def resolve_module_address(module_key: str) -> tuple[int, ModuleProfile | None]:
    return resolve_module_profile(module_key)


def module_open_kwargs(module_key: str) -> dict[str, object]:
    logical, module = resolve_module_profile(module_key)
    kwargs: dict[str, object] = {"logical_address": logical}
    if module and module.ecu_to_tester_can_id is not None:
        kwargs["requested_ecu_tx_id"] = module.ecu_to_tester_can_id
    # Non-engine VCDS captures showed this tester response to ECU-side A3
    # while modules were in long waits. Engine keeps its original default.
    if module and module.address != "01" and module.has_vcds_tp20_profile:
        kwargs["channel_test_response"] = TP_CHANNEL_TEST_RESPONSE_VCDS_MODULE
        # Active v0.3.10 traces showed target modules accepting 10 89 then
        # ignoring the immediate post-session 1A/18 request. VCDS appears to
        # leave a small application-layer gap between KWP messages.
        kwargs["min_kwp_gap"] = 0.20
    return kwargs


def module_session(module: ModuleProfile | None, fallback: int = 0x89) -> int:
    if module and module.kwp_session is not None:
        return module.kwp_session & 0xFF
    return fallback & 0xFF


def module_dtc_request(module: ModuleProfile | None) -> list[int]:
    if module and module.dtc_read_request:
        return [x & 0xFF for x in module.dtc_read_request]
    return list(PROVEN_DTC_READ)


def module_vcds_key(module: ModuleProfile | None, module_key: str) -> str:
    if module:
        return module.address.upper()
    return module_key.strip().upper().removeprefix("0X").zfill(2)


def module_display_label(module: ModuleProfile | None, module_key: str) -> str:
    key = module_vcds_key(module, module_key)
    if module:
        return f"{module.name} / module {key}"
    return f"module {key}"


def print_kwp_raw_result(reporter: Reporter, label: str, req: list[int], resp: bytes) -> None:
    c = reporter.colour
    reporter.line(c.cyan(label))
    reporter.line(f"  req:  {fmt(req)}")
    reporter.line(f"  resp: {c.green(fmt(resp)) if resp else c.yellow('<empty>')}")

    neg = decode_negative(resp)
    if neg:
        svc, code, name = neg
        reporter.line(f"  negative: service=0x{svc:02X} code=0x{code:02X} {name}")
        return

    runs = ascii_runs(resp, min_len=4)
    if runs:
        reporter.line("  text:")
        for run in runs:
            reporter.line(f"    {c.green(run)}")




def expected_prefixes_for_request(req: list[int]) -> list[bytes]:
    if not req:
        return []
    if req[0] == 0x1A and len(req) >= 2:
        return [bytes([0x5A, req[1]]), b"\x7F\x1A"]
    if req[0] == 0x31:
        return [b"\x71", b"\x7F\x31"]
    if req[0] == 0x18:
        return [b"\x58", b"\x7F\x18"]
    return []


def print_kwp_late_payload(reporter: Reporter, label: str, resp: bytes) -> None:
    c = reporter.colour
    reporter.line(c.cyan(label))
    reporter.line(f"  late resp: {c.green(fmt(resp)) if resp else c.yellow('<empty>')}")
    runs = ascii_runs(resp, min_len=4)
    if runs:
        reporter.line("  text:")
        for run in runs:
            reporter.line(f"    {c.green(run)}")


def print_module_profile(reporter: Reporter, logical: int, module: ModuleProfile | None) -> None:
    reporter.header(f"Read-only module probe 0x{logical:02X}")
    if module:
        reporter.line(f"VCDS address: {module.address}")
        reporter.line(f"Module:       {module.name}")
        reporter.line(f"Part number:  {reporter.colour.green(module.part_number) if module.part_number else reporter.colour.dim('unknown')}")
        reporter.line(f"Role:         {module.role}")
        reporter.line(f"Protocol:     {module.likely_protocol}")
        if module.has_vcds_tp20_profile:
            reporter.line(
                "TP2.0:       "
                f"logical=0x{module.diag_logical_address:02X} "
                f"tester→ECU=0x{module.tester_to_ecu_can_id:03X} "
                f"ECU→tester=0x{module.ecu_to_tester_can_id:03X} "
                f"session=0x{module.kwp_session:02X}"
            )
        if module.notes:
            reporter.line(f"Notes:        {module.notes}")
    reporter.warn("Read-only probe: session open + ident/DTC reads only. No clear/coding/adaptation/output tests.")


def run_vcds_dtc_preamble(ecu, reporter: Reporter, module_key: str, module: ModuleProfile | None) -> None:
    key = module_vcds_key(module, module_key)
    steps = VCDS_DTC_PREAMBLE_BY_ADDRESS.get(key, [])
    if not steps:
        return

    reporter.header("VCDS-style pre-DTC ritual")
    reporter.detail("Replay read-only ID/status requests seen before VCDS asks for DTCs.")

    for label, req, timeout in steps:
        try:
            resp = ecu.kwp_request(
                req,
                timeout=timeout,
                max_pending=240,
                expected_prefixes=expected_prefixes_for_request(req),
                strict_expected=True,
            )
            print_kwp_raw_result(reporter, label, req, resp)

            # Drain passive late payloads after read-ID requests. This is a
            # receive/ACK operation only. It must not send another 1A request.
            if req[:1] == [0x1A]:
                try:
                    quiet_timeout, max_extra_frames = VCDS_EXTRA_DRAIN_BY_ADDRESS.get(key, (0.30, 8))
                    bare_5a_count = 0
                    for index, extra in enumerate(
                        ecu.drain_kwp_extras(quiet_timeout=quiet_timeout, max_frames=max_extra_frames),
                        start=1,
                    ):
                        if extra == b"\x5A":
                            bare_5a_count += 1
                            continue
                        if bare_5a_count:
                            reporter.detail(f"Drained {bare_5a_count} one-byte stale 5A payload(s)")
                            bare_5a_count = 0
                        print_kwp_late_payload(reporter, f"{label} late payload #{index}", extra)
                    if bare_5a_count:
                        reporter.detail(f"Drained {bare_5a_count} one-byte stale 5A payload(s)")
                except Exception as extra_exc:
                    reporter.warn(f"{label} passive drain stopped: {extra_exc}")
        except Exception as exc:
            # VCDS tolerates unsupported optional IDs on some modules. Continue
            # so the DTC read can still be attempted and logged.
            reporter.warn(f"{label} failed/unsupported: {exc}")

    keepalives = VCDS_PRE_DTC_KEEPALIVES.get(key, 0)
    if keepalives:
        reporter.detail(f"Sending {keepalives} tester-side A3 keepalive(s) before DTC read")
        try:
            ecu.idle_keepalive(count=keepalives, interval=0.12)
        except Exception as exc:
            reporter.warn(f"Pre-DTC keepalive failed/ignored: {exc}")


def _dtc_required_len(resp: bytes) -> int | None:
    if len(resp) >= 2 and resp[0] == 0x58:
        return 2 + (resp[1] * 3)
    return None


def _merge_late_dtc_payloads(first: bytes, extras: list[bytes]) -> bytes:
    """Best-effort merge for modules that emit DTC data as late payloads.

    Some body modules can return a leading 58/count payload and then emit
    additional DTC bytes as separate application payloads. Keep this conservative:
    only extend positive 0x58 responses, and stop once the declared count has
    enough 3-byte records.
    """
    required = _dtc_required_len(first)
    if required is None or len(first) >= required:
        return first

    merged = bytearray(first)
    for extra in extras:
        if not extra:
            continue
        if extra[0] == 0x58:
            # Body modules can split DTC data as:
            #   first: 58 <count>
            #   late:  58 <dtc_hi> <dtc_lo> <status>
            # When the first response had only the wrapper/count, treat bytes
            # after the late 0x58 as record data. If the late response carries
            # its own count byte, this still remains conservative because we
            # stop as soon as the original declared count is satisfied.
            if len(first) <= 2 and len(extra) > 1:
                merged.extend(extra[1:])
            elif len(extra) > 2:
                merged.extend(extra[2:])
        else:
            merged.extend(extra)
        if len(merged) >= required:
            break
    return bytes(merged)


def run_module_dtc(ecu, reporter: Reporter, module_key: str, db: DtcDatabase) -> bytes:
    logical, module = resolve_module_profile(module_key)
    print_module_profile(reporter, logical, module)
    run_vcds_dtc_preamble(ecu, reporter, module_key, module)
    req = module_dtc_request(module)
    reporter.header("DTC read")
    reporter.info(f"KWP command: {fmt(req)}")
    key = module_vcds_key(module, module_key)
    timeout = 36.0 if key == "03" else 24.0
    resp = ecu.kwp_request(
        req,
        timeout=timeout,
        max_pending=240 if key == "03" else 160,
        expected_prefixes=expected_prefixes_for_request(req),
        strict_expected=True,
    )

    required = _dtc_required_len(resp)
    if required is not None and len(resp) < required:
        reporter.warn(
            f"DTC response declared {resp[1]} record(s) but only returned "
            f"{max(0, len(resp) - 2)} record byte(s); draining late payloads"
        )
        extras = ecu.drain_kwp_extras(quiet_timeout=0.45 if key != "46" else 0.80, max_frames=8 if key != "46" else 18)
        bare_58_count = 0
        shown_index = 0
        for extra in extras:
            if extra == b"\x58":
                bare_58_count += 1
                continue
            if bare_58_count:
                reporter.detail(f"Drained {bare_58_count} one-byte stale 58 payload(s)")
                bare_58_count = 0
            shown_index += 1
            print_kwp_late_payload(reporter, f"DTC late payload #{shown_index}", extra)
        if bare_58_count:
            reporter.detail(f"Drained {bare_58_count} one-byte stale 58 payload(s)")
        resp = _merge_late_dtc_payloads(resp, extras)

    print_dtc_response(reporter, resp, db, title="Module DTC result", ecu_label=module_display_label(module, module_key))
    return resp


def run_module_ident(ecu, reporter: Reporter, module_key: str, include_optional: bool = False) -> dict[str, bytes]:
    logical, module = resolve_module_profile(module_key)
    print_module_profile(reporter, logical, module)
    requests = list(IDENT_REQUESTS)
    if include_optional:
        requests.extend(OPTIONAL_IDENT_REQUESTS)

    results: dict[str, bytes] = {}
    reporter.header("Identification probes")
    for label, req in requests:
        try:
            resp = ecu.kwp_request(req, timeout=30.0, max_pending=240)
            print_kwp_raw_result(reporter, label, req, resp)
            results[label] = resp
        except Exception as exc:
            reporter.warn(f"{label} failed: {exc}")
            results[label] = b""
    return results


def run_read_only_probe(
    ecu,
    reporter: Reporter,
    module_key: str,
    db: DtcDatabase,
    ident: bool = True,
    dtcs: bool = True,
    optional_ident: bool = False,
    dtc_variants: bool = False,
) -> None:
    logical, module = resolve_module_profile(module_key)
    print_module_profile(reporter, logical, module)

    if ident:
        requests = list(IDENT_REQUESTS)
        if optional_ident:
            requests.extend(OPTIONAL_IDENT_REQUESTS)
        reporter.header("Identification probes")
        for label, req in requests:
            try:
                resp = ecu.kwp_request(req, timeout=30.0, max_pending=240)
                print_kwp_raw_result(reporter, label, req, resp)
            except Exception as exc:
                reporter.warn(f"{label} failed: {exc}")

    if dtcs:
        run_vcds_dtc_preamble(ecu, reporter, module_key, module)
        reporter.header("DTC read probes")
        req = module_dtc_request(module)
        try:
            resp = ecu.kwp_request(req, timeout=24.0, max_pending=160)
            reporter.line(reporter.colour.cyan("Read DTCs mode 18 02 FF 00"))
            reporter.detail(f"  req: {fmt(req)}")
            print_dtc_response(reporter, resp, db, title="Read DTCs mode 18 02 FF 00 result", ecu_label=module_display_label(module, module_key))
        except Exception as exc:
            reporter.warn(f"Read DTCs mode 18 02 FF 00 failed: {exc}")

        if dtc_variants:
            for label, variant_req in OPTIONAL_DTC_READS:
                try:
                    resp = ecu.kwp_request(variant_req, timeout=12.0, max_pending=80)
                    reporter.line(reporter.colour.cyan(label))
                    reporter.detail(f"  req: {fmt(variant_req)}")
                    print_dtc_response(reporter, resp, db, title=f"{label} result", ecu_label=module_display_label(module, module_key))
                except Exception as exc:
                    reporter.warn(f"{label} failed: {exc}")

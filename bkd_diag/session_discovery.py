from __future__ import annotations

import time

from .kwp import decode_negative
from .reporting import Reporter
from .tp20 import TP20KWP
from .utils import fmt
from .vehicle_profile import find_module


DEFAULT_SESSION_CANDIDATES = [0x89, 0x81, 0x85, 0x86, 0x87, 0x90]


def resolve_logical_address(module_key: str) -> tuple[int, object | None]:
    module = find_module(module_key)
    if module:
        try:
            return int(module.address, 16), module
        except ValueError:
            pass

    key = module_key.strip().lower()
    if key.startswith("0x"):
        return int(key, 16) & 0xFF, None
    return int(key, 16) & 0xFF, None


def run_session_discovery(
    iface: str,
    reporter: Reporter,
    module_key: str,
    candidates: list[int] | None = None,
    timeout: float = 2.0,
) -> int | None:
    logical, module = resolve_logical_address(module_key)
    candidates = candidates or DEFAULT_SESSION_CANDIDATES

    reporter.header(f"KWP session discovery for 0x{logical:02X}")
    if module:
        reporter.line(f"Module:      {module.name}")
        reporter.line(f"Part number: {reporter.colour.green(module.part_number) if module.part_number else reporter.colour.dim('unknown')}")
        reporter.line(f"Role:        {module.role}")

    reporter.warn("Session discovery opens TP2.0 and sends StartDiagnosticSession only. No DTC read, clear, coding, adaptation, basic settings or output tests.")

    first_positive: int | None = None

    for candidate in candidates:
        reporter.header(f"Trying session 0x{candidate:02X}")
        ecu = TP20KWP(iface=iface, reporter=reporter, logical_address=logical)
        try:
            try:
                ecu.open(session=candidate, start_session=False)
            except Exception as exc:
                reporter.warn(f"TP2.0 setup/channel open failed before session 0x{candidate:02X}: {exc}")
                continue

            try:
                resp = ecu.kwp_request([0x10, candidate], timeout=timeout)
                reporter.line(f"Response: {fmt(resp)}")

                neg = decode_negative(resp)
                if neg:
                    _svc, code, name = neg
                    reporter.warn(f"Negative response: code=0x{code:02X} {name}")
                elif len(resp) >= 2 and resp[0] == 0x50 and resp[1] == candidate:
                    reporter.ok(f"Session 0x{candidate:02X} accepted")
                    if first_positive is None:
                        first_positive = candidate
                else:
                    reporter.warn("Unexpected non-negative response")
            except Exception as exc:
                reporter.warn(f"Session 0x{candidate:02X} failed/timed out: {exc}")
        finally:
            ecu.close()
            time.sleep(0.20)

    if first_positive is not None:
        reporter.ok(f"First accepted session: 0x{first_positive:02X}")
    else:
        reporter.warn("No tested session was accepted. Try --no-session-open or sniff VCDS.")
    return first_positive

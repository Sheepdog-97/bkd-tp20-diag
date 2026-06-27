from __future__ import annotations

from .dtc import DtcDatabase, print_dtc_response
from .kwp import decode_negative
from .reporting import Reporter
from .utils import ascii_runs, fmt
from .vehicle_profile import find_module


IDENT_REQUESTS = [
    ("VIN / chassis identity", [0x1A, 0x90]),
    ("HW / supplier identity", [0x1A, 0x91]),
    ("ECU identity extended", [0x1A, 0x9B]),
    ("ECU identity extra", [0x1A, 0x9C]),
]

DTC_READ_REQUESTS = [
    ("Read DTCs mode 18 02 FF 00", [0x18, 0x02, 0xFF, 0x00]),
    ("Read DTCs mode 18 00 FF 00", [0x18, 0x00, 0xFF, 0x00]),
]


def resolve_module_address(module_key: str) -> tuple[int, object | None]:
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


def run_read_only_probe(ecu, reporter: Reporter, module_key: str, db: DtcDatabase, ident: bool = True, dtcs: bool = True) -> None:
    logical, module = resolve_module_address(module_key)

    reporter.header(f"Read-only module probe 0x{logical:02X}")
    if module:
        reporter.line(f"Module:      {module.name}")
        reporter.line(f"Part number: {reporter.colour.green(module.part_number) if module.part_number else reporter.colour.dim('unknown')}")
        reporter.line(f"Role:        {module.role}")
        reporter.line(f"Protocol:    {module.likely_protocol}")
        if module.notes:
            reporter.line(f"Notes:       {module.notes}")

    reporter.warn("Read-only probe: session open + ident/DTC reads only. No clear/coding/adaptation/output tests.")

    if ident:
        reporter.header("Identification probes")
        for label, req in IDENT_REQUESTS:
            try:
                resp = ecu.kwp_request(req, timeout=6.0)
                print_kwp_raw_result(reporter, label, req, resp)
            except Exception as exc:
                reporter.warn(f"{label} failed: {exc}")

    if dtcs:
        reporter.header("DTC read probes")
        for label, req in DTC_READ_REQUESTS:
            try:
                resp = ecu.kwp_request(req, timeout=6.0)
                reporter.line(reporter.colour.cyan(label))
                reporter.detail(f"  req: {fmt(req)}")
                print_dtc_response(reporter, resp, db, title=f"{label} result")
            except Exception as exc:
                reporter.warn(f"{label} failed: {exc}")

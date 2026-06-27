from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from .kwp import decode_negative
from .reporting import Reporter
from .utils import fmt


BUILTIN_DTC_LOOKUP: dict[int, dict[str, str]] = {
    16486: {
        "pcode": "P0102",
        "description": "Mass Air Flow Sensor (G70): Signal too Low",
        "hint": "Proven on this BKD test ECU by unplugging MAF/G70.",
    },
}


STATUS_BITS = {
    0x01: "test failed now",
    0x02: "failed this operation cycle",
    0x04: "pending DTC",
    0x08: "confirmed DTC",
    0x10: "test not completed since last clear",
    0x20: "test failed since last clear",
    0x40: "test not completed this operation cycle",
    0x80: "warning indicator/MIL requested",
}


@dataclass
class DtcDatabase:
    lookup: dict[int, dict[str, str]]

    @classmethod
    def built_in(cls) -> "DtcDatabase":
        return cls(dict(BUILTIN_DTC_LOOKUP))

    def load_csv(self, path: str, reporter: Reporter | None = None) -> None:
        if not path:
            return
        if not os.path.exists(path):
            if reporter:
                reporter.warn(f"DTC database not found: {path}")
            return

        count = 0
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                raw_code = (row.get("vag_code") or row.get("code") or "").strip()
                if not raw_code:
                    continue
                try:
                    code = int(raw_code, 0)
                except ValueError:
                    continue

                self.lookup[code] = {
                    "pcode": (row.get("pcode") or "").strip(),
                    "description": (row.get("description") or "").strip(),
                    "hint": (row.get("hint") or "").strip(),
                }
                count += 1

        if reporter:
            reporter.ok(f"Loaded {count} DTC record(s) from {path}")

    def write_template(self, path: str) -> None:
        if os.path.exists(path):
            raise RuntimeError(f"Refusing to overwrite existing file: {path}")

        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["vag_code", "pcode", "description", "hint"])
            for code, info in sorted(BUILTIN_DTC_LOOKUP.items()):
                writer.writerow([code, info.get("pcode", ""), info.get("description", ""), info.get("hint", "")])


def status_bit_text(status: int) -> list[str]:
    return [name for bit, name in STATUS_BITS.items() if status & bit]


def dtc_count_from_response(resp: bytes) -> int | None:
    if resp and len(resp) >= 2 and resp[0] == 0x58:
        return resp[1]
    return None


def print_dtc_response(reporter: Reporter, resp: bytes, db: DtcDatabase, title: str = "Fault read result") -> None:
    c = reporter.colour
    reporter.header(title)
    reporter.detail(f"{c.dim('KWP raw response:')} {fmt(resp)}")

    neg = decode_negative(resp)
    if neg:
        svc, code, name = neg
        reporter.fail(f"Negative KWP response to service 0x{svc:02X}: 0x{code:02X} {name}")
        return

    if not resp:
        reporter.warn("Empty response")
        return

    if resp[0] != 0x58:
        reporter.warn("Unexpected response. Positive ReadDTC response normally starts with 0x58.")
        reporter.detail(f"Raw: {fmt(resp)}")
        return

    if len(resp) == 1:
        reporter.warn("Positive response 0x58, but no count/data byte returned.")
        return

    count = resp[1]
    records = resp[2:]

    if count == 0:
        reporter.ok("No DTCs reported by the engine ECU for this read mode")
        reporter.detail("Decoded meaning: 58 00 = positive DTC-read response, zero faults")
        return

    reporter.warn(f"ECU reports {count} DTC record(s)")

    if len(records) % 3 != 0:
        reporter.warn("DTC record data is not a clean multiple of 3 bytes.")
        reporter.detail("Expected VAG KWP format here is usually: DTC_HI DTC_LO STATUS")
        reporter.detail(f"Raw records: {fmt(records)}")
        return

    for idx in range(0, len(records), 3):
        hi, lo, status = records[idx], records[idx + 1], records[idx + 2]
        dtc_num = (hi << 8) | lo
        known = db.lookup.get(dtc_num)
        number = idx // 3 + 1

        reporter.line("")
        reporter.line(c.bold(f"DTC {number}"))
        reporter.line(f"  VAG decimal: {c.yellow(str(dtc_num))}")
        reporter.line(f"  Raw DTC hex: 0x{dtc_num:04X}")
        reporter.line(f"  Raw record:  {hi:02X} {lo:02X} {status:02X}")
        reporter.line(f"  Status byte: 0x{status:02X}")

        bits = status_bit_text(status)
        if bits:
            reporter.line("  Status bits:")
            for bit_name in bits:
                reporter.line(f"    - {bit_name}")

        if known:
            if known.get("pcode"):
                reporter.line(f"  OBD/P-code:  {c.yellow(known['pcode'])}")
            if known.get("description"):
                reporter.line(f"  Meaning:     {c.green(known['description'])}")
            if known.get("hint"):
                reporter.line(f"  Hint:        {known['hint']}")
        else:
            reporter.line(f"  Meaning:     {c.dim('Unknown in local lookup table')}")
            reporter.line("  Hint:        Add this VAG decimal code to your CSV DTC database.")

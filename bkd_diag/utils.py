from __future__ import annotations

import re
from typing import Iterable

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def fmt(data: Iterable[int] | bytes | bytearray) -> str:
    return " ".join(f"{int(b) & 0xFF:02X}" for b in data)


def parse_hex_items(items: list[str]) -> list[int]:
    out: list[int] = []
    for item in items:
        item = item.replace(",", " ")
        for part in item.split():
            out.append(int(part, 16) & 0xFF)
    return out


def parse_int_auto(text: str) -> int:
    value = text.strip()
    if value.lower().startswith("0x"):
        return int(value, 16)
    # Treat leading-zero CLI values as decimal measuring block numbers.
    # Python's int(x, 0) rejects strings like "001"; users naturally type
    # VAG groups as 001/003/011.
    return int(value, 10)


def ascii_printable(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else "." for b in data)


def ascii_runs(data: bytes, min_len: int = 4) -> list[str]:
    runs: list[str] = []
    cur: list[str] = []

    for b in data:
        if 32 <= b <= 126:
            cur.append(chr(b))
        else:
            if len(cur) >= min_len:
                run = "".join(cur).strip("()[]{}<>.,;:'\"`~!@#$%^&*_+=|\\/ ")
                if run:
                    runs.append(run)
            cur = []

    if len(cur) >= min_len:
        run = "".join(cur).strip("()[]{}<>.,;:'\"`~!@#$%^&*_+=|\\/ ")
        if run:
            runs.append(run)

    return runs

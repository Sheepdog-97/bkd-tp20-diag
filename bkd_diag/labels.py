from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass
class LabelStore:
    path: str
    readable: bool
    error: str | None = None
    groups: dict[int, dict[int, str]] = field(default_factory=dict)
    group_names: dict[int, str] = field(default_factory=dict)
    raw_line_count: int = 0

    def field_label(self, block_num: int, field_index: int) -> str | None:
        return self.groups.get(block_num, {}).get(field_index)

    def group_name(self, block_num: int) -> str | None:
        return self.group_names.get(block_num)


def looks_binary(data: bytes) -> bool:
    if not data:
        return False
    sample = data[:4096]
    nul_count = sample.count(b"\x00")
    if nul_count:
        return True
    textish = sum(1 for b in sample if b in b"\r\n\t" or 32 <= b <= 126)
    return (textish / len(sample)) < 0.85


def parse_label_file(path: str) -> LabelStore:
    """
    Best-effort parser for readable Ross-Tech-style label files.

    Many .clb files are compiled/proprietary and not directly parseable as text.
    This parser intentionally does not try to defeat that. It only extracts useful
    labels from plain-text .lbl files or readable .clb text.
    """
    if not os.path.exists(path):
        return LabelStore(path=path, readable=False, error="file not found")

    data = open(path, "rb").read()
    if looks_binary(data):
        return LabelStore(
            path=path,
            readable=False,
            error="file appears binary/compiled; use a plain .lbl or extracted labels if available",
        )

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")

    store = LabelStore(path=path, readable=True)
    lines = text.splitlines()
    store.raw_line_count = len(lines)

    current_group: int | None = None

    # Handle several common-ish text patterns:
    #   003,0,MAF/EGR
    #   003,1,Engine Speed
    #   Group 003: MAF/EGR
    #   003-1 Engine Speed
    # This is deliberately best-effort because label formats vary.
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith(";") or raw.startswith("#"):
            continue

        m = re.search(r"\bGroup\s+(\d{3})\b\s*[:,-]?\s*(.*)", raw, re.I)
        if m:
            current_group = int(m.group(1))
            name = m.group(2).strip(" ,;-")
            if name:
                store.group_names[current_group] = name
            continue

        m = re.match(r"^(\d{3})\s*[,;]\s*(\d)\s*[,;]\s*(.+)$", raw)
        if m:
            group = int(m.group(1))
            field = int(m.group(2))
            label = m.group(3).strip(" ,;")
            if field == 0:
                store.group_names[group] = label
            else:
                store.groups.setdefault(group, {})[field] = label
            current_group = group
            continue

        m = re.match(r"^(\d{3})\s*[-.]\s*(\d)\s+(.+)$", raw)
        if m:
            group = int(m.group(1))
            field = int(m.group(2))
            label = m.group(3).strip(" ,;")
            store.groups.setdefault(group, {})[field] = label
            current_group = group
            continue

        # If a block/group was named on a preceding line, catch simple field lines:
        #   1,Engine Speed
        #   1 - Engine Speed
        if current_group is not None:
            m = re.match(r"^([1-8])\s*[,;:-]\s*(.+)$", raw)
            if m:
                field = int(m.group(1))
                label = m.group(2).strip(" ,;")
                store.groups.setdefault(current_group, {})[field] = label

    return store

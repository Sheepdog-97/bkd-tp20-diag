from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bkd_data import BLOCK_HINTS, OBSERVED_ACTIVE_BLOCKS, OBSERVED_EMPTY_BLOCKS, PRESETS
from .utils import ascii_runs, fmt


EMPTY_FIELD = bytes([0x25, 0x00, 0x00])


def decode_measuring_value(type_byte: int, a: int, b: int) -> dict[str, Any] | None:
    raw_u16 = (a << 8) | b

    # VAG/KWP measuring values are three-byte cells: formula byte + A + B.
    # The first public builds wrongly treated several cells as a big-endian
    # integer divided by a constant.  An ignition-on/engine-off capture proved
    # that formula was bogus: 01 69 00 decoded as ~840 rpm even though the
    # engine was stopped.  These formula-byte decodes now use the classic VAG
    # measured-value table shape and are kept deliberately small/conservative.
    if type_byte == 0x01:
        value = a * 0.2 * b
        return {"value": value, "unit": "rpm", "kind": "engine speed", "text": f"{value:.0f} rpm"}

    if type_byte == 0x12:
        value = 0.04 * a * b
        return {"value": value, "unit": "mbar", "kind": "pressure", "text": f"{value:.1f} mbar"}

    if type_byte == 0x17:
        value = (a * b) / 256.0
        return {"value": value, "unit": "%", "kind": "percentage/duty", "text": f"{value:.1f} %"}

    if type_byte == 0x31:
        # Formula byte 0x31 is commonly an air-mass-per-stroke style value on
        # TDI blocks.  The base table is effectively A*B/4 with an implied
        # one-decimal display for these labels, hence /40 here.  This makes
        # 31 C8 00 decode to 0 instead of a false ~400 mg/str with engine off.
        value = (a * b) / 40.0
        return {"value": value, "unit": "mg/str", "kind": "air mass", "text": f"{value:.1f} mg/str"}

    return None


def block_hint(block_num: int, labels=None) -> dict[str, Any]:
    base = dict(BLOCK_HINTS.get(block_num, {"name": f"Block {block_num:03d}", "confidence": "unknown", "fields": {}}))
    base["fields"] = dict(base.get("fields", {}))
    if labels:
        group_name = labels.group_name(block_num)
        if group_name:
            base["name"] = group_name
            base["confidence"] = "label-file"
        for i in range(1, 9):
            lab = labels.field_label(block_num, i)
            if lab:
                base["fields"][i] = lab
                base["confidence"] = "label-file"
    return base


def split_measuring_fields(block_num: int, payload: bytes, labels=None) -> list[dict[str, Any]]:
    hint = block_hint(block_num, labels=labels)
    labels = hint.get("fields", {})
    fields: list[dict[str, Any]] = []

    for idx in range(0, len(payload), 3):
        chunk = payload[idx:idx + 3]
        field_index = (idx // 3) + 1

        if len(chunk) < 3:
            fields.append({
                "index": field_index,
                "raw": chunk,
                "label": labels.get(field_index, f"Field {field_index}"),
                "status": "partial",
            })
            continue

        type_byte, a, b = chunk
        unsigned = (a << 8) | b
        signed = unsigned - 0x10000 if unsigned & 0x8000 else unsigned
        empty = chunk == EMPTY_FIELD
        decoded = None if empty else decode_measuring_value(type_byte, a, b)

        fields.append({
            "index": field_index,
            "raw": chunk,
            "type": type_byte,
            "a": a,
            "b": b,
            "unsigned": unsigned,
            "signed": signed,
            "empty": empty,
            "status": "empty" if empty else "active",
            "label": labels.get(field_index, f"Field {field_index}"),
            "decoded": decoded,
        })

    return fields


def decode_block_response(block_num: int, resp: bytes, labels=None) -> dict[str, Any] | None:
    if len(resp) < 2 or resp[0] != 0x61 or resp[1] != (block_num & 0xFF):
        return None

    payload = bytes(resp[2:])
    fields = split_measuring_fields(block_num, payload, labels=labels)
    active_fields = [f for f in fields if f.get("status") == "active"]
    empty_fields = [f for f in fields if f.get("status") == "empty"]
    hint = block_hint(block_num, labels=labels)
    text_runs = ascii_runs(payload, min_len=4) if hint.get("text") else []

    if hint.get("text") and text_runs:
        classification = "text"
    elif active_fields:
        classification = "active"
    elif empty_fields and len(empty_fields) == len(fields):
        classification = "empty"
    else:
        classification = "mixed"

    return {
        "block": block_num,
        "payload": payload,
        "fields": fields,
        "active_count": len(active_fields),
        "empty_count": len(empty_fields),
        "classification": classification,
        "text_runs": text_runs,
        "hint": hint,
    }


def short_field_label(label: str) -> str:
    replacements = {
        "Engine speed": "rpm",
        "MAF specified": "MAF spec",
        "MAF actual": "MAF actual",
        "EGR duty": "EGR duty",
        "Boost specified": "boost spec",
        "Boost actual": "boost actual",
        "Boost control duty / N75": "boost duty",
        "Boost control duty": "boost duty",
        "Charge pressure specified": "boost spec",
        "Charge pressure actual": "boost actual",
    }
    return replacements.get(label, label)


def field_display(field: dict[str, Any]) -> str:
    if field.get("status") == "empty":
        return "empty"
    if field.get("status") == "partial":
        return f"partial raw={fmt(field.get('raw', b''))}"
    if field.get("decoded"):
        return field["decoded"]["text"]
    return f"raw={fmt(field.get('raw', b''))} u16={field.get('unsigned', '')}"



def _c(colour, method: str, text: str) -> str:
    if colour is None:
        return text
    return getattr(colour, method)(text)


def live_line(block_num: int, decoded_block: dict[str, Any], include_raw: bool = False, raw_resp: bytes | None = None, colour=None) -> str:
    hint = decoded_block["hint"]
    parts = [_c(colour, "bold", f"block {block_num:03d}")]

    if hint.get("name") and hint["name"] != f"Block {block_num:03d}":
        parts.append(_c(colour, "cyan", f"({hint['name']})"))

    if decoded_block.get("classification") == "text":
        text = " | ".join(decoded_block.get("text_runs", [])) or "<no printable text>"
        parts.append("text=" + _c(colour, "green", text))
        if include_raw and raw_resp is not None:
            parts.append(_c(colour, "dim", f"raw={fmt(raw_resp)}"))
        return "  ".join(parts)

    for field in decoded_block["fields"]:
        if field.get("status") == "empty":
            continue
        label = _c(colour, "cyan", short_field_label(field.get("label", f"F{field.get('index')}")))
        value = field_display(field)
        if field.get("decoded"):
            value = _c(colour, "green", value)
        elif field.get("status") == "active":
            value = _c(colour, "yellow", value)
        parts.append(f"{label}={value}")

    if include_raw and raw_resp is not None:
        parts.append(_c(colour, "dim", f"raw={fmt(raw_resp)}"))

    return "  ".join(parts)


def format_block_table(decoded_block: dict[str, Any], detail: bool = True, colour=None) -> list[str]:
    lines: list[str] = []
    block_num = decoded_block["block"]
    hint = decoded_block["hint"]

    title = f"Block {block_num:03d}: {hint.get('name', 'unknown')} [{hint.get('confidence', 'unknown')}]"
    lines.append(_c(colour, "bold", title))

    cls = decoded_block["classification"]
    cls_col = "green" if cls in ("active", "text") else "yellow"
    lines.append(
        "  classification="
        + _c(colour, cls_col, cls)
        + f" active={_c(colour, 'green', str(decoded_block['active_count']))} "
        + f"empty={_c(colour, 'dim', str(decoded_block['empty_count']))} "
        + f"payload={len(decoded_block['payload'])} byte(s)"
    )

    if decoded_block.get("classification") == "text":
        if decoded_block.get("text_runs"):
            for run in decoded_block["text_runs"]:
                lines.append(f"  text: {_c(colour, 'green', run)}")
        else:
            lines.append(f"  text: {_c(colour, 'yellow', '<no printable text>')}")
        if detail:
            lines.append(_c(colour, "dim", f"  raw payload: {fmt(decoded_block['payload'])}"))
        return lines

    for field in decoded_block["fields"]:
        idx = field["index"]
        label = _c(colour, "cyan", field.get("label", f"Field {idx}"))
        if field.get("status") == "empty":
            lines.append(_c(colour, "dim", f"  F{idx}: empty raw={fmt(field['raw'])}"))
            continue

        if field.get("status") == "partial":
            lines.append(f"  F{idx}: " + _c(colour, "yellow", f"partial raw={fmt(field['raw'])}"))
            continue

        value = field_display(field)
        if field.get("decoded"):
            value = _c(colour, "green", value)
        else:
            value = _c(colour, "yellow", value)

        line = (
            f"  F{idx}: {label}: {value} "
            + _c(colour, "dim", f"type=0x{field['type']:02X} raw={fmt(field['raw'])}")
        )
        if detail:
            line += _c(colour, "dim", f" u16={field['unsigned']} s16={field['signed']} bytes=({field['a']},{field['b']})")
        lines.append(line)

    return lines


def known_map_lines() -> list[str]:
    active = ", ".join(f"{b:03d}" for b in OBSERVED_ACTIVE_BLOCKS)
    empty = ", ".join(f"{b:03d}" for b in OBSERVED_EMPTY_BLOCKS)
    lines = [
        "Observed BKD block map",
        f"  active/non-empty observed: {active}",
        f"  empty-placeholder observed: {empty}",
        "",
        "High-confidence useful blocks:",
        "  003  EGR / air mass",
        "  011  charge pressure / boost control",
        "  013  idle stabilisation / injection quantity deviation",
        "  080  extended ECU identification text",
        "",
        "Useful presets:",
    ]
    for name, preset in PRESETS.items():
        blocks = " ".join(f"{b:03d}" for b in preset["blocks"])
        lines.append(f"  {name:<10} {blocks:<24} {preset['description']}")
    return lines


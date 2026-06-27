from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from typing import Any

from .tp20 import tp20_id_from_setup
from .utils import fmt


HASH_RE = re.compile(r"\b(?P<canid>[0-9A-Fa-f]{3,8})#(?P<data>[0-9A-Fa-f]*)\b")

# candump common and extended examples:
#   can0  200   [7]  03 C0 00 10 00 03 01
#   (ts) can0  RX - -  200   [7]  03 C0 00 10 00 03 01
BRACKET_RE = re.compile(
    r"(?<![#\w])(?P<canid>[0-9A-Fa-f]{3,8})\s+"
    r"(?:RX|TX)?\s*(?:-\s*){0,3}"
    r"\[(?P<dlc>[0-9]+)\]\s+"
    r"(?P<data>(?:[0-9A-Fa-f]{2}\s*){0,64})",
    re.IGNORECASE,
)

# Project trace/log examples:
#   TX 200 03 C0 00 10 00 03 01
#   RX 203 00 D0 00 03 90 07 01
#   CHAN-TEST-RESP 790 A1 0F 8A FF 32 FF
SPACE_RE = re.compile(
    r"^\s*(?:TX|RX|SETUP-PROBE|CHAN-TEST-RESP|CLOSE)?\s*"
    r"(?P<canid>[0-9A-Fa-f]{3,8})\s+"
    r"(?P<data>(?:[0-9A-Fa-f]{2}\s*){1,64})\s*$",
    re.IGNORECASE,
)

TS_RE = re.compile(r"\((?P<ts>[-+0-9.]+)\)")


@dataclass
class TraceFrame:
    line_no: int
    can_id: int
    data: bytes
    raw: str
    timestamp: str | None = None


@dataclass
class TraceEvent:
    line_no: int
    can_id: int
    data: bytes
    kind: str
    detail: str
    raw: str
    service: str | None = None
    service_id: int | None = None
    subfunction: int | None = None
    sequence: int | None = None


def _hex_to_bytes(hex_text: str) -> bytes:
    hex_text = re.sub(r"\s+", "", hex_text.strip())
    if not hex_text:
        return b""
    if len(hex_text) % 2:
        hex_text = hex_text[:-1]
    return bytes.fromhex(hex_text)


def parse_candump_line(line: str, line_no: int) -> TraceFrame | None:
    raw = line.rstrip("\n")
    if not raw.strip() or raw.lstrip().startswith("#"):
        return None

    ts_m = TS_RE.search(raw)
    timestamp = ts_m.group("ts") if ts_m else None

    for regex in (HASH_RE, BRACKET_RE, SPACE_RE):
        m = regex.search(raw)
        if not m:
            continue

        data = _hex_to_bytes(m.group("data"))
        if "dlc" in m.groupdict() and m.group("dlc"):
            try:
                data = data[:int(m.group("dlc"), 10)]
            except ValueError:
                pass

        return TraceFrame(
            line_no=line_no,
            can_id=int(m.group("canid"), 16),
            data=data,
            raw=raw,
            timestamp=timestamp,
        )

    return None


def read_trace(path: str | Path) -> list[TraceFrame]:
    frames: list[TraceFrame] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            frame = parse_candump_line(line, line_no)
            if frame is not None:
                frames.append(frame)
    return frames


def _kwp_payload_from_tp_data(data: bytes) -> bytes | None:
    if len(data) < 4:
        return None

    first = data[0]
    high = first & 0xF0
    if high not in (0x10, 0x20):
        return None

    declared = (data[1] << 8) | data[2]
    if declared == 0:
        return b""

    return bytes(data[3:3 + min(declared, len(data) - 3)])


def _kwp_service_name(svc: int) -> str:
    return {
        0x10: "StartDiagnosticSession request",
        0x50: "StartDiagnosticSession positive response",
        0x18: "ReadDTC request",
        0x58: "ReadDTC positive response",
        0x14: "ClearDTC request",
        0x54: "ClearDTC positive response",
        0x1A: "ReadECUIdentification request",
        0x5A: "ReadECUIdentification positive response",
        0x21: "ReadDataByLocalIdentifier/measuring block request",
        0x61: "ReadDataByLocalIdentifier/measuring block positive response",
        0x3E: "TesterPresent request",
        0x7E: "TesterPresent positive response",
        0x7F: "Negative response",
    }.get(svc, f"KWP service 0x{svc:02X}")


def describe_kwp(payload: bytes) -> tuple[str, str | None, int | None, int | None]:
    """Return detail, service label, service id, subfunction/local-id."""
    if not payload:
        return "empty KWP payload", None, None, None

    svc = payload[0]
    service = _kwp_service_name(svc)
    sub = payload[1] if len(payload) >= 2 else None

    if svc in (0x10, 0x50) and sub is not None:
        return f"{service}: {svc:02X} {sub:02X}", service, svc, sub

    if svc == 0x18:
        return f"{service}: {fmt(payload)}", service, svc, sub

    if svc == 0x58:
        if len(payload) >= 2:
            return f"{service}: count={payload[1]} raw={fmt(payload)}", service, svc, payload[1]
        return f"{service}: {fmt(payload)}", service, svc, sub

    if svc in (0x14, 0x54):
        return f"{service}: {fmt(payload)}", service, svc, sub

    if svc in (0x1A, 0x5A) and sub is not None:
        return f"{service}: {svc:02X} {sub:02X} len={len(payload)}", service, svc, sub

    if svc in (0x21, 0x61) and sub is not None:
        return f"{service}: {svc:02X} {sub:02X} ({sub:03d}) len={len(payload)}", service, svc, sub

    if svc == 0x7F and len(payload) >= 3:
        original = payload[1]
        code = payload[2]
        if code == 0x78:
            return f"Negative/pending response: 7F {original:02X} 78 responsePending", service, svc, original
        return f"Negative KWP response: service=0x{original:02X} code=0x{code:02X}", service, svc, original

    return f"{service}: {fmt(payload)}", service, svc, sub


def classify_frame(frame: TraceFrame) -> TraceEvent | None:
    data = frame.data
    if not data:
        return None

    if frame.can_id == 0x200 and len(data) >= 7 and data[1] == 0xC0:
        requested_rx, rx_valid = tp20_id_from_setup(data[2], data[3])
        requested_tx, tx_valid = tp20_id_from_setup(data[4], data[5])
        detail = (
            f"TP2.0 setup request logical=0x{data[0]:02X} "
            f"requested ECU→tester=0x{requested_tx:03X}{'' if tx_valid else ' invalid/auto'} "
            f"tester-id-field=0x{requested_rx:03X}{'' if rx_valid else ' invalid/auto'}"
        )
        return TraceEvent(frame.line_no, frame.can_id, data, "setup-request", detail, frame.raw)

    if len(data) >= 7 and data[1] == 0xD0:
        ecu_tx, ecu_valid = tp20_id_from_setup(data[2], data[3])
        tester_tx, tester_valid = tp20_id_from_setup(data[4], data[5])
        detail = (
            f"TP2.0 setup accepted logical≈0x{frame.can_id - 0x200:02X} "
            f"ECU→tester=0x{ecu_tx:03X}{'' if ecu_valid else ' invalid'} "
            f"tester→ECU=0x{tester_tx:03X}{'' if tester_valid else ' invalid'}"
        )
        return TraceEvent(frame.line_no, frame.can_id, data, "setup-response", detail, frame.raw)

    first = data[0]

    if first == 0xA0:
        return TraceEvent(frame.line_no, frame.can_id, data, "channel-params", f"TP2.0 channel parameter request: {fmt(data)}", frame.raw)
    if first == 0xA1:
        return TraceEvent(frame.line_no, frame.can_id, data, "channel-params-response", f"TP2.0 channel parameter/test response: {fmt(data)}", frame.raw)
    if first == 0xA3:
        return TraceEvent(frame.line_no, frame.can_id, data, "channel-test", "TP2.0 channel test / keepalive request A3", frame.raw)
    if first == 0xA8:
        return TraceEvent(frame.line_no, frame.can_id, data, "channel-close", "TP2.0 close/disconnect A8", frame.raw)
    if 0xB0 <= first <= 0xBF:
        return TraceEvent(frame.line_no, frame.can_id, data, "tp-ack", f"TP2.0 ACK/control frame {first:02X}", frame.raw)

    payload = _kwp_payload_from_tp_data(data)
    if payload is not None:
        seq = first & 0x0F
        detail, service, service_id, subfunction = describe_kwp(payload)
        return TraceEvent(
            frame.line_no,
            frame.can_id,
            data,
            "kwp",
            f"TP2.0 data seq={seq:X}: {detail}",
            frame.raw,
            service=service,
            service_id=service_id,
            subfunction=subfunction,
            sequence=seq,
        )

    return None


def analyse_trace(path: str | Path) -> tuple[list[TraceFrame], list[TraceEvent], Counter[int]]:
    frames = read_trace(path)
    events = [event for frame in frames if (event := classify_frame(frame)) is not None]
    counts = Counter(frame.can_id for frame in frames)
    return frames, events, counts


def build_summary(path: str | Path, frames: list[TraceFrame], events: list[TraceEvent], counts: Counter[int]) -> dict[str, Any]:
    setup_channels: list[dict[str, Any]] = []
    for event in events:
        if event.kind == "setup-response":
            data = event.data
            ecu_tx, ecu_valid = tp20_id_from_setup(data[2], data[3])
            tester_tx, tester_valid = tp20_id_from_setup(data[4], data[5])
            setup_channels.append({
                "line": event.line_no,
                "response_can_id": f"0x{event.can_id:X}",
                "logical_address_guess": f"0x{event.can_id - 0x200:02X}",
                "ecu_to_tester_can_id": f"0x{ecu_tx:X}" if ecu_valid else None,
                "tester_to_ecu_can_id": f"0x{tester_tx:X}" if tester_valid else None,
            })

    kwp_events = [event for event in events if event.kind == "kwp"]
    service_counts = Counter(event.service or "unknown" for event in kwp_events)

    sessions_requested = sorted({
        f"0x{event.subfunction:02X}"
        for event in kwp_events
        if event.service_id == 0x10 and event.subfunction is not None
    })

    ident_requests = sorted({
        f"0x{event.subfunction:02X}"
        for event in kwp_events
        if event.service_id == 0x1A and event.subfunction is not None
    })

    measuring_blocks = sorted({
        event.subfunction
        for event in kwp_events
        if event.service_id == 0x21 and event.subfunction is not None
    })

    return {
        "path": str(path),
        "frames_parsed": len(frames),
        "events_found": len(events),
        "can_id_counts": {f"0x{can_id:X}": count for can_id, count in sorted(counts.items())},
        "setup_channels": setup_channels,
        "service_counts": dict(service_counts),
        "sessions_requested": sessions_requested,
        "ident_requests": ident_requests,
        "measuring_block_requests": [f"{block:03d}" for block in measuring_blocks],
        "dtc_read_requests": sum(1 for event in kwp_events if event.service_id == 0x18),
        "dtc_read_responses": sum(1 for event in kwp_events if event.service_id == 0x58),
        "negative_responses": [
            {
                "line": event.line_no,
                "can_id": f"0x{event.can_id:X}",
                "detail": event.detail,
            }
            for event in kwp_events
            if event.service_id == 0x7F
        ],
        "events": [
            {
                "line": event.line_no,
                "can_id": f"0x{event.can_id:X}",
                "kind": event.kind,
                "data": fmt(event.data),
                "detail": event.detail,
                "service": event.service,
                "service_id": f"0x{event.service_id:02X}" if event.service_id is not None else None,
                "subfunction": f"0x{event.subfunction:02X}" if event.subfunction is not None else None,
                "sequence": event.sequence,
            }
            for event in events
        ],
    }


def write_summary_json(path: str | Path, summary: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

from __future__ import annotations

import bisect
import csv
import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .trace_analyzer import TraceFrame, read_trace
from .utils import fmt


# Diagnostic transport IDs used by the tool/VCDS on the proven PQ35 modules.
# Passive correlation normally wants vehicle broadcast traffic, not the active
# KWP measuring-block request/response that created the truth CSV.
DEFAULT_DIAGNOSTIC_CAN_IDS = {
    0x200, 0x201, 0x300,
    0x328, 0x32E, 0x33D,
    0x740, 0x750, 0x790, 0x7A8,
}


@dataclass(frozen=True)
class KnownPassiveSignal:
    name: str
    description: str
    can_id: int
    signal_expr: str
    signal_name: str
    unit: str = ""
    scale: float = 1.0
    offset: float = 0.0
    default_truth_field: str = ""
    status: str = "seed"
    notes: str = ""


@dataclass(frozen=True)
class KnownSignalOffsetResult:
    offset_seconds: float
    score: float
    correlation: float
    samples: int
    can_id: str
    signal: str
    expression: str
    slope_truth_per_raw: float
    intercept_truth: float
    rmse_truth: float
    raw_min: float
    raw_max: float
    truth_min: float
    truth_max: float


# User-observed PQ35 comfort/infotainment CAN seeds.  Treat "candidate" entries
# as research hints until they are validated with at least one independent
# capture.  Confirmed signals can still vary by vehicle/coding, so Open MMI
# should keep passive signal support profile-gated.
KNOWN_PASSIVE_SIGNALS: dict[str, KnownPassiveSignal] = {
    "dimmer_470_b2": KnownPassiveSignal(
        name="dimmer_470_b2",
        description="PQ35 dimming Terminal 58d percentage",
        can_id=0x470,
        signal_expr="b2",
        signal_name="byte[2] u8",
        unit="%",
        scale=1.0,
        default_truth_field="008.F3",
        status="confirmed",
        notes="Validated as a timing anchor and dimmer percentage: raw 30..100, corr +1.000 in the 2026-07-01 validation capture. Use as the preferred offset anchor on the 100 kbit/s comfort/infotainment bus.",
    ),
    "blower_3e1_b4": KnownPassiveSignal(
        name="blower_3e1_b4",
        description="PQ35 HVAC blower/turbine load percentage",
        can_id=0x3E1,
        signal_expr="b4",
        signal_name="byte[4] u8",
        unit="%",
        scale=100.0 / 255.0,
        default_truth_field="007.F3",
        status="confirmed",
        notes="Validated against HVAC 007.F3 Turbine Load over 0..95.6% on the 100 kbit/s comfort/infotainment bus: corr +0.998, raw 0..239, scale close to raw*100/255.",
    ),
    "speed_351_u16le_b1_200": KnownPassiveSignal(
        name="speed_351_u16le_b1_200",
        description="PQ35 vehicle speed",
        can_id=0x351,
        signal_expr="u16le1",
        signal_name="u16le[1:3]",
        unit="km/h",
        scale=1.0 / 200.0,
        default_truth_field="001.F3",
        status="confirmed",
        notes="Validated over 0..47 km/h: speed_kmh = u16le(bytes[1:3]) / 200. 0x351 byte[0] also carries reverse-state observations.",
    ),
    "speed_527_u16le_b1_200": KnownPassiveSignal(
        name="speed_527_u16le_b1_200",
        description="PQ35 vehicle speed duplicate/related broadcast",
        can_id=0x527,
        signal_expr="u16le1",
        signal_name="u16le[1:3]",
        unit="km/h",
        scale=1.0 / 200.0,
        default_truth_field="001.F3",
        status="confirmed",
        notes="Validated over 0..47 km/h: speed_kmh = u16le(bytes[1:3]) / 200. Ranked fractionally above 0x351 in the validation capture.",
    ),
    "speed_359_u16le_b1_200": KnownPassiveSignal(
        name="speed_359_u16le_b1_200",
        description="PQ35 vehicle speed duplicate/related broadcast",
        can_id=0x359,
        signal_expr="u16le1",
        signal_name="u16le[1:3]",
        unit="km/h",
        scale=1.0 / 200.0,
        default_truth_field="001.F3",
        status="confirmed",
        notes="Validated over 0..47 km/h: speed_kmh = u16le(bytes[1:3]) / 200. Treat as a duplicate/related speed broadcast until frame role is mapped.",
    ),
    "speed_351_b1_candidate": KnownPassiveSignal(
        name="speed_351_b1_candidate",
        description="Deprecated low-speed-only vehicle speed candidate",
        can_id=0x351,
        signal_expr="b1",
        signal_name="byte[1] u8",
        unit="km/h",
        scale=0.0213,
        default_truth_field="001.F3",
        status="deprecated-low-speed-artifact",
        notes="Looked plausible over 0..4 km/h, but wider 0..47 km/h validation showed the useful speed value is u16le[1:3]/200.",
    ),
}


def list_known_signal_lines() -> list[str]:
    lines = ["Known / seeded passive signals (PQ35 comfort/infotainment CAN, 100 kbit/s):"]
    for sig in sorted(KNOWN_PASSIVE_SIGNALS.values(), key=lambda item: item.name):
        unit = f" {sig.unit}" if sig.unit else ""
        lines.append(
            f"  {sig.name:<28} CAN 0x{sig.can_id:X} {sig.signal_name:<12} "
            f"truth={sig.default_truth_field or '-':<8} status={sig.status}{unit}"
        )
        lines.append(f"    {sig.description}")
        if sig.notes:
            lines.append(f"    notes: {sig.notes}")
    return lines


def resolve_known_signal(name: str | None) -> KnownPassiveSignal | None:
    if not name:
        return None
    key = name.strip().lower()
    try:
        return KNOWN_PASSIVE_SIGNALS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(KNOWN_PASSIVE_SIGNALS))
        raise ValueError(f"unknown --known-signal {name!r}; choices: {choices}") from exc


@dataclass(frozen=True)
class TruthPoint:
    t: float
    value: float


@dataclass(frozen=True)
class TruthField:
    key: str
    block: str
    field: str
    label: str
    unit: str
    kind: str
    samples: tuple[TruthPoint, ...]


@dataclass(frozen=True)
class CandidateResult:
    rank: int
    score: float
    correlation: float
    samples: int
    can_id: str
    signal: str
    expression: str
    slope_truth_per_raw: float
    intercept_truth: float
    rmse_truth: float
    raw_min: float
    raw_max: float
    truth_min: float
    truth_max: float
    first_pairs: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class CorrelationReport:
    truth_csv: str
    can_trace: str
    truth_key: str
    truth_label: str
    truth_unit: str
    truth_samples_total: int
    can_frames_total: int
    can_ids_considered: tuple[str, ...]
    skipped_diagnostic_ids: tuple[str, ...]
    offset_seconds: float
    window_seconds: float
    min_samples: int
    results: tuple[CandidateResult, ...]
    warnings: tuple[str, ...] = ()
    known_signal: str | None = None
    known_signal_truth_key: str | None = None
    auto_offset_applied: bool = False
    offset_sweep_results: tuple[KnownSignalOffsetResult, ...] = ()


def _clean_float_text(text: str) -> str:
    return (text or "").strip().strip("()")


def _parse_float(text: str) -> float | None:
    s = _clean_float_text(text)
    if not s:
        return None
    # Keep normal decimal/scientific notation; strip common display suffixes if
    # they accidentally leak into a CSV field.
    m = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_csv_time(text: str) -> float | None:
    s = (text or "").strip()
    if not s:
        return None
    f = _parse_float(s)
    # Plain numeric timestamps are accepted directly.  ISO datetimes also begin
    # with a year, so only use numeric parsing when the whole string is numeric.
    if f is not None and re.fullmatch(r"\(?[-+0-9.]+\)?", s):
        return f
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _field_key(block: str, field: str, label: str) -> str:
    block = (block or "").zfill(3)
    field_text = str(field or "").strip()
    prefix = f"{block}.F{field_text}" if field_text else block
    return f"{prefix} {label}".strip()


def load_truth_fields(path: str | Path) -> list[TruthField]:
    groups: dict[tuple[str, str, str, str, str], list[tuple[float, float]]] = {}
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        required = {"timestamp", "block", "field", "label", "decoded_value"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"truth CSV is missing columns: {', '.join(sorted(missing))}")

        for row in reader:
            t = _parse_csv_time(row.get("timestamp", ""))
            value = _parse_float(row.get("decoded_value", ""))
            if t is None or value is None:
                continue
            block = str(row.get("block", "")).zfill(3)
            field = str(row.get("field", "")).strip()
            label = str(row.get("label", "")).strip() or f"F{field}"
            unit = str(row.get("unit", "")).strip()
            kind = str(row.get("kind", "")).strip()
            groups.setdefault((block, field, label, unit, kind), []).append((t, value))

    fields: list[TruthField] = []
    for (block, field, label, unit, kind), samples in groups.items():
        if not samples:
            continue
        samples.sort(key=lambda x: x[0])
        t0 = samples[0][0]
        points = tuple(TruthPoint(t=t - t0, value=v) for t, v in samples)
        fields.append(TruthField(
            key=_field_key(block, field, label),
            block=block,
            field=field,
            label=label,
            unit=unit,
            kind=kind,
            samples=points,
        ))

    fields.sort(key=lambda item: (item.block, int(item.field or 0), item.label.lower()))
    return fields


def list_truth_field_lines(fields: Iterable[TruthField]) -> list[str]:
    lines = ["Available numeric truth fields:"]
    for item in fields:
        values = [p.value for p in item.samples]
        unit = f" {item.unit}" if item.unit else ""
        lines.append(
            f"  {item.key:<56} samples={len(item.samples):>4} "
            f"range={min(values):.3g}..{max(values):.3g}{unit}"
        )
    return lines


def resolve_truth_field(fields: list[TruthField], query: str | None) -> TruthField:
    if not fields:
        raise ValueError("truth CSV contains no numeric decoded_value samples")
    if not query:
        raise ValueError("choose a truth field with --truth-field, or run --list-truth-fields")

    q = query.strip().lower()
    exact = [f for f in fields if q in {f.key.lower(), f.label.lower(), f"{f.block}.{f.field}".lower(), f"{f.block}.f{f.field}".lower()}]
    if len(exact) == 1:
        return exact[0]

    contains = [f for f in fields if q in f.key.lower() or q in f.label.lower()]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        examples = "\n".join(f"  {f.key}" for f in contains[:12])
        raise ValueError(f"--truth-field matched multiple fields:\n{examples}")

    examples = "\n".join(f"  {f.key}" for f in fields[:16])
    raise ValueError(f"No truth field matched {query!r}. Examples:\n{examples}")


def _frame_time(frame: TraceFrame, fallback_index: int) -> float:
    if frame.timestamp is not None:
        parsed = _parse_float(frame.timestamp)
        if parsed is not None:
            return parsed
    # Last-resort ordering fallback.  It is not real time, but it lets users get
    # a rough shape from simple/timestamp-less toy traces and unit tests.
    return float(fallback_index)


def _normalise_frame_times(frames: list[TraceFrame]) -> list[tuple[float, TraceFrame]]:
    timed = [(_frame_time(frame, idx), frame) for idx, frame in enumerate(frames)]
    if not timed:
        return []
    t0 = timed[0][0]
    return [(t - t0, frame) for t, frame in timed]


def _parse_can_id_filter(text: str | None) -> set[int] | None:
    if not text:
        return None
    ids: set[int] = set()
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        ids.add(int(part, 16 if part.lower().startswith("0x") else 16))
    return ids


def _signal_values(data: bytes, include_bits: bool = False) -> list[tuple[str, str, float]]:
    values: list[tuple[str, str, float]] = []
    n = len(data)
    for i, b in enumerate(data):
        values.append((f"byte[{i}] u8", f"b{i}", float(b)))
        if include_bits:
            for bit in range(8):
                values.append((f"bit[{i}].{bit}", f"bit{ i }_{ bit }", float((b >> bit) & 1)))

    for i in range(max(0, n - 1)):
        be = (data[i] << 8) | data[i + 1]
        le = data[i] | (data[i + 1] << 8)
        sbe = be - 0x10000 if be & 0x8000 else be
        sle = le - 0x10000 if le & 0x8000 else le
        values.append((f"u16be[{i}:{i+2}]", f"u16be{i}", float(be)))
        values.append((f"u16le[{i}:{i+2}]", f"u16le{i}", float(le)))
        values.append((f"s16be[{i}:{i+2}]", f"s16be{i}", float(sbe)))
        values.append((f"s16le[{i}:{i+2}]", f"s16le{i}", float(sle)))
    return values


def _build_signal_series(
    timed_frames: list[tuple[float, TraceFrame]],
    include_bits: bool,
    include_diagnostic_ids: bool,
    can_id_filter: set[int] | None,
) -> tuple[dict[tuple[int, str], tuple[str, list[float], list[float]]], set[int], set[int]]:
    series: dict[tuple[int, str], tuple[str, list[float], list[float]]] = {}
    considered: set[int] = set()
    skipped_diag: set[int] = set()

    for t, frame in timed_frames:
        can_id = frame.can_id
        if can_id_filter is not None and can_id not in can_id_filter:
            continue
        if not include_diagnostic_ids and can_id in DEFAULT_DIAGNOSTIC_CAN_IDS:
            skipped_diag.add(can_id)
            continue
        considered.add(can_id)
        for name, short_name, value in _signal_values(frame.data, include_bits=include_bits):
            key = (can_id, short_name)
            if key not in series:
                series[key] = (name, [], [])
            _, times, values = series[key]
            times.append(t)
            values.append(value)

    return series, considered, skipped_diag


def _nearest_value(times: list[float], values: list[float], target: float, window: float) -> float | None:
    if not times:
        return None
    pos = bisect.bisect_left(times, target)
    best_i = None
    best_dt = None
    for i in (pos - 1, pos):
        if 0 <= i < len(times):
            dt = abs(times[i] - target)
            if best_dt is None or dt < best_dt:
                best_i = i
                best_dt = dt
    if best_i is None or best_dt is None or best_dt > window:
        return None
    return values[best_i]


def _pearson_and_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0.0, float("inf")
    xm = sum(xs) / n
    ym = sum(ys) / n
    dx = [x - xm for x in xs]
    dy = [y - ym for y in ys]
    vx = sum(d * d for d in dx)
    vy = sum(d * d for d in dy)
    if vx <= 1e-12 or vy <= 1e-12:
        return 0.0, 0.0, ym, float("inf")
    cov = sum(a * b for a, b in zip(dx, dy))
    corr = cov / math.sqrt(vx * vy)
    slope = cov / vx
    intercept = ym - slope * xm
    rmse = math.sqrt(sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)) / n)
    return corr, slope, intercept, rmse




def parse_offset_sweep(text: str | None) -> tuple[float, float, float]:
    if not text:
        return (-12.0, 12.0, 0.5)
    parts = [p for p in re.split(r"[:,]", text.strip()) if p]
    if len(parts) != 3:
        raise ValueError("--offset-sweep must be START:END:STEP, e.g. -12:12:0.5")
    start, end, step = (float(p) for p in parts)
    if step == 0:
        raise ValueError("--offset-sweep step must not be zero")
    if (end - start) * step < 0:
        raise ValueError("--offset-sweep step direction does not move from START to END")
    return start, end, step


def _offset_values(start: float, end: float, step: float) -> list[float]:
    values: list[float] = []
    cur = start
    # Small epsilon so decimal steps include the requested endpoint.
    if step > 0:
        while cur <= end + 1e-9:
            values.append(round(cur, 9))
            cur += step
    else:
        while cur >= end - 1e-9:
            values.append(round(cur, 9))
            cur += step
    return values


def _evaluate_known_signal_offset(
    truth: TruthField,
    signal: KnownPassiveSignal,
    series: dict[tuple[int, str], tuple[str, list[float], list[float]]],
    *,
    offset_seconds: float,
    window_seconds: float,
    min_samples: int,
) -> KnownSignalOffsetResult | None:
    key = (signal.can_id, signal.signal_expr)
    if key not in series:
        return None
    signal_name, times, values = series[key]
    xs: list[float] = []
    ys: list[float] = []
    for point in truth.samples:
        raw = _nearest_value(times, values, point.t - offset_seconds, window_seconds)
        if raw is None:
            continue
        xs.append(raw)
        ys.append(point.value)
    if len(xs) < min_samples or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    corr, slope, intercept, rmse = _pearson_and_fit(xs, ys)
    # Penalise offsets where the fit is numerically strong but direction is the
    # opposite of the known signal's expected positive scale.
    direction_ok = 1.0 if (signal.scale >= 0 and corr >= 0) or (signal.scale < 0 and corr <= 0) else 0.75
    coverage = len(xs) / max(1, len(truth.samples))
    score = abs(corr) * coverage * direction_ok
    return KnownSignalOffsetResult(
        offset_seconds=offset_seconds,
        score=score,
        correlation=corr,
        samples=len(xs),
        can_id=f"0x{signal.can_id:X}",
        signal=signal_name,
        expression=f"truth ≈ {slope:.8g}*raw + {intercept:.8g}",
        slope_truth_per_raw=slope,
        intercept_truth=intercept,
        rmse_truth=rmse,
        raw_min=min(xs),
        raw_max=max(xs),
        truth_min=min(ys),
        truth_max=max(ys),
    )


def find_known_signal_offset(
    truth_csv: str | Path,
    can_trace: str | Path,
    known_signal_name: str,
    *,
    truth_field_query: str | None = None,
    offset_sweep: str | None = None,
    window_seconds: float = 1.0,
    min_samples: int = 8,
    include_diagnostic_ids: bool = False,
) -> tuple[KnownPassiveSignal, TruthField, tuple[KnownSignalOffsetResult, ...]]:
    signal = resolve_known_signal(known_signal_name)
    if signal is None:
        raise ValueError("--known-signal is required for offset search")
    fields = load_truth_fields(truth_csv)
    truth = resolve_truth_field(fields, truth_field_query or signal.default_truth_field)
    frames = read_trace(can_trace)
    timed_frames = _normalise_frame_times(frames)
    series, _, _ = _build_signal_series(
        timed_frames,
        include_bits=False,
        include_diagnostic_ids=include_diagnostic_ids,
        can_id_filter={signal.can_id},
    )
    start, end, step = parse_offset_sweep(offset_sweep)
    results: list[KnownSignalOffsetResult] = []
    for off in _offset_values(start, end, step):
        result = _evaluate_known_signal_offset(
            truth,
            signal,
            series,
            offset_seconds=off,
            window_seconds=window_seconds,
            min_samples=min_samples,
        )
        if result is not None:
            results.append(result)
    results.sort(key=lambda r: (-r.score, -r.samples, r.rmse_truth, abs(r.offset_seconds)))
    return signal, truth, tuple(results)


def evaluate_known_signal_at_offset(
    truth_csv: str | Path,
    can_trace: str | Path,
    known_signal_name: str,
    *,
    truth_field_query: str | None = None,
    offset_seconds: float = 0.0,
    window_seconds: float = 1.0,
    min_samples: int = 8,
    include_diagnostic_ids: bool = False,
) -> tuple[KnownPassiveSignal, TruthField, KnownSignalOffsetResult | None]:
    """Evaluate one exact known signal at a fixed offset.

    This is used by the passive validation wizard/report where we already know
    the expected CAN ID and byte/u16 expression.  It avoids treating other
    fields in the same CAN frame as equivalent candidates.
    """
    signal = resolve_known_signal(known_signal_name)
    if signal is None:
        raise ValueError("known signal name is required")
    fields = load_truth_fields(truth_csv)
    truth = resolve_truth_field(fields, truth_field_query or signal.default_truth_field)
    frames = read_trace(can_trace)
    timed_frames = _normalise_frame_times(frames)
    series, _, _ = _build_signal_series(
        timed_frames,
        include_bits=False,
        include_diagnostic_ids=include_diagnostic_ids,
        can_id_filter={signal.can_id},
    )
    result = _evaluate_known_signal_offset(
        truth,
        signal,
        series,
        offset_seconds=offset_seconds,
        window_seconds=window_seconds,
        min_samples=min_samples,
    )
    return signal, truth, result


def correlate_truth_to_can(
    truth_csv: str | Path,
    can_trace: str | Path,
    truth_field_query: str,
    *,
    top: int = 20,
    min_samples: int = 8,
    window_seconds: float = 0.25,
    offset_seconds: float = 0.0,
    include_bits: bool = False,
    include_diagnostic_ids: bool = False,
    can_id_filter_text: str | None = None,
) -> CorrelationReport:
    fields = load_truth_fields(truth_csv)
    truth = resolve_truth_field(fields, truth_field_query)
    warnings: list[str] = []

    truth_values_all = [p.value for p in truth.samples]
    if len(set(round(v, 6) for v in truth_values_all)) < 2:
        warnings.append("Selected truth field did not vary; correlation needs a changing signal.")
    elif max(truth_values_all) - min(truth_values_all) < 5 and (truth.unit or "").lower() in {"km/h", "%"}:
        warnings.append("Selected truth field has a small range; use a wider deliberate change before treating candidates as proven.")

    frames = read_trace(can_trace)
    timed_frames = _normalise_frame_times(frames)
    can_filter = _parse_can_id_filter(can_id_filter_text)
    series, considered_ids, skipped_diag = _build_signal_series(
        timed_frames,
        include_bits=include_bits,
        include_diagnostic_ids=include_diagnostic_ids,
        can_id_filter=can_filter,
    )

    raw_results: list[tuple[float, int, str, str, float, float, float, float, float, float, float, float, list[tuple[float, float]]]] = []
    # tuple: score, can_id, signal_name, expr, corr, slope, intercept, rmse, raw_min, raw_max, truth_min, truth_max, first_pairs

    for (can_id, expr), (signal_name, times, values) in series.items():
        xs: list[float] = []
        ys: list[float] = []
        for point in truth.samples:
            # Positive offset moves the passive CAN timeline later relative to
            # the truth CSV: CAN sample time + offset ~= truth time.
            raw = _nearest_value(times, values, point.t - offset_seconds, window_seconds)
            if raw is None:
                continue
            xs.append(raw)
            ys.append(point.value)

        if len(xs) < min_samples:
            continue
        if len(set(xs)) < 2 or len(set(ys)) < 2:
            continue

        corr, slope, intercept, rmse = _pearson_and_fit(xs, ys)
        score = abs(corr) * min(1.0, len(xs) / max(1, min_samples))
        first_pairs = list(zip(xs[:8], ys[:8]))
        raw_results.append((
            score, can_id, signal_name, expr, corr, slope, intercept, rmse,
            min(xs), max(xs), min(ys), max(ys), first_pairs,
        ))

    raw_results.sort(key=lambda item: (-item[0], item[1], item[3]))
    results: list[CandidateResult] = []
    for rank, item in enumerate(raw_results[:max(0, top)], start=1):
        score, can_id, signal_name, expr, corr, slope, intercept, rmse, raw_min, raw_max, truth_min, truth_max, first_pairs = item
        results.append(CandidateResult(
            rank=rank,
            score=score,
            correlation=corr,
            samples=len(first_pairs) if False else sum(
                1 for point in truth.samples
                if _nearest_value(series[(can_id, expr)][1], series[(can_id, expr)][2], point.t - offset_seconds, window_seconds) is not None
            ),
            can_id=f"0x{can_id:X}",
            signal=signal_name,
            expression=f"truth ≈ {slope:.8g}*raw + {intercept:.8g}",
            slope_truth_per_raw=slope,
            intercept_truth=intercept,
            rmse_truth=rmse,
            raw_min=raw_min,
            raw_max=raw_max,
            truth_min=truth_min,
            truth_max=truth_max,
            first_pairs=tuple(first_pairs),
        ))

    if not results:
        warnings.append("No candidates met the thresholds. Try more movement/change, a larger --window, or --offset adjustment.")
    elif abs(results[0].correlation) < 0.75:
        warnings.append("Top candidate correlation is below 0.75; treat this as weak/noisy until timing and capture range are improved.")
    if not any(frame.timestamp for frame in frames):
        warnings.append("CAN trace had no timestamps; line-order fallback was used and timing correlation will be weak.")

    return CorrelationReport(
        truth_csv=str(truth_csv),
        can_trace=str(can_trace),
        truth_key=truth.key,
        truth_label=truth.label,
        truth_unit=truth.unit,
        truth_samples_total=len(truth.samples),
        can_frames_total=len(frames),
        can_ids_considered=tuple(f"0x{x:X}" for x in sorted(considered_ids)),
        skipped_diagnostic_ids=tuple(f"0x{x:X}" for x in sorted(skipped_diag)),
        offset_seconds=offset_seconds,
        window_seconds=window_seconds,
        min_samples=min_samples,
        results=tuple(results),
        warnings=tuple(warnings),
    )


def report_to_dict(report: CorrelationReport) -> dict[str, Any]:
    data = asdict(report)
    return data


def write_report_json(path: str | Path, report: CorrelationReport) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_to_dict(report), f, indent=2)
        f.write("\n")


def report_markdown_lines(report: CorrelationReport) -> list[str]:
    unit = f" ({report.truth_unit})" if report.truth_unit else ""
    lines = [
        "# Passive CAN correlation report",
        "",
        f"Truth CSV: `{report.truth_csv}`",
        f"Passive CAN trace: `{report.can_trace}`",
        f"Truth field: `{report.truth_key}`{unit}",
        f"Truth samples: {report.truth_samples_total}",
        f"CAN frames parsed: {report.can_frames_total}",
        f"Timing: window ±{report.window_seconds:.3f}s, offset {report.offset_seconds:+.3f}s, minimum samples {report.min_samples}",
        "",
    ]
    if report.skipped_diagnostic_ids:
        lines.append(f"Skipped diagnostic CAN IDs: {', '.join(report.skipped_diagnostic_ids)}")
        lines.append("")
    if report.known_signal and report.offset_sweep_results:
        lines.append("## Timing alignment")
        lines.append("")
        lines.append(f"Known signal: `{report.known_signal}`")
        if report.known_signal_truth_key:
            lines.append(f"Alignment truth field: `{report.known_signal_truth_key}`")
        lines.append(f"Auto-offset applied: {'yes' if report.auto_offset_applied else 'no'}")
        lines.append("")
        lines.append("| Rank | Offset | Score | Corr | Samples | CAN ID | Signal | Fit | Raw range | RMSE |")
        lines.append("|---:|---:|---:|---:|---:|---|---|---|---|---:|")
        for idx, r in enumerate(report.offset_sweep_results[:10], start=1):
            lines.append(
                f"| {idx} | {r.offset_seconds:+.3f}s | {r.score:.3f} | {r.correlation:+.3f} | {r.samples} | "
                f"`{r.can_id}` | `{r.signal}` | `{r.expression}` | {r.raw_min:.3g}..{r.raw_max:.3g} | {r.rmse_truth:.3g} |"
            )
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lines.extend([
        "## Top candidates",
        "",
        "| Rank | Score | Corr | Samples | CAN ID | Signal | Fit | Raw range | RMSE |",
        "|---:|---:|---:|---:|---|---|---|---|---:|",
    ])
    for r in report.results:
        lines.append(
            f"| {r.rank} | {r.score:.3f} | {r.correlation:+.3f} | {r.samples} | "
            f"`{r.can_id}` | `{r.signal}` | `{r.expression}` | "
            f"{r.raw_min:.3g}..{r.raw_max:.3g} | {r.rmse_truth:.3g} |"
        )
    if not report.results:
        lines.append("| — | — | — | — | — | — | No candidates met thresholds | — | — |")
    lines.extend([
        "",
        "## Notes",
        "",
        "This is a candidate finder, not proof. Validate a candidate with another drive pattern, different speeds/states, and a narrow filtered capture before using it in Open MMI.",
        "Diagnostic request/response IDs are skipped by default so the tool does not rediscover its own active KWP measuring-block traffic.",
    ])
    return lines


def write_report_markdown(path: str | Path, report: CorrelationReport) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_markdown_lines(report)))
        f.write("\n")

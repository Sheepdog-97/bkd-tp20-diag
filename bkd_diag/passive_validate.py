from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .correlate import (
    KnownSignalOffsetResult,
    evaluate_known_signal_at_offset,
    find_known_signal_offset,
)
from .reporting import Reporter


@dataclass(frozen=True)
class PassiveValidationCheck:
    name: str
    role: str
    known_signal: str
    truth_field: str
    threshold_corr: float = 0.95
    threshold_rmse: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class PassiveValidationItem:
    name: str
    role: str
    known_signal: str
    truth_field: str
    status: str
    can_id: str | None
    signal: str | None
    correlation: float | None
    samples: int
    expression: str | None
    raw_min: float | None
    raw_max: float | None
    truth_min: float | None
    truth_max: float | None
    rmse_truth: float | None
    notes: str


@dataclass(frozen=True)
class PassiveValidationReport:
    profile: str
    profile_label: str
    bus_name: str
    bus_description: str
    bus_bitrate: int
    truth_csv: str
    can_trace: str
    generated: str
    offset_seconds: float
    offset_source: str
    window_seconds: float
    min_samples: int
    alignment_known_signal: str
    alignment_truth_field: str
    alignment_correlation: float | None
    alignment_rmse: float | None
    alignment_score: float | None
    checks: tuple[PassiveValidationItem, ...]
    warnings: tuple[str, ...]


PQ35_INFOTAINMENT_CHECKS: tuple[PassiveValidationCheck, ...] = (
    PassiveValidationCheck(
        name="dimmer_470_b2",
        role="Dimmer / Terminal 58d percentage",
        known_signal="dimmer_470_b2",
        truth_field="008.F3",
        threshold_corr=0.95,
        threshold_rmse=3.0,
        notes="Confirmed timing anchor; raw should closely equal percent.",
    ),
    PassiveValidationCheck(
        name="blower_3e1_b4",
        role="HVAC blower / turbine load percentage",
        known_signal="blower_3e1_b4",
        truth_field="007.F3",
        threshold_corr=0.95,
        threshold_rmse=5.0,
        notes="Expected scale is approximately raw * 100 / 255.",
    ),
    PassiveValidationCheck(
        name="speed_351_u16le_b1_200",
        role="Vehicle speed from 0x351",
        known_signal="speed_351_u16le_b1_200",
        truth_field="001.F3",
        threshold_corr=0.95,
        threshold_rmse=3.0,
        notes="Expected scale is u16le(bytes[1:3]) / 200 km/h.",
    ),
    PassiveValidationCheck(
        name="speed_527_u16le_b1_200",
        role="Vehicle speed from 0x527",
        known_signal="speed_527_u16le_b1_200",
        truth_field="001.F3",
        threshold_corr=0.95,
        threshold_rmse=3.0,
        notes="Expected scale is u16le(bytes[1:3]) / 200 km/h.",
    ),
    PassiveValidationCheck(
        name="speed_359_u16le_b1_200",
        role="Vehicle speed from 0x359",
        known_signal="speed_359_u16le_b1_200",
        truth_field="001.F3",
        threshold_corr=0.95,
        threshold_rmse=3.0,
        notes="Expected scale is u16le(bytes[1:3]) / 200 km/h.",
    ),
)


PROFILE_CHECKS: dict[str, tuple[PassiveValidationCheck, ...]] = {
    "pq35-infotainment": PQ35_INFOTAINMENT_CHECKS,
}

PROFILE_METADATA: dict[str, dict[str, object]] = {
    "pq35-infotainment": {
        "label": "PQ35 comfort/infotainment",
        "bus_name": "comfort",
        "bus_description": "PQ35 comfort/infotainment CAN used by the Open MMI tablet",
        "bus_bitrate": 100000,
    },
}


TRUTH_PATTERNS = ("logs/*_live.csv",)
CAN_PATTERNS = (
    "captures/comfort_validation_*.log",
    "captures/comfort_passive_*.log",
    "captures/infotainment_validation_*.log",
    "captures/infotainment_passive_*.log",
    "captures/passive_*.log",
    "captures/*.log",
)


def _latest_file(patterns: Iterable[str]) -> Path | None:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(Path().glob(pattern))
    files = [p for p in matches if p.is_file()]
    if not files:
        return None
    # Deduplicate while preserving real latest by mtime.
    unique = {p.resolve(): p for p in files}
    return max(unique.values(), key=lambda p: p.stat().st_mtime)


def resolve_input_path(kind: str, value: str | None) -> Path:
    text = (value or "latest").strip()
    if text.lower() == "latest":
        path = _latest_file(TRUTH_PATTERNS if kind == "truth" else CAN_PATTERNS)
        if path is None:
            patterns = ", ".join(TRUTH_PATTERNS if kind == "truth" else CAN_PATTERNS)
            raise FileNotFoundError(f"no {kind} file found for latest; tried {patterns}")
        return path
    path = Path(text)
    if not path.exists():
        raise FileNotFoundError(f"{kind} file not found: {path}")
    return path


def default_report_paths(profile: str, can_trace: Path) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    can_stem = can_trace.stem.replace(" ", "_")
    out_dir = Path("captures")
    out_dir.mkdir(exist_ok=True)
    base = out_dir / f"passive_validation_{profile}_{can_stem}_{stamp}"
    return base.with_suffix(".md"), base.with_suffix(".json")


def _status_for_result(result: KnownSignalOffsetResult | None, check: PassiveValidationCheck) -> str:
    if result is None:
        return "FAIL"
    corr_ok = result.correlation >= check.threshold_corr
    rmse_ok = True if check.threshold_rmse is None else result.rmse_truth <= check.threshold_rmse
    if corr_ok and rmse_ok:
        return "PASS"
    if result.correlation >= 0.85:
        return "WARN"
    return "FAIL"


def _item_from_result(check: PassiveValidationCheck, result: KnownSignalOffsetResult | None) -> PassiveValidationItem:
    status = _status_for_result(result, check)
    if result is None:
        return PassiveValidationItem(
            name=check.name,
            role=check.role,
            known_signal=check.known_signal,
            truth_field=check.truth_field,
            status=status,
            can_id=None,
            signal=None,
            correlation=None,
            samples=0,
            expression=None,
            raw_min=None,
            raw_max=None,
            truth_min=None,
            truth_max=None,
            rmse_truth=None,
            notes=check.notes,
        )
    return PassiveValidationItem(
        name=check.name,
        role=check.role,
        known_signal=check.known_signal,
        truth_field=check.truth_field,
        status=status,
        can_id=result.can_id,
        signal=result.signal,
        correlation=result.correlation,
        samples=result.samples,
        expression=result.expression,
        raw_min=result.raw_min,
        raw_max=result.raw_max,
        truth_min=result.truth_min,
        truth_max=result.truth_max,
        rmse_truth=result.rmse_truth,
        notes=check.notes,
    )


def build_passive_validation_report(
    *,
    truth_csv: str | Path,
    can_trace: str | Path,
    profile: str = "pq35-infotainment",
    auto_offset: bool = True,
    offset_seconds: float | None = None,
    offset_sweep: str | None = None,
    window_seconds: float = 1.0,
    min_samples: int = 8,
) -> PassiveValidationReport:
    profile_key = profile.strip().lower()
    if profile_key not in PROFILE_CHECKS:
        choices = ", ".join(sorted(PROFILE_CHECKS))
        raise ValueError(f"unknown passive validation profile {profile!r}; choices: {choices}")

    truth_path = resolve_input_path("truth", str(truth_csv))
    can_path = resolve_input_path("can", str(can_trace))
    checks = PROFILE_CHECKS[profile_key]
    alignment_check = checks[0]

    warnings: list[str] = []
    alignment_result: KnownSignalOffsetResult | None = None
    alignment_truth_key = alignment_check.truth_field
    offset_source = "manual"

    if auto_offset:
        signal, align_truth, sweep = find_known_signal_offset(
            truth_path,
            can_path,
            alignment_check.known_signal,
            truth_field_query=alignment_check.truth_field,
            offset_sweep=offset_sweep,
            window_seconds=window_seconds,
            min_samples=min_samples,
        )
        alignment_truth_key = align_truth.key
        if not sweep:
            warnings.append("No usable auto-offset found from dimmer anchor; using supplied/manual offset or 0.0s.")
            offset = float(offset_seconds or 0.0)
        else:
            alignment_result = sweep[0]
            offset = alignment_result.offset_seconds
            offset_source = f"auto:{signal.name}"
    else:
        offset = float(offset_seconds or 0.0)

    items: list[PassiveValidationItem] = []
    for check in checks:
        _, _, result = evaluate_known_signal_at_offset(
            truth_path,
            can_path,
            check.known_signal,
            truth_field_query=check.truth_field,
            offset_seconds=offset,
            window_seconds=window_seconds,
            min_samples=min_samples,
        )
        items.append(_item_from_result(check, result))
        if check == alignment_check and result is not None:
            alignment_result = result
            alignment_truth_key = check.truth_field

    if any(item.status == "FAIL" for item in items):
        warnings.append("At least one validation check failed; keep failed signals out of Open MMI runtime.")
    if any(item.status == "WARN" for item in items):
        warnings.append("At least one validation check is only WARN; repeat with a clearer deliberate state-change pattern.")

    return PassiveValidationReport(
        profile=profile_key,
        profile_label=str(PROFILE_METADATA.get(profile, {}).get("label", profile)),
        bus_name=str(PROFILE_METADATA.get(profile, {}).get("bus_name", "unknown")),
        bus_description=str(PROFILE_METADATA.get(profile, {}).get("bus_description", "unknown")),
        bus_bitrate=int(PROFILE_METADATA.get(profile, {}).get("bus_bitrate", 0)),
        truth_csv=str(truth_path),
        can_trace=str(can_path),
        generated=datetime.now().isoformat(timespec="seconds"),
        offset_seconds=offset,
        offset_source=offset_source,
        window_seconds=window_seconds,
        min_samples=min_samples,
        alignment_known_signal=alignment_check.known_signal,
        alignment_truth_field=alignment_truth_key,
        alignment_correlation=alignment_result.correlation if alignment_result else None,
        alignment_rmse=alignment_result.rmse_truth if alignment_result else None,
        alignment_score=alignment_result.score if alignment_result else None,
        checks=tuple(items),
        warnings=tuple(warnings),
    )


def validation_markdown_lines(report: PassiveValidationReport) -> list[str]:
    lines = [
        "# Passive CAN validation report",
        "",
        f"Generated: `{report.generated}`",
        f"Profile: `{report.profile}` ({report.profile_label})",
        f"Bus: `{report.bus_name}` — {report.bus_description}, `{report.bus_bitrate}` bit/s passive/listen-only",
        f"Truth CSV: `{report.truth_csv}`",
        f"Passive CAN trace: `{report.can_trace}`",
        "",
        "## Timing alignment",
        "",
        f"Known anchor: `{report.alignment_known_signal}`",
        f"Alignment truth: `{report.alignment_truth_field}`",
        f"Offset: `{report.offset_seconds:+.3f}s` ({report.offset_source})",
        f"Window: `±{report.window_seconds:.3f}s`",
    ]
    if report.alignment_correlation is not None:
        lines.append(f"Correlation: `{report.alignment_correlation:+.3f}`")
    if report.alignment_rmse is not None:
        lines.append(f"RMSE: `{report.alignment_rmse:.3g}`")
    lines.extend([
        "",
        "## Checks",
        "",
        "| Status | Signal | Role | CAN | Raw signal | Truth field | Corr | RMSE | Raw range | Fit |",
        "|---|---|---|---|---|---|---:|---:|---|---|",
    ])
    for item in report.checks:
        corr = "—" if item.correlation is None else f"{item.correlation:+.3f}"
        rmse = "—" if item.rmse_truth is None else f"{item.rmse_truth:.3g}"
        raw_range = "—" if item.raw_min is None else f"{item.raw_min:.3g}..{item.raw_max:.3g}"
        lines.append(
            f"| {item.status} | `{item.known_signal}` | {item.role} | `{item.can_id or '—'}` | "
            f"`{item.signal or '—'}` | `{item.truth_field}` | {corr} | {rmse} | {raw_range} | `{item.expression or '—'}` |"
        )
    if report.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend([
        "",
        "## Safety",
        "",
        "This report is for passive decoding only. Do not transmit, replay, spoof, code, adapt, run output tests, or clear DTCs from Open MMI runtime.",
    ])
    return lines


def write_validation_markdown(path: str | Path, report: PassiveValidationReport) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(validation_markdown_lines(report)) + "\n", encoding="utf-8")


def write_validation_json(path: str | Path, report: PassiveValidationReport) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")


def print_validation_summary(reporter: Reporter, report: PassiveValidationReport) -> None:
    c = reporter.colour
    reporter.header("Passive validation summary")
    reporter.info(f"Profile: {report.profile} ({report.profile_label})")
    reporter.info(f"Bus: {report.bus_name} / {report.bus_bitrate} bit/s passive")
    reporter.info(f"Truth CSV: {report.truth_csv}")
    reporter.info(f"Passive CAN: {report.can_trace}")
    align = f"offset {report.offset_seconds:+.3f}s via {report.offset_source}"
    if report.alignment_correlation is not None:
        align += f"  corr={report.alignment_correlation:+.3f}"
    reporter.ok(align)
    reporter.line("")
    reporter.line(f"{'status':<6}  {'signal':<30}  {'CAN':<6}  {'raw':<14}  {'corr':>7}  {'rmse':>7}  role")
    for item in report.checks:
        colour = c.green if item.status == "PASS" else c.yellow if item.status == "WARN" else c.red
        corr = "—" if item.correlation is None else f"{item.correlation:+.3f}"
        rmse = "—" if item.rmse_truth is None else f"{item.rmse_truth:.3g}"
        reporter.line(
            f"{colour(item.status):<6}  {item.known_signal:<30}  {(item.can_id or '—'):<6}  "
            f"{(item.signal or '—'):<14}  {corr:>7}  {rmse:>7}  {item.role}"
        )
    for warning in report.warnings:
        reporter.warn(warning)


def run_passive_validate(
    reporter: Reporter,
    *,
    truth_csv: str = "latest",
    can_trace: str = "latest",
    profile: str = "pq35-infotainment",
    auto_offset: bool = True,
    offset_seconds: float | None = None,
    offset_sweep: str | None = None,
    window_seconds: float = 1.0,
    min_samples: int = 8,
    md_out: str | None = None,
    json_out: str | None = None,
    write_reports: bool = True,
) -> PassiveValidationReport:
    reporter.header("Passive CAN validation")
    reporter.warn("Offline/passive analysis only. Results validate signals; they do not authorise transmit/replay/control.")
    report = build_passive_validation_report(
        truth_csv=truth_csv,
        can_trace=can_trace,
        profile=profile,
        auto_offset=auto_offset,
        offset_seconds=offset_seconds,
        offset_sweep=offset_sweep,
        window_seconds=window_seconds,
        min_samples=min_samples,
    )
    print_validation_summary(reporter, report)

    if write_reports:
        if not md_out or not json_out:
            default_md, default_json = default_report_paths(report.profile, Path(report.can_trace))
            md_out = md_out or str(default_md)
            json_out = json_out or str(default_json)
        write_validation_markdown(md_out, report)
        reporter.ok(f"Markdown validation report written: {md_out}")
        write_validation_json(json_out, report)
        reporter.ok(f"JSON validation report written: {json_out}")
    return report

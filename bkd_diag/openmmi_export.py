from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .passive_validate import PROFILE_METADATA
from .reporting import Reporter

VALIDATION_PATTERNS = (
    "captures/passive_validation_*.json",
    "captures/*validation*.json",
)

SEED_PATH = Path("data/passive_signals_pq35_seed.json")

SAFETY_TEXT = (
    "Passive receive/decode configuration only. Do not transmit, spoof, replay, "
    "clear DTCs, code, adapt, run output tests, or perform vehicle control from "
    "the Open MMI runtime."
)


@dataclass(frozen=True)
class ExportSignal:
    name: str
    path: str
    role: str
    can_id: str
    raw: str
    decoder: dict[str, Any]
    status: str
    validation: dict[str, Any]
    notes: str = ""
    alias_of: str | None = None


# Open MMI-facing signal names.  The bridge intentionally exports a small,
# conservative overlay rather than trying to rewrite Open MMI profiles in-place.
OPENMMI_PATHS: dict[str, tuple[str, str, str | None]] = {
    "dimmer_470_b2": ("lighting.dimmer_percent", "Dimmer / Terminal 58d percentage", None),
    "blower_3e1_b4": ("climate.blower_load_percent", "HVAC blower / turbine load percentage", None),
    "speed_351_u16le_b1_200": ("vehicle.speed_kmh", "Vehicle speed primary", None),
    "speed_527_u16le_b1_200": ("vehicle.speed_kmh_from_527", "Vehicle speed duplicate/cross-check", "vehicle.speed_kmh"),
    "speed_359_u16le_b1_200": ("vehicle.speed_kmh_from_359", "Vehicle speed duplicate/cross-check", "vehicle.speed_kmh"),
}

PRIMARY_EXPORT_SIGNALS = (
    "dimmer_470_b2",
    "blower_3e1_b4",
    "speed_351_u16le_b1_200",
)

DUPLICATE_SPEED_SIGNALS = (
    "speed_527_u16le_b1_200",
    "speed_359_u16le_b1_200",
)


def _latest_file(patterns: Iterable[str]) -> Path | None:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(Path().glob(pattern))
    files = [p for p in matches if p.is_file()]
    if not files:
        return None
    unique = {p.resolve(): p for p in files}
    return max(unique.values(), key=lambda p: p.stat().st_mtime)


def resolve_validation_path(value: str | None) -> Path:
    text = (value or "latest").strip()
    if text.lower() == "latest":
        latest = _latest_file(VALIDATION_PATTERNS)
        if latest is None:
            raise FileNotFoundError("no passive validation JSON report found under captures/")
        return latest
    path = Path(text)
    if not path.exists():
        raise FileNotFoundError(f"validation report not found: {path}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _profile_metadata(profile: str) -> dict[str, Any]:
    meta = PROFILE_METADATA.get(profile, {})
    return {
        "profile_label": str(meta.get("label", profile)),
        "bus_name": str(meta.get("bus_name", "comfort")),
        "bus_description": str(meta.get("bus_description", "PQ35 comfort/infotainment CAN")),
        "bus_bitrate": int(meta.get("bus_bitrate", 100000)),
    }


def _normalise_validation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Back-fill fields missing from older v0.8.x validation reports.

    v0.8.4 added bus metadata to validation reports.  Older reports are still
    perfectly usable for Open MMI export as long as their profile is known, so
    infer the conservative PQ35 comfort/100 kbit/s defaults instead of failing.
    """
    profile = str(report.get("profile") or "pq35-infotainment")
    meta = _profile_metadata(profile)
    out = dict(report)
    for key, value in meta.items():
        out.setdefault(key, value)
    out.setdefault("truth_csv", report.get("truth") or report.get("truth_path") or "unknown")
    out.setdefault("can_trace", report.get("can") or report.get("can_path") or "unknown")
    out.setdefault("generated", report.get("timestamp") or "unknown")
    out.setdefault("offset_seconds", report.get("offset") or 0.0)
    out.setdefault("checks", report.get("items") or report.get("results") or [])
    return out


def _load_seed_signals(path: Path = SEED_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = _load_json(path)
    signals = data.get("signals", [])
    by_name: dict[str, dict[str, Any]] = {}
    if isinstance(signals, list):
        for item in signals:
            if isinstance(item, dict) and item.get("name"):
                by_name[str(item["name"])] = item
    return by_name


def _check_by_signal(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = report.get("checks", [])
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(checks, list):
        return out
    for item in checks:
        if not isinstance(item, dict):
            continue
        name = str(item.get("known_signal") or item.get("name") or "")
        if name:
            out[name] = item
    return out


def _decoder_from_seed(name: str, seed: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    typ = str(seed.get("type") or "")
    can_id = str(seed.get("can_id") or "")
    unit = str(seed.get("unit") or "")
    formula = str(seed.get("formula") or "")

    if typ == "u8" and "byte" in seed:
        byte = int(seed["byte"])
        scale = 1.0
        if name == "blower_3e1_b4" or "100 / 255" in formula or "100/255" in formula:
            scale = 100.0 / 255.0
        return f"byte[{byte}] u8", {
            "type": "u8",
            "byte": byte,
            "scale": scale,
            "offset": 0.0,
            "unit": unit,
            "formula": formula or f"value = raw * {scale:g}",
        }

    if typ == "u16le" and "bytes" in seed:
        bytes_ = list(seed.get("bytes") or [])
        if len(bytes_) >= 2:
            start = int(bytes_[0])
            end = int(bytes_[1]) + 1
        else:
            start, end = 1, 3
        scale = 1.0 / 200.0 if "/ 200" in formula or name.startswith("speed_") else 1.0
        return f"u16le[{start}:{end}]", {
            "type": "u16le",
            "start_byte": start,
            "end_byte_exclusive": end,
            "scale": scale,
            "offset": 0.0,
            "unit": unit,
            "formula": formula or f"value = u16le(bytes[{start}:{end}]) * {scale:g}",
        }

    # Fallback keeps the data visible without claiming a runtime-ready decoder.
    return str(seed.get("type") or "unknown"), {
        "type": typ or "unknown",
        "unit": unit,
        "formula": formula,
        "manual_review_required": True,
    }


def _validation_blob(check: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": check.get("status") or seed.get("status"),
        "correlation": check.get("correlation"),
        "rmse_truth": check.get("rmse_truth"),
        "samples": check.get("samples"),
        "truth_field": check.get("truth_field") or seed.get("truth_field"),
        "raw_min": check.get("raw_min"),
        "raw_max": check.get("raw_max"),
        "source_validation_text": seed.get("validation"),
    }


def _export_signal(name: str, check: dict[str, Any], seed: dict[str, Any]) -> ExportSignal:
    if name not in OPENMMI_PATHS:
        raise KeyError(name)
    path, role, alias_of = OPENMMI_PATHS[name]
    raw, decoder = _decoder_from_seed(name, seed)
    can_id = str(seed.get("can_id") or check.get("can_id") or "")
    return ExportSignal(
        name=name,
        path=path,
        role=role,
        can_id=can_id,
        raw=raw,
        decoder=decoder,
        status=str(check.get("status") or seed.get("status") or "unknown"),
        validation=_validation_blob(check, seed),
        notes=str(seed.get("notes") or ""),
        alias_of=alias_of,
    )


def build_openmmi_export(
    *,
    validation_report: str | Path = "latest",
    include_speed_duplicates: bool = False,
    vehicle_profile: str = "seat_1p",
) -> tuple[Path, dict[str, Any], list[str]]:
    validation_path = resolve_validation_path(str(validation_report))
    raw_report = _load_json(validation_path)
    report = _normalise_validation_report(raw_report)
    seeds = _load_seed_signals()
    checks = _check_by_signal(report)

    wanted = list(PRIMARY_EXPORT_SIGNALS)
    if include_speed_duplicates:
        wanted.extend(DUPLICATE_SPEED_SIGNALS)

    warnings: list[str] = []
    exported: list[ExportSignal] = []
    for name in wanted:
        seed = seeds.get(name, {})
        check = checks.get(name, {})
        status = str(check.get("status") or seed.get("status") or "").upper()
        if status != "PASS" and str(seed.get("status")) != "confirmed":
            warnings.append(f"{name}: not exported as confirmed/PASS; status={status or seed.get('status')}")
            continue
        if not seed:
            warnings.append(f"{name}: seed metadata missing; exported from validation only with manual review")
        try:
            exported.append(_export_signal(name, check, seed))
        except KeyError:
            warnings.append(f"{name}: no Open MMI path mapping yet")

    bus_name = str(report.get("bus_name") or "comfort")
    bus_bitrate = int(report.get("bus_bitrate") or 100000)
    profile_label = str(report.get("profile_label") or report.get("profile") or "pq35-infotainment")

    overlay = {
        "schema": "bkd_diag.openmmi_profile_overlay.v1",
        "generated_by": f"bkd_diag {__version__} openmmi-export",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "vehicle_profile": vehicle_profile,
        "validation_report": str(validation_path),
        "validation": {
            "profile": report.get("profile", "pq35-infotainment"),
            "profile_label": profile_label,
            "truth_csv": report.get("truth_csv"),
            "can_trace": report.get("can_trace"),
            "offset_seconds": report.get("offset_seconds"),
            "alignment_known_signal": report.get("alignment_known_signal", "dimmer_470_b2"),
            "alignment_correlation": report.get("alignment_correlation"),
        },
        "safety": SAFETY_TEXT,
        "can_buses": {
            bus_name: {
                "interface": "can0",
                "bitrate": bus_bitrate,
                "mode": "listen-only recommended",
                "description": report.get("bus_description") or "PQ35 comfort/infotainment CAN",
            }
        },
        "status_signals": [
            {
                "name": sig.name,
                "path": sig.path,
                "role": sig.role,
                "bus": bus_name,
                "can_id": sig.can_id,
                "raw": sig.raw,
                "decoder": sig.decoder,
                "validation": sig.validation,
                "status": sig.status,
                **({"alias_of": sig.alias_of} if sig.alias_of else {}),
                **({"notes": sig.notes} if sig.notes else {}),
            }
            for sig in exported
        ],
        "warnings": warnings,
    }
    return validation_path, overlay, warnings


def _markdown_for_overlay(overlay: dict[str, Any]) -> str:
    lines = [
        "# Open MMI passive profile overlay",
        "",
        f"Generated by: `{overlay['generated_by']}`",
        f"Vehicle profile: `{overlay['vehicle_profile']}`",
        f"Validation report: `{overlay['validation_report']}`",
        "",
        "## Safety",
        "",
        overlay["safety"],
        "",
        "## Bus",
        "",
    ]
    for name, bus in overlay.get("can_buses", {}).items():
        lines.append(f"- `{name}`: `{bus.get('interface')}` at `{bus.get('bitrate')}` bit/s ({bus.get('mode')})")
    lines.extend([
        "",
        "## Signals",
        "",
        "| Path | CAN | Raw | Decoder | Role | Status | Corr | RMSE |",
        "|---|---:|---|---|---|---|---:|---:|",
    ])
    for sig in overlay.get("status_signals", []):
        dec = sig.get("decoder", {})
        validation = sig.get("validation", {})
        corr = validation.get("correlation")
        rmse = validation.get("rmse_truth")
        corr_s = "—" if corr is None else f"{float(corr):+.3f}"
        rmse_s = "—" if rmse is None else f"{float(rmse):.3g}"
        formula = dec.get("formula") or f"{dec.get('type')} scale={dec.get('scale')}"
        lines.append(
            f"| `{sig.get('path')}` | `{sig.get('can_id')}` | `{sig.get('raw')}` | `{formula}` | "
            f"{sig.get('role')} | {sig.get('status')} | {corr_s} | {rmse_s} |"
        )
    if overlay.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {w}" for w in overlay["warnings"])
    lines.extend([
        "",
        "## How to use",
        "",
        "This file is an overlay/export artifact. Review it before copying values into an Open MMI vehicle profile. "
        "It is passive receive/decode data only, not runtime CAN transmit configuration.",
    ])
    return "\n".join(lines) + "\n"


def write_openmmi_export(
    *,
    validation_report: str | Path = "latest",
    out_dir: str | Path = "exports/openmmi",
    include_speed_duplicates: bool = False,
    vehicle_profile: str = "seat_1p",
) -> dict[str, Path]:
    validation_path, overlay, _warnings = build_openmmi_export(
        validation_report=validation_report,
        include_speed_duplicates=include_speed_duplicates,
        vehicle_profile=vehicle_profile,
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"openmmi_{vehicle_profile}_{overlay['validation'].get('profile', 'pq35')}_overlay"
    json_path = out / f"{stem}.json"
    md_path = out / f"{stem}.md"
    signals_path = out / f"{stem}_signals.json"
    readme_path = out / "README.md"

    json_path.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")
    signals_path.write_text(json.dumps(overlay.get("status_signals", []), indent=2) + "\n", encoding="utf-8")
    md = _markdown_for_overlay(overlay)
    md_path.write_text(md, encoding="utf-8")
    readme_path.write_text(md, encoding="utf-8")
    return {
        "validation": validation_path,
        "overlay_json": json_path,
        "signals_json": signals_path,
        "markdown": md_path,
        "readme": readme_path,
    }


def run_openmmi_export(
    reporter: Reporter,
    *,
    validation_report: str = "latest",
    out_dir: str = "exports/openmmi",
    include_speed_duplicates: bool = False,
    vehicle_profile: str = "seat_1p",
) -> None:
    reporter.header("Open MMI export bridge")
    reporter.warn("Offline export only. The generated Open MMI material is passive receive/decode configuration, not CAN transmit/control.")
    paths = write_openmmi_export(
        validation_report=validation_report,
        out_dir=out_dir,
        include_speed_duplicates=include_speed_duplicates,
        vehicle_profile=vehicle_profile,
    )
    overlay = _load_json(paths["overlay_json"])
    reporter.info(f"Validation: {paths['validation']}")
    buses = overlay.get("can_buses", {})
    for name, bus in buses.items():
        reporter.info(f"Bus: {name} / {bus.get('bitrate')} bit/s / {bus.get('interface')} ({bus.get('mode')})")
    reporter.line("")
    reporter.line(f"{'path':<32}  {'CAN':<6}  {'raw':<14}  decoder")
    for sig in overlay.get("status_signals", []):
        dec = sig.get("decoder", {})
        reporter.line(
            f"{sig.get('path',''):<32}  {sig.get('can_id',''):<6}  {sig.get('raw',''):<14}  {dec.get('formula') or dec.get('type')}"
        )
    for warning in overlay.get("warnings", []):
        reporter.warn(str(warning))
    reporter.ok(f"Open MMI overlay written: {paths['overlay_json']}")
    reporter.ok(f"Signals JSON written: {paths['signals_json']}")
    reporter.ok(f"Markdown notes written: {paths['markdown']}")

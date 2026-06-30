from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .dtc import DtcDatabase, status_bit_text
from .module_probe import module_open_kwargs, module_session, run_module_dtc
from .reporting import Reporter
from .tp20 import TP20KWP
from .vehicle_profile import ModuleProfile, find_module
from .utils import fmt
from .engine_profiles import read_engine_dtcs_with_profile

PROVEN_AUTOSCAN_MODULES = ["01", "03", "08", "17", "19", "44", "46"]

@dataclass
class DtcRecord:
    vag_decimal: int
    raw_hex: str
    raw_record: str
    status: int
    status_hex: str
    status_bits: list[str]
    pcode: str = ""
    description: str = "Unknown in local lookup table"
    hint: str = ""


@dataclass
class ModuleScanResult:
    address: str
    name: str
    part_number: str = ""
    component: str = ""
    role: str = ""
    status: str = "unknown"  # ok, faults, error, skipped
    dtc_count: int | None = None
    dtcs: list[DtcRecord] = field(default_factory=list)
    raw_response: str = ""
    error: str = ""
    close_note: str = ""


@dataclass
class ActiveAutoScanReport:
    generated_at: str
    modules: list[ModuleScanResult]
    scope: str = "read-only VW TP2.0/KWP2000 over CAN"
    redacted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def quiet_reporter_like(reporter: Reporter) -> Reporter:
    return Reporter(
        colour=reporter.colour,
        logger=None,
        verbosity="silent",
        redact_private=getattr(reporter, "redact_private", False),
    )


def parse_dtc_response(resp: bytes, db: DtcDatabase) -> tuple[str, int | None, list[DtcRecord], str]:
    """Return (status, count, records, error)."""
    if not resp:
        return "error", None, [], "empty response"
    if resp[0] != 0x58:
        return "error", None, [], f"unexpected response: {fmt(resp)}"
    if len(resp) < 2:
        return "error", None, [], "truncated positive response 0x58"

    count = resp[1]
    if count == 0:
        return "ok", 0, [], ""

    records = resp[2:]
    expected = count * 3
    if len(records) < expected:
        return "error", count, [], f"incomplete DTC response: expected {expected} record byte(s), got {len(records)}"

    out: list[DtcRecord] = []
    for idx in range(0, expected, 3):
        hi, lo, status = records[idx], records[idx + 1], records[idx + 2]
        num = (hi << 8) | lo
        known = db.lookup.get(num, {})
        out.append(DtcRecord(
            vag_decimal=num,
            raw_hex=f"0x{num:04X}",
            raw_record=f"{hi:02X} {lo:02X} {status:02X}",
            status=status,
            status_hex=f"0x{status:02X}",
            status_bits=status_bit_text(status),
            pcode=known.get("pcode", ""),
            description=known.get("description") or "Unknown in local lookup table",
            hint=known.get("hint", ""),
        ))
    return "faults", count, out, ""


def _module_summary(address: str) -> ModuleScanResult:
    module = find_module(address)
    if module:
        return ModuleScanResult(
            address=module.address,
            name=module.name,
            part_number=module.part_number,
            component="",
            role=module.role,
        )
    return ModuleScanResult(address=address, name=f"Module {address}")


def _open_engine(iface: str, reporter: Reporter, session: int) -> TP20KWP:
    ecu = TP20KWP(iface=iface, reporter=reporter, logical_address=0x01)
    ecu.open(session=session, start_session=True)
    return ecu


def _open_module(iface: str, reporter: Reporter, module: ModuleProfile, session: int) -> TP20KWP:
    kwargs = module_open_kwargs(module.address)
    ecu = TP20KWP(iface=iface, reporter=reporter, **kwargs)
    ecu.open(session=module_session(module, fallback=session), start_session=True)
    return ecu


def collect_active_autoscan(
    iface: str,
    session: int,
    reporter: Reporter,
    db: DtcDatabase,
    modules: Iterable[str] = PROVEN_AUTOSCAN_MODULES,
    include_non_engine: bool = False,
    detail_protocol: bool = False,
) -> ActiveAutoScanReport:
    work_reporter = reporter if detail_protocol else quiet_reporter_like(reporter)
    results: list[ModuleScanResult] = []

    for address in modules:
        address = str(address).strip().upper().zfill(2)
        if address != "01" and not include_non_engine:
            skipped = _module_summary(address)
            skipped.status = "skipped"
            skipped.error = "requires --experimental-module"
            results.append(skipped)
            continue

        result = _module_summary(address)
        module = find_module(address)
        ecu = None
        try:
            if address == "01":
                ecu = _open_engine(iface, work_reporter, session)
                profile_result = read_engine_dtcs_with_profile(ecu, work_reporter, announce=detail_protocol)
                resp = profile_result.response
                result.component = profile_result.profile.name
                if profile_result.identity.part_number:
                    result.part_number = profile_result.identity.part_number
                if profile_result.profile.key != "bkd_edc16":
                    result.role = profile_result.profile.family
            else:
                if not module:
                    raise RuntimeError(f"Unknown module profile: {address}")
                ecu = _open_module(iface, work_reporter, module, session)
                resp = run_module_dtc(ecu, work_reporter, address, db)

            result.raw_response = fmt(resp)
            status, count, dtcs, err = parse_dtc_response(resp, db)
            result.status = status
            result.dtc_count = count
            result.dtcs = dtcs
            result.error = err

        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        finally:
            if ecu is not None:
                try:
                    if address == "03":
                        result.close_note = "ABS/ESP graceful close path used"
                        ecu.graceful_close(pre_drain=0.8, post_drain=1.8)
                    ecu.close()
                except Exception as exc:
                    if not result.error:
                        result.error = f"close failed/ignored: {exc}"
                    try:
                        ecu.close()
                    except Exception:
                        pass

        results.append(result)

    return ActiveAutoScanReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        modules=results,
        redacted=getattr(reporter, "redact_private", False),
    )


def render_autoscan_text(report: ActiveAutoScanReport, colour=None) -> str:
    def c(method: str, text: str) -> str:
        return getattr(colour, method)(text) if colour else text

    lines = ["BKD TP2.0/KWP read-only Auto-Scan", f"Generated: {report.generated_at}", f"Scope: {report.scope}"]
    if report.redacted:
        lines.append("Private identifiers: redacted")
    lines.append("")

    for module in report.modules:
        title = f"{module.address} {module.name}"
        lines.append(c("cyan", title))
        if module.part_number:
            lines.append(f"  Part No: {module.part_number}")
        if module.component:
            lines.append(f"  Component/Profile: {module.component}")
        if module.status == "skipped":
            lines.append("  Status: skipped")
            lines.append(f"  Note: {module.error}")
        elif module.status == "error":
            lines.append(c("red", "  Status: scan failed"))
            if module.error:
                lines.append(f"  Error: {module.error}")
        elif module.status == "ok":
            lines.append(c("green", "  DTCs: none"))
        elif module.status == "faults":
            lines.append(c("yellow", f"  DTCs: {module.dtc_count} record(s)"))
            for dtc in module.dtcs:
                desc = dtc.description
                pcode = f" / {dtc.pcode}" if dtc.pcode else ""
                lines.append(c("yellow", f"  {dtc.vag_decimal:05d} / {dtc.raw_hex}{pcode}: {desc}  status={dtc.status_hex}"))
                if dtc.status_bits:
                    lines.append("    status bits: " + ", ".join(dtc.status_bits))
        else:
            lines.append(f"  Status: {module.status}")
        if module.close_note:
            lines.append(f"  Close: {module.close_note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_autoscan_markdown(report: ActiveAutoScanReport) -> str:
    lines = ["# BKD TP2.0/KWP read-only Auto-Scan", "", f"Generated: `{report.generated_at}`", "", f"Scope: {report.scope}", ""]
    if report.redacted:
        lines.extend(["Private identifiers: redacted", ""])
    lines.append("| Module | Part No | Status | DTCs |")
    lines.append("|---|---|---|---|")
    for module in report.modules:
        dtc_text = ""
        status = module.status
        if module.status == "ok":
            status = "OK"
            dtc_text = "none"
        elif module.status == "faults":
            status = f"{module.dtc_count} DTC(s)"
            dtc_text = "<br>".join(f"{d.vag_decimal:05d} / {d.raw_hex}: {d.description} ({d.status_hex})" for d in module.dtcs)
        elif module.status == "error":
            dtc_text = module.error.replace("|", "\\|")
        elif module.status == "skipped":
            dtc_text = module.error.replace("|", "\\|")
        lines.append(f"| {module.address} {module.name} | {module.part_number or ''} | {status} | {dtc_text} |")
    lines.append("")
    for module in report.modules:
        if module.dtcs:
            lines.append(f"## {module.address} {module.name}")
            lines.append("")
            for dtc in module.dtcs:
                lines.append(f"- **{dtc.vag_decimal:05d} / {dtc.raw_hex}**: {dtc.description}")
                lines.append(f"  - Status: `{dtc.status_hex}`" + (f" — {', '.join(dtc.status_bits)}" if dtc.status_bits else ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_autoscan_outputs(report: ActiveAutoScanReport, txt_out: str | None = None, json_out: str | None = None, md_out: str | None = None, colour=None) -> list[str]:
    written: list[str] = []
    if txt_out:
        Path(txt_out).parent.mkdir(parents=True, exist_ok=True)
        Path(txt_out).write_text(render_autoscan_text(report, colour=None), encoding="utf-8")
        written.append(txt_out)
    if json_out:
        Path(json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(json_out).write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(json_out)
    if md_out:
        Path(md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(md_out).write_text(render_autoscan_markdown(report), encoding="utf-8")
        written.append(md_out)
    return written

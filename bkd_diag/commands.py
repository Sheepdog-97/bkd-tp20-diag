from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime

from .dtc import DtcDatabase, dtc_count_from_response, print_dtc_response
from .kwp import decode_negative
from .mblocks import decode_block_response, format_block_table, live_line, known_map_lines, field_display, short_field_label
from .labels import LabelStore
from .bkd_data import PRESETS
from .vehicle_profile import MODULES, find_module, profile_lines, module_probe_plan_lines, AUTOSCAN_LABELS, AUTOSCAN_COMPONENTS, AUTOSCAN_KNOWN_CURRENT_FAULTS
from .autoscan import load_autoscan, load_default_autoscan
from .reporting import CsvLiveLogger, Reporter
from .utils import ascii_runs, fmt
from .trace_analyzer import analyse_trace, build_summary, write_summary_json
from .active_autoscan import collect_active_autoscan, render_autoscan_text, write_autoscan_outputs, PROVEN_AUTOSCAN_MODULES


def print_negative_response(reporter: Reporter, resp: bytes) -> bool:
    neg = decode_negative(resp)
    if not neg:
        return False
    svc, code, name = neg
    reporter.fail(f"Negative KWP response to service 0x{svc:02X}: 0x{code:02X} {name}")
    reporter.detail(f"Raw response: {fmt(resp)}")
    return True


def run_read(ecu, reporter: Reporter, read_cmd: list[int], db: DtcDatabase) -> bytes:
    reporter.header("Reading DTCs")
    reporter.info(f"KWP command: {fmt(read_cmd)}")
    resp = ecu.kwp_request(read_cmd, timeout=5.0)
    print_dtc_response(reporter, resp, db)
    return resp


def run_clear(ecu, reporter: Reporter, clear_cmd: list[int]) -> tuple[bytes, bool]:
    reporter.header("Clearing DTCs")
    reporter.warn("This may erase freeze-frame/readiness context from the engine ECU")
    reporter.info(f"KWP command: {fmt(clear_cmd)}")
    resp = ecu.kwp_request(clear_cmd, timeout=5.0)

    reporter.header("Clear fault result")
    reporter.detail(f"KWP raw response: {fmt(resp)}")

    if print_negative_response(reporter, resp):
        return resp, False

    if resp and resp[0] == 0x54:
        reporter.ok("Clear faults accepted by ECU")
        reporter.detail("Positive response: 0x14 → 0x54")
        return resp, True

    reporter.warn("Unexpected clear response. Positive ClearDiagnosticInformation usually starts with 0x54.")
    return resp, False


def run_quick(ecu, reporter: Reporter, read_cmd: list[int], clear_cmd: list[int], db: DtcDatabase, yes_clear: bool = False, no_prompt: bool = False) -> None:
    reporter.header("Quick workflow")
    reporter.info("Step 1: read DTCs")
    before = run_read(ecu, reporter, read_cmd, db)
    count = dtc_count_from_response(before)

    if count is None:
        reporter.warn("Could not determine DTC count from response; skipping clear in quick mode.")
        return
    if count == 0:
        reporter.ok("No DTCs present, so quick mode will not clear anything.")
        return

    reporter.warn(f"{count} DTC record(s) present")
    should_clear = False
    if yes_clear:
        should_clear = True
        reporter.info("--yes-clear supplied; proceeding with clear.")
    elif no_prompt:
        reporter.warn("--no-prompt supplied and --yes-clear not supplied; not clearing.")
    else:
        answer = input("Clear engine ECU DTCs now? Type yes/no: ").strip().lower()
        should_clear = answer in ("y", "yes")
        reporter.line(f"User clear decision: {'yes' if should_clear else 'no'}")

    if not should_clear:
        reporter.warn("Clear skipped.")
        return

    run_clear(ecu, reporter, clear_cmd)
    reporter.header("Quick verification")
    run_read(ecu, reporter, read_cmd, db)


def run_block(ecu, reporter: Reporter, block_num: int, labels: LabelStore | None = None) -> bytes:
    reporter.header(f"Reading measuring block {block_num:03d}")
    reporter.info(f"KWP command: 21 {block_num & 0xFF:02X}")
    resp = ecu.kwp_request([0x21, block_num & 0xFF], timeout=6.0)

    decoded = decode_block_response(block_num, resp, labels=labels)
    if decoded is None:
        reporter.warn(f"Unexpected response for block {block_num:03d}: {fmt(resp)}")
        print_negative_response(reporter, resp)
        return resp

    for line in format_block_table(decoded, detail=True, colour=reporter.colour):
        reporter.line(line, level=1)

    reporter.detail(f"Raw response: {fmt(resp)}")
    return resp


def _write_live_csv(csv_logger: CsvLiveLogger | None, decoded: dict, block_num: int) -> None:
    if not csv_logger:
        return
    text_value = " | ".join(decoded.get("text_runs", [])) if decoded.get("classification") == "text" else None
    csv_logger.write_sample(
        datetime.now().isoformat(timespec="milliseconds"),
        block_num,
        decoded["fields"],
        text_value=text_value,
    )


def _field_numeric_value(field: dict) -> float | None:
    decoded = field.get("decoded")
    if not decoded:
        return None
    value = decoded.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _update_live_stats(stats: dict[tuple[int, int], dict[str, float]], block_num: int, decoded: dict) -> None:
    for field in decoded.get("fields", []):
        value = _field_numeric_value(field)
        if value is None:
            continue
        key = (block_num, int(field.get("index", 0)))
        item = stats.setdefault(key, {"first": value, "min": value, "max": value, "last": value})
        item["last"] = value
        item["min"] = min(item["min"], value)
        item["max"] = max(item["max"], value)


def _fmt_num(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:.0f}"
    if abs(value) >= 100:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _live_dashboard_block_lines(block_num: int, decoded_block: dict, stats: dict[tuple[int, int], dict[str, float]], colour) -> list[str]:
    hint = decoded_block["hint"]
    name = hint.get("name") or f"Block {block_num:03d}"
    lines = [colour.bold(colour.cyan(f"block {block_num:03d}")) + colour.dim(f"  {name}")]

    if decoded_block.get("classification") == "text":
        text = " | ".join(decoded_block.get("text_runs", [])) or "<no printable text>"
        lines.append(f"  text: {colour.green(text)}")
        return lines

    for field in decoded_block.get("fields", []):
        if field.get("status") == "empty":
            continue
        label = short_field_label(field.get("label", f"F{field.get('index')}"))
        value_text = field_display(field)
        numeric = _field_numeric_value(field)
        if numeric is None:
            lines.append(f"  {colour.cyan(label):<34} {colour.yellow(value_text)}")
            continue

        unit = field.get("decoded", {}).get("unit", "")
        item = stats.get((block_num, int(field.get("index", 0))), {})
        delta = numeric - item.get("first", numeric)
        changed = abs(delta) > 0.01
        val_col = colour.yellow if changed else colour.green
        range_text = (
            f"min {item.get('min', numeric):.1f}  "
            f"max {item.get('max', numeric):.1f}  "
            f"Δ {delta:+.1f}"
        )
        lines.append(
            f"  {colour.cyan(label):<34} "
            f"{val_col(_fmt_num(numeric) + (' ' + unit if unit else '')):<18} "
            f"{colour.dim(range_text)}"
        )
    return lines


def _render_live_dashboard(
    reporter: Reporter,
    clean_blocks: list[int],
    interval: float,
    count: int,
    sample_no: int,
    started_at: float,
    latest_lines: list[str],
    error_lines: list[str],
    csv_path: str | None = None,
) -> None:
    colour = reporter.colour
    elapsed = time.time() - started_at
    lines = [
        colour.bold(colour.cyan("== Live measuring blocks ==")),
        f"Sample: {colour.green(str(sample_no))}" + (f" / {count}" if count else "")
        + f"    Time: {colour.green(datetime.now().strftime('%H:%M:%S'))}"
        + f"    Elapsed: {colour.green(f'{elapsed:0.1f}s')}",
        f"Blocks: {', '.join(f'{b:03d}' for b in clean_blocks)}    Interval: {interval:.2f}s",
    ]
    if csv_path:
        lines.append(colour.dim(f"CSV live log: {csv_path}"))
    lines.extend(["", colour.dim("Press Ctrl+C to stop and return to the menu."), ""])

    if latest_lines:
        lines.extend(latest_lines)
    else:
        lines.append(colour.yellow("No samples decoded yet."))

    if error_lines:
        lines.extend(["", colour.yellow("Recent warnings:")])
        lines.extend(error_lines[-4:])

    sys.stdout.write("\033[2J\033[H" + "\n".join(lines) + "\n")
    sys.stdout.flush()


def run_live(
    ecu,
    reporter: Reporter,
    blocks: list[int],
    interval: float,
    count: int,
    include_raw: bool,
    csv_logger: CsvLiveLogger | None,
    labels: LabelStore | None = None,
    dashboard: bool = False,
) -> None:
    if interval < 0.2:
        reporter.warn(f"Requested interval {interval:.2f}s is very fast; clamping to 0.20s")
        interval = 0.2

    clean_blocks = [b & 0xFF for b in blocks]
    dashboard_enabled = dashboard and reporter.colour.enabled and sys.stdout.isatty()

    if not dashboard_enabled:
        if dashboard:
            reporter.warn("Live dashboard disabled because stdout is not an interactive colour terminal; using scrolling output.")
        reporter.header("Live measuring blocks")
        reporter.info("Press Ctrl+C to stop")
        reporter.info(f"Blocks: {', '.join(f'{b:03d}' for b in clean_blocks)}")
        reporter.info(f"Interval: {interval:.2f}s")
        if csv_logger and csv_logger.path:
            reporter.info(f"CSV live log: {csv_logger.path}")

        samples = 0
        while True:
            tick_started = time.time()
            ts = datetime.now().strftime("%H:%M:%S")

            for block_num in clean_blocks:
                try:
                    resp = ecu.kwp_request([0x21, block_num], timeout=6.0)
                    decoded = decode_block_response(block_num, resp, labels=labels)
                    if decoded is None:
                        reporter.warn(f"{ts} block {block_num:03d} unexpected={fmt(resp)}")
                        continue

                    reporter.line(f"{ts}  {live_line(block_num, decoded, include_raw=include_raw, raw_resp=resp, colour=reporter.colour)}")
                    _write_live_csv(csv_logger, decoded, block_num)

                except Exception as exc:
                    reporter.warn(f"Live read failed for block {block_num:03d}: {exc}")

            samples += 1
            if count and samples >= count:
                reporter.ok(f"Live capture complete: {samples} sample cycle(s)")
                return

            time.sleep(max(0.0, interval - (time.time() - tick_started)))

    # Dashboard mode deliberately redraws the same terminal area instead of
    # producing a journal of samples. The run log stays compact; use --csv from
    # the direct CLI if you need a full sample history.
    reporter.header("Live measuring blocks")
    reporter.info("Dashboard mode: values update in place. Press Ctrl+C to stop.")
    reporter.info(f"Blocks: {', '.join(f'{b:03d}' for b in clean_blocks)}")
    reporter.info(f"Interval: {interval:.2f}s")
    if csv_logger and csv_logger.path:
        reporter.info(f"CSV live log: {csv_logger.path}")

    samples = 0
    started_at = time.time()
    latest_lines: list[str] = []
    error_lines: list[str] = []
    stats: dict[tuple[int, int], dict[str, float]] = {}

    while True:
        tick_started = time.time()
        samples += 1
        new_lines: list[str] = []

        for block_num in clean_blocks:
            try:
                resp = ecu.kwp_request([0x21, block_num], timeout=6.0)
                decoded = decode_block_response(block_num, resp, labels=labels)
                if decoded is None:
                    error_lines.append(reporter.colour.yellow(f"block {block_num:03d} unexpected={fmt(resp)}"))
                    continue

                _update_live_stats(stats, block_num, decoded)
                new_lines.extend(_live_dashboard_block_lines(block_num, decoded, stats, reporter.colour))
                if include_raw:
                    new_lines.append(reporter.colour.dim(f"  raw={fmt(resp)}"))
                _write_live_csv(csv_logger, decoded, block_num)

            except Exception as exc:
                error_lines.append(reporter.colour.yellow(f"block {block_num:03d}: {exc}"))

        if new_lines:
            latest_lines = new_lines

        _render_live_dashboard(
            reporter,
            clean_blocks=clean_blocks,
            interval=interval,
            count=count,
            sample_no=samples,
            started_at=started_at,
            latest_lines=latest_lines,
            error_lines=error_lines,
            csv_path=csv_logger.path if csv_logger and csv_logger.path else None,
        )

        if count and samples >= count:
            reporter.ok(f"Live capture complete: {samples} sample cycle(s)")
            return

        time.sleep(max(0.0, interval - (time.time() - tick_started)))


def run_scan_blocks(ecu, reporter: Reporter, start: int, end: int, delay: float, show_empty: bool, show_negative: bool, labels: LabelStore | None = None) -> None:
    if start < 0 or end > 255 or start > end:
        raise ValueError("Block scan range must be 0-255 and start <= end")

    reporter.header(f"Scanning measuring blocks {start:03d}-{end:03d}")
    reporter.info("Classifying positive responses as active, empty, text, or mixed.")

    active: list[int] = []
    empty: list[int] = []
    text: list[int] = []
    mixed: list[int] = []
    negative: list[int] = []

    for block_num in range(start, end + 1):
        try:
            resp = ecu.kwp_request([0x21, block_num & 0xFF], timeout=5.0)
            decoded = decode_block_response(block_num, resp, labels=labels)

            if decoded:
                cls = decoded["classification"]
                if cls == "active":
                    active.append(block_num)
                    reporter.line(f"  ✓ block {block_num:03d} active fields={decoded['active_count']}/{len(decoded['fields'])}")
                elif cls == "text":
                    text.append(block_num)
                    runs = " | ".join(decoded["text_runs"])
                    reporter.line(f"  ★ block {block_num:03d} text/version: {runs}")
                elif cls == "empty":
                    empty.append(block_num)
                    if show_empty:
                        reporter.line(f"  - block {block_num:03d} empty")
                else:
                    mixed.append(block_num)
                    reporter.line(f"  ? block {block_num:03d} mixed active={decoded['active_count']} empty={decoded['empty_count']}")
            else:
                neg = decode_negative(resp)
                if neg:
                    negative.append(block_num)
                    if show_negative:
                        svc, code, name = neg
                        reporter.line(f"  - block {block_num:03d} negative=0x{code:02X} {name}")
                else:
                    mixed.append(block_num)
                    reporter.line(f"  ? block {block_num:03d} unexpected={fmt(resp)}")

        except Exception as exc:
            mixed.append(block_num)
            reporter.warn(f"block {block_num:03d} error={exc}")

        if delay > 0:
            time.sleep(delay)

    reporter.header("Block scan summary")
    reporter.ok(f"Active blocks: {', '.join(f'{b:03d}' for b in active) if active else 'none'}")
    if text:
        reporter.ok(f"Text/version blocks: {', '.join(f'{b:03d}' for b in text)}")
    if empty:
        reporter.info(f"Empty placeholder blocks: {len(empty)}")
        reporter.detail(", ".join(f"{b:03d}" for b in empty))
    if negative:
        reporter.info(f"Negative/unsupported blocks: {', '.join(f'{b:03d}' for b in negative)}")
    if mixed:
        reporter.warn(f"Mixed/unclassified blocks: {', '.join(f'{b:03d}' for b in mixed)}")


def run_ident(ecu, reporter: Reporter) -> None:
    reporter.header("Reading ECU identification")
    ids = [0x90, 0x91, 0x92, 0x9B, 0x9C]
    results: dict[int, bytes] = {}

    for local_id in ids:
        reporter.info(f"Requesting ReadECUIdentification: 1A {local_id:02X}")
        try:
            results[local_id] = ecu.kwp_request([0x1A, local_id], timeout=6.0)
        except Exception as exc:
            reporter.warn(f"1A {local_id:02X} failed: {exc}")
            results[local_id] = b""

    reporter.header("ECU identification result")
    vin = None
    sw_part = None
    sw_version = None
    hw_bosch = None
    component = None

    for local_id, resp in results.items():
        reporter.detail("")
        reporter.detail(f"Local ID 0x{local_id:02X}: {fmt(resp)}")
        neg = decode_negative(resp)
        if neg:
            svc, code, name = neg
            reporter.detail(f"  negative: 0x{code:02X} {name}")
            continue
        if len(resp) >= 2 and resp[0] == 0x5A and resp[1] == local_id:
            payload = bytes(resp[2:])
            runs = ascii_runs(payload, min_len=4)
            if local_id == 0x90 and runs:
                vin = "".join(runs).strip()
            elif local_id == 0x91:
                clean = bytes(b for b in payload if 32 <= b <= 126).decode("ascii", errors="ignore").strip()
                if clean:
                    hw_bosch = clean
            elif local_id == 0x9B:
                all_text = " | ".join(runs)
                m = re.search(r"(03G[0-9A-Z ]{6,12}AJ)\s+([0-9]{4})", all_text)
                if m:
                    sw_part = m.group(1).replace(" ", "")
                    sw_version = m.group(2)
                for run in runs:
                    if "EDC" in run or "R4" in run:
                        component = run.strip(" )(").strip()

    if sw_part:
        sw_part_pretty = f"{sw_part[0:3]} {sw_part[3:6]} {sw_part[6:9]} {sw_part[9:]}"
    else:
        sw_part_pretty = "not decoded"

    if hw_bosch and len(hw_bosch) == 10 and hw_bosch.isdigit():
        hw_bosch = f"{hw_bosch[0:3]} {hw_bosch[3:6]} {hw_bosch[6:9]} {hw_bosch[9:]}"

    c = reporter.colour
    reporter.line(f"VIN:        {c.green(vin) if vin else c.dim('not decoded')}")
    reporter.line(f"ECU SW:     {c.green(sw_part_pretty) if sw_part else c.dim('not decoded')}")
    reporter.line(f"SW version: {c.green(sw_version) if sw_version else c.dim('not decoded')}")
    reporter.line(f"HW/Bosch:   {c.green(hw_bosch) if hw_bosch else c.dim('not decoded')}")
    reporter.line(f"Component:  {c.green(component) if component else c.dim('not decoded')}")
    reporter.line(f"Protocol:   {c.cyan('VW TP2.0 / KWP2000')}")


def run_cmd(ecu, reporter: Reporter, req: list[int]) -> None:
    reporter.header("Sending custom KWP command")
    reporter.info(f"KWP command: {fmt(req)}")
    resp = ecu.kwp_request(req, timeout=6.0)
    reporter.line(f"Response: {fmt(resp)}")
    print_negative_response(reporter, resp)


def run_freeze_probe(ecu, reporter: Reporter) -> None:
    reporter.header("Experimental freeze-frame / fault-environment probe")
    reporter.warn("Raw probe only; no verified environment decoder yet.")

    candidates = [
        ("Proven DTC read", [0x18, 0x02, 0xFF, 0x00]),
        ("Read DTC variant 18 00 FF 00", [0x18, 0x00, 0xFF, 0x00]),
        ("Read DTC variant 18 01 FF 00", [0x18, 0x01, 0xFF, 0x00]),
        ("Read DTC variant 18 03 FF 00", [0x18, 0x03, 0xFF, 0x00]),
        ("Read DTC variant 18 04 FF 00", [0x18, 0x04, 0xFF, 0x00]),
    ]
    for label, req in candidates:
        reporter.info(f"{label}: {fmt(req)}")
        try:
            resp = ecu.kwp_request(req, timeout=5.0)
            reporter.line(f"  raw={fmt(resp)}")
            print_negative_response(reporter, resp)
        except Exception as exc:
            reporter.warn(f"  failed: {exc}")


def run_readiness_probe(ecu, reporter: Reporter, labels: LabelStore | None = None) -> None:
    reporter.header("Readiness / EOBD probe")
    reporter.info("First reading measuring block 017, which public BKD/BMM-style labels describe as EOBD readiness/CARB Mode 01 data.")

    try:
        run_block(ecu, reporter, 17, labels=labels)
    except Exception as exc:
        reporter.warn(f"Block 017 readiness read failed: {exc}")

    reporter.header("Raw OBD service 01 probe")
    reporter.warn("Generic OBD service 01 was previously rejected in this KWP session; keeping probe raw.")

    candidates = [
        ("OBD service 01 PID 01", [0x01, 0x01]),
        ("OBD service 01 PID 1C", [0x01, 0x1C]),
        ("OBD service 01 PID 1F", [0x01, 0x1F]),
    ]
    for label, req in candidates:
        reporter.info(f"{label}: {fmt(req)}")
        try:
            resp = ecu.kwp_request(req, timeout=4.0)
            reporter.line(f"  raw={fmt(resp)}")
            print_negative_response(reporter, resp)
        except Exception as exc:
            reporter.warn(f"  failed: {exc}")


def run_selftest(ecu, reporter: Reporter, db: DtcDatabase, labels: LabelStore | None = None) -> None:
    reporter.header("Self-test")
    resp = ecu.kwp_request([0x18, 0x02, 0xFF, 0x00], timeout=5.0)
    print_dtc_response(reporter, resp, db, title="Self-test DTC read")
    run_block(ecu, reporter, 0x0B, labels=labels)




def _decoded_field_text(decoded: dict, index: int) -> str:
    for field in decoded.get("fields", []):
        if field.get("index") == index and field.get("status") == "active":
            return field_display(field)
    return "not available"


def _try_decoded_block(ecu, reporter: Reporter, block_num: int, labels: LabelStore | None = None) -> dict | None:
    try:
        resp = ecu.kwp_request([0x21, block_num & 0xFF], timeout=6.0)
        decoded = decode_block_response(block_num, resp, labels=labels)
        if decoded is None:
            reporter.warn(f"Block {block_num:03d} unexpected response: {fmt(resp)}")
        return decoded
    except Exception as exc:
        reporter.warn(f"Block {block_num:03d} read failed: {exc}")
        return None


def run_engine_check(ecu, reporter: Reporter, db: DtcDatabase, labels: LabelStore | None = None) -> None:
    """Read-only, engine-only quick health/MOT-style snapshot."""
    reporter.header("Engine check / reader-style snapshot")
    reporter.warn("Read-only Engine 01 check. No clear, coding, adaptation, basic settings, or non-engine modules.")

    dtc_status = "unknown"
    dtc_count = None
    dtc_resp = None
    vin = None
    ecu_id = None

    reporter.header("Step 1: engine fault memory")
    try:
        dtc_resp = ecu.kwp_request([0x18, 0x02, 0xFF, 0x00], timeout=5.0)
        dtc_count = dtc_count_from_response(dtc_resp)
        if dtc_count == 0:
            dtc_status = "OK"
            reporter.ok("Engine DTCs: none reported by 18 02 FF 00")
        elif dtc_count is None:
            dtc_status = "unknown"
            reporter.warn(f"Engine DTCs: unexpected response {fmt(dtc_resp)}")
        else:
            dtc_status = "FAULTS"
            reporter.warn(f"Engine DTCs: {dtc_count} record(s)")
            print_dtc_response(reporter, dtc_resp, db, title="Engine DTC details")
    except Exception as exc:
        dtc_status = "read failed"
        reporter.warn(f"Engine DTC read failed: {exc}")

    reporter.header("Step 2: identity")
    try:
        vin_resp = ecu.kwp_request([0x1A, 0x90], timeout=6.0)
        if len(vin_resp) >= 2 and vin_resp[:2] == bytes([0x5A, 0x90]):
            runs = ascii_runs(vin_resp[2:], min_len=8)
            if runs:
                vin = "".join(runs).strip()

        id_resp = ecu.kwp_request([0x1A, 0x9B], timeout=6.0)
        if len(id_resp) >= 2 and id_resp[:2] == bytes([0x5A, 0x9B]):
            runs = ascii_runs(id_resp[2:], min_len=4)
            ecu_id = " | ".join(runs)
    except Exception as exc:
        reporter.warn(f"ECU identification in engine-check failed: {exc}")

    reporter.line(f"VIN:      {reporter.colour.green(vin) if vin else reporter.colour.dim('not decoded')}")
    reporter.line(f"ECU info: {reporter.colour.green(ecu_id) if ecu_id else reporter.colour.dim('not decoded')}")

    reporter.header("Step 3: BKD live-data snapshot")
    b001 = _try_decoded_block(ecu, reporter, 1, labels=labels)
    b003 = _try_decoded_block(ecu, reporter, 3, labels=labels)
    b011 = _try_decoded_block(ecu, reporter, 11, labels=labels)
    b017 = _try_decoded_block(ecu, reporter, 17, labels=labels)

    coolant = _decoded_field_text(b001, 4) if b001 else "not available"
    rpm = _decoded_field_text(b003, 1) if b003 else "not available"
    maf_spec = _decoded_field_text(b003, 2) if b003 else "not available"
    maf_actual = _decoded_field_text(b003, 3) if b003 else "not available"
    egr_duty = _decoded_field_text(b003, 4) if b003 else "not available"
    boost_spec = _decoded_field_text(b011, 2) if b011 else "not available"
    boost_actual = _decoded_field_text(b011, 3) if b011 else "not available"
    boost_duty = _decoded_field_text(b011, 4) if b011 else "not available"

    reporter.line(f"Coolant temp candidate: {coolant}")
    reporter.warn("Coolant temp is currently shown from BKD measuring block 001, field 4. Treat as a candidate/raw value until calibrated against VCDS/EOBD PID 05.")

    reporter.line("MAF / EGR:")
    reporter.line(f"  rpm:        {rpm}")
    reporter.line(f"  air spec:   {maf_spec}")
    reporter.line(f"  air actual: {maf_actual}")
    reporter.line(f"  EGR duty:   {egr_duty}")

    reporter.line("Boost:")
    reporter.line(f"  boost spec:   {boost_spec}")
    reporter.line(f"  boost actual: {boost_actual}")
    reporter.line(f"  N75/duty:     {boost_duty}")

    reporter.header("Step 4: readiness / EOBD")
    if b017:
        reporter.warn("Readiness is currently shown as raw/candidate BKD block 017 fields, not a polished MOT readiness decoder.")
        for field in b017.get("fields", []):
            if field.get("status") == "active":
                reporter.line(f"  F{field['index']} {field.get('label', '')}: {field_display(field)} raw={fmt(field.get('raw', b''))}")
    else:
        reporter.warn("Readiness block 017 not available in this snapshot.")

    reporter.header("Summary")
    if dtc_status == "OK":
        reporter.ok("Engine fault memory: clear")
    elif dtc_status == "FAULTS":
        reporter.warn(f"Engine fault memory: {dtc_count} fault record(s)")
    else:
        reporter.warn(f"Engine fault memory: {dtc_status}")

    reporter.line(f"VIN/ECU identity: {'decoded' if vin or ecu_id else 'not decoded'}")
    reporter.line("Live data: BKD block 003/011 snapshot complete" if (b003 and b011) else "Live data: partial/failed snapshot")
    reporter.warn("MOT-style caveat: this is the BKD TP2.0/KWP path. Coolant/readiness are not yet the same polished generic EOBD presentation a commercial MOT reader would show.")
    reporter.ok("Engine check complete")


def run_trace_analysis(reporter: Reporter, path: str, show_raw: bool = False, max_events: int = 0, json_out: str | None = None) -> None:
    reporter.header("candump TP2.0/KWP trace analysis")
    frames, events, counts = analyse_trace(path)
    summary = build_summary(path, frames, events, counts)

    reporter.line(f"Path:          {path}")
    reporter.line(f"Frames parsed: {reporter.colour.green(str(len(frames)))}")
    reporter.line(f"Events found:  {reporter.colour.green(str(len(events)))}")

    if json_out:
        write_summary_json(json_out, summary)
        reporter.ok(f"JSON summary written: {json_out}")

    if not frames:
        reporter.warn("No CAN frames parsed. Expected candump formats like '200#03C0...', '200 [7] 03 C0 ...', or project logs like 'TX 200 03 C0 ...'.")
        return

    reporter.header("CAN ID counts")
    for can_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]:
        reporter.line(f"  0x{can_id:03X}: {count}")

    if summary["setup_channels"]:
        reporter.header("TP2.0 setup channels")
        for channel in summary["setup_channels"]:
            reporter.ok(
                f"L{channel['line']}: response {channel['response_can_id']} "
                f"logical≈{channel['logical_address_guess']} "
                f"ECU→tester={channel['ecu_to_tester_can_id']} "
                f"tester→ECU={channel['tester_to_ecu_can_id']}"
            )
    else:
        reporter.warn("No TP2.0 D0 setup response detected.")

    reporter.header("KWP/service summary")
    service_counts = summary.get("service_counts", {})
    if service_counts:
        for service, count in sorted(service_counts.items(), key=lambda item: (-item[1], item[0])):
            reporter.line(f"  {service}: {count}")
    else:
        reporter.warn("No TP2.0 data/KWP service frames detected.")

    if summary.get("sessions_requested"):
        reporter.line("Sessions requested: " + ", ".join(summary["sessions_requested"]))
    if summary.get("ident_requests"):
        reporter.line("Ident IDs requested: " + ", ".join(summary["ident_requests"]))
    if summary.get("measuring_block_requests"):
        reporter.line("Measuring blocks requested: " + ", ".join(summary["measuring_block_requests"]))

    reporter.header("Detected TP2.0/KWP events")
    shown = 0
    for event in events:
        if max_events and shown >= max_events:
            remaining = len(events) - shown
            reporter.warn(f"Stopped after {max_events} event(s); {remaining} more not shown.")
            break

        marker = {
            "setup-response": "✓",
            "kwp": "•",
            "channel-close": "!",
            "channel-test": "•",
            "setup-request": "•",
        }.get(event.kind, "•")
        reporter.line(f"{marker} L{event.line_no:<5} ID 0x{event.can_id:03X} {event.detail}")
        if show_raw:
            reporter.detail(f"    raw: {event.raw}")
        shown += 1

    if not any(e.kind == "kwp" for e in events):
        reporter.warn("No TP2.0 data/KWP frames detected. Trace may only contain setup/control frames or an unsupported format.")


def run_list_presets(reporter: Reporter) -> None:
    reporter.header("BKD live presets")
    for name, preset in PRESETS.items():
        blocks = " ".join(f"{b:03d}" for b in preset["blocks"])
        reporter.line(f"{reporter.colour.green(name):<18} {blocks:<24} {preset['description']}")


def run_preset(ecu, reporter: Reporter, name: str, interval: float, count: int, include_raw: bool, csv_logger: CsvLiveLogger | None, labels: LabelStore | None = None) -> None:
    key = name.lower().strip()
    if key not in PRESETS:
        reporter.fail(f"Unknown preset: {name}")
        run_list_presets(reporter)
        return
    preset = PRESETS[key]
    reporter.header(f"Preset: {key}")
    reporter.info(preset["description"])
    run_live(
        ecu,
        reporter,
        blocks=preset["blocks"],
        interval=interval,
        count=count,
        include_raw=include_raw,
        csv_logger=csv_logger,
        labels=labels,
    )


def run_vehicle_profile(reporter: Reporter, detail: bool = False) -> None:
    reporter.header("Vehicle profile")
    for line in profile_lines(detail=detail):
        if not line:
            reporter.line("")
            continue
        if line.startswith("VIN:"):
            parts = line.split(":", 1)
            reporter.line(f"{parts[0]}:{reporter.colour.green(parts[1])}")
        elif line.strip().startswith(("01", "03", "08", "09", "15", "16", "17", "19", "25", "42", "44", "46", "52", "62", "72")):
            reporter.line(line)
        else:
            reporter.line(line)


def run_module_info(reporter: Reporter, key: str) -> None:
    module = find_module(key)
    if not module:
        reporter.fail(f"No module found for: {key}")
        reporter.info("Run: python3 -m bkd_diag.cli vehicle --detail")
        return

    reporter.header(f"Module {module.address} - {module.name}")
    reporter.line(f"Part number: {reporter.colour.green(module.part_number)}")
    if module.address in AUTOSCAN_COMPONENTS:
        reporter.line(f"Component:   {reporter.colour.green(AUTOSCAN_COMPONENTS[module.address])}")
    if module.address in AUTOSCAN_LABELS:
        reporter.line(f"VCDS label:  {reporter.colour.green(AUTOSCAN_LABELS[module.address])}")
    reporter.line(f"Role:        {module.role}")
    reporter.line(f"Protocol:    {module.likely_protocol}")
    if module.has_vcds_tp20_profile:
        reporter.line(
            "TP2.0:      "
            f"logical=0x{module.diag_logical_address:02X} "
            f"tester→ECU=0x{module.tester_to_ecu_can_id:03X} "
            f"ECU→tester=0x{module.ecu_to_tester_can_id:03X} "
            f"session=0x{module.kwp_session:02X} "
            f"dtc={fmt(module.dtc_read_request)}"
        )
    if module.label_candidates:
        reporter.line("Candidate labels:")
        for label in module.label_candidates:
            marker = " ← Auto-Scan" if label == AUTOSCAN_LABELS.get(module.address) else ""
            reporter.line(f"  - {label}{marker}")
    faults = AUTOSCAN_KNOWN_CURRENT_FAULTS.get(module.address, [])
    if faults:
        reporter.line("Known current Auto-Scan faults:")
        for fault in faults:
            reporter.line(f"  - {reporter.colour.yellow(fault)}")
    if module.notes:
        reporter.line(f"Notes:       {module.notes}")


def run_module_probe_plan(reporter: Reporter) -> None:
    reporter.header("Module expansion plan")
    for line in module_probe_plan_lines():
        reporter.line(line)


def run_autoscan_summary(reporter: Reporter, path: str | None = None, faults_only: bool = False) -> None:
    scan = load_autoscan(path) if path else load_default_autoscan()
    reporter.header("VCDS Auto-Scan summary")
    if scan.vin:
        reporter.line(f"VIN:     {reporter.colour.green(scan.vin)}")
    if scan.mileage:
        reporter.line(f"Mileage: {scan.mileage}")
    if scan.chassis:
        reporter.line(f"Chassis: {scan.chassis}")
    if scan.scan:
        reporter.line(f"Scan:    {scan.scan}")

    reporter.line("")
    reporter.line("Modules:")
    for addr in sorted(scan.modules):
        module = scan.modules[addr]
        has_faults = bool(module.faults) or "Cannot be reached" in module.fault_status
        if faults_only and not has_faults:
            continue

        status_col = reporter.colour.yellow(module.fault_status) if has_faults else reporter.colour.green(module.fault_status)
        reporter.line(f"  {addr:<2} {module.name:<22} {module.part_number:<16} {status_col}")
        if module.label:
            reporter.detail(f"      label:     {module.label}")
        if module.component:
            reporter.detail(f"      component: {module.component}")
        if module.coding:
            reporter.detail(f"      coding:    {module.coding}")
        for fault in module.faults:
            reporter.line(f"      - {reporter.colour.yellow(fault['code'] + ' - ' + fault['text'])}")
            reporter.line(f"        {fault['subcode']} - {fault['subtext']}")


def run_autoscan_faults(reporter: Reporter, path: str | None = None) -> None:
    run_autoscan_summary(reporter, path=path, faults_only=True)

def run_active_autoscan(
    reporter: Reporter,
    iface: str,
    session: int,
    db: DtcDatabase,
    include_non_engine: bool,
    detail_protocol: bool = False,
    txt_out: str | None = None,
    json_out: str | None = None,
    md_out: str | None = None,
    modules: list[str] | None = None,
) -> None:
    reporter.header("Auto-Scan read-only")
    if include_non_engine:
        reporter.warn("Read-only autoscan opens proven modules and reads DTCs. No clears/coding/adaptations are sent.")
    else:
        reporter.warn("--experimental-module not supplied; autoscan will read Engine 01 only.")

    selected = modules or (PROVEN_AUTOSCAN_MODULES if include_non_engine else ["01"])
    report = collect_active_autoscan(
        iface=iface,
        session=session,
        reporter=reporter,
        db=db,
        modules=selected,
        include_non_engine=include_non_engine,
        detail_protocol=detail_protocol,
    )

    reporter.line(render_autoscan_text(report, colour=reporter.colour).rstrip())
    written = write_autoscan_outputs(report, txt_out=txt_out, json_out=json_out, md_out=md_out, colour=reporter.colour)
    for path in written:
        reporter.ok(f"Wrote Auto-Scan report: {path}")


def run_map_blocks(reporter: Reporter) -> None:
    reporter.header("BKD block map")
    for line in known_map_lines():
        reporter.line(line)

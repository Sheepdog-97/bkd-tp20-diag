from __future__ import annotations

import argparse
import sys

from .canif import ensure_can_interface
from .commands import (
    run_block, run_clear, run_cmd, run_freeze_probe, run_ident, run_live,
    run_map_blocks, run_quick, run_read, run_readiness_probe, run_scan_blocks, run_selftest,
    run_list_presets, run_preset, run_vehicle_profile, run_module_info, run_module_probe_plan, run_autoscan_summary, run_autoscan_faults,
    run_engine_check, run_trace_analysis
)
from .dtc import DtcDatabase
from .reporting import Colour, CsvLiveLogger, Reporter, RunLogger
from .tp20 import TP20KWP
from .utils import parse_hex_items, parse_int_auto
from .labels import parse_label_file
from .module_probe import module_open_kwargs, module_session, resolve_module_address, run_module_dtc, run_module_ident, run_read_only_probe
from .setup_discovery import run_setup_discovery
from .session_discovery import run_session_discovery, DEFAULT_SESSION_CANDIDATES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BKD / VAG TP2.0 KWP2000 diagnostics via SocketCAN")

    parser.add_argument("--iface", default="can0")
    parser.add_argument("--bitrate", type=int, default=500000)
    parser.add_argument("--no-iface-setup", action="store_true")
    parser.add_argument("--force-iface-setup", action="store_true")
    parser.add_argument("--session", default="89")
    parser.add_argument("--log-dir", default="logs")
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument("--dtc-db", default=None)
    parser.add_argument("--label-file", default=None, help="Optional readable .lbl/.clb label file for measuring block names")
    parser.add_argument("--no-colour", "--no-color", action="store_true")
    parser.add_argument("--force-colour", "--force-color", action="store_true", help="Force ANSI colour even if stdout is not detected as a TTY")
    parser.add_argument("--experimental-module", action="store_true", help="Allow active experimental non-engine module probes/discovery")

    out = parser.add_mutually_exclusive_group()
    out.add_argument("--silent", action="store_true", help="Minimal terminal output")
    out.add_argument("--detail", action="store_true", help="Readable details without raw frame trace")
    out.add_argument("--trace", action="store_true", help="Full raw TX/RX trace on terminal")

    sub = parser.add_subparsers(dest="action", required=True)

    read_p = sub.add_parser("read", help="Read engine ECU faults")
    read_p.add_argument("--cmd", nargs="+", default=["18", "02", "FF", "00"])

    clear_p = sub.add_parser("clear", help="Clear engine ECU faults")
    clear_p.add_argument("--cmd", nargs="+", default=["14", "FF", "00"])
    clear_p.add_argument("--yes-clear", action="store_true")

    quick_p = sub.add_parser("quick", help="Read, optionally clear, then read again")
    quick_p.add_argument("--read-cmd", nargs="+", default=["18", "02", "FF", "00"])
    quick_p.add_argument("--clear-cmd", nargs="+", default=["14", "FF", "00"])
    quick_p.add_argument("--yes-clear", action="store_true")
    quick_p.add_argument("--no-prompt", action="store_true")

    sub.add_parser("ident", help="Read ECU identification")
    sub.add_parser("engine-check", help="Read-only Engine 01 DTC/ID/live-data snapshot")
    sub.add_parser("mot-check", help="Alias for engine-check")
    sub.add_parser("selftest", help="DTC read + block 011 sanity check")
    sub.add_parser("map-blocks", help="Show observed BKD block map")
    sub.add_parser("presets", help="List built-in live/snapshot block presets")

    vehicle_p = sub.add_parser("vehicle", help="Show this vehicle profile and known modules")
    vehicle_p.add_argument("--detail", action="store_true", help="Show protocol notes and candidate label files")

    mod_p = sub.add_parser("module-info", help="Show profile info for one module/address")
    mod_p.add_argument("module", help="Address/name/part number, e.g. 19, gateway, engine")

    sub.add_parser("module-plan", help="Show safe plan for adding non-engine modules")

    autoscan_p = sub.add_parser("autoscan-summary", help="Summarise a VCDS Auto-Scan log")
    autoscan_p.add_argument("path", nargs="?", help="Optional VCDS Auto-Scan text file; defaults to built-in profile scan")
    autoscan_p.add_argument("--faults-only", action="store_true")

    autoscan_faults_p = sub.add_parser("autoscan-faults", help="Show only faults from a VCDS Auto-Scan log")
    autoscan_faults_p.add_argument("path", nargs="?", help="Optional VCDS Auto-Scan text file; defaults to built-in profile scan")

    preset_p = sub.add_parser("preset", help="Run a named block preset in live mode")
    preset_p.add_argument("name")
    preset_p.add_argument("--interval", type=float, default=1.0)
    preset_p.add_argument("--count", type=int, default=0)
    preset_p.add_argument("--raw", action="store_true")
    preset_p.add_argument("--csv", action="store_true")

    label_info = sub.add_parser("label-info", help="Inspect readability of a .lbl/.clb label file")
    label_info.add_argument("path")

    trace_p = sub.add_parser("analyse-trace", aliases=["analyze-trace"], help="Analyse a candump TP2.0/KWP trace")
    trace_p.add_argument("path")
    trace_p.add_argument("--raw", action="store_true", help="Show original candump line for each detected event")
    trace_p.add_argument("--max-events", type=int, default=0, help="Limit displayed events; 0 shows all")
    trace_p.add_argument("--json-out", help="Write machine-readable trace summary JSON")

    block_p = sub.add_parser("block", help="Read one measuring block snapshot")
    block_p.add_argument("number", type=parse_int_auto)

    live_p = sub.add_parser("live", help="Poll one or more measuring blocks")
    live_p.add_argument("blocks", nargs="+", type=parse_int_auto)
    live_p.add_argument("--interval", type=float, default=1.0)
    live_p.add_argument("--count", type=int, default=0)
    live_p.add_argument("--raw", action="store_true", help="Include raw KWP response in live line")
    live_p.add_argument("--csv", action="store_true", help="Write live samples to CSV")

    scan_p = sub.add_parser("scan-blocks", help="Scan measuring block range")
    scan_p.add_argument("--start", type=parse_int_auto, default=0)
    scan_p.add_argument("--end", type=parse_int_auto, default=80)
    scan_p.add_argument("--delay", type=float, default=0.05)
    scan_p.add_argument("--show-empty", action="store_true")
    scan_p.add_argument("--show-negative", action="store_true")

    tpl = sub.add_parser("dtc-template", help="Write starter DTC CSV")
    tpl.add_argument("path")

    sub.add_parser("freeze", help="Experimental raw freeze-frame/fault-environment probe")
    sub.add_parser("readiness", help="Experimental raw readiness probe")

    discover_setup_p = sub.add_parser("discover-setup", help="Send safe TP2.0 setup-only probes for one module")
    discover_setup_p.add_argument("module", help="Address/name/part number, e.g. 19, gateway, 17, instruments")
    discover_setup_p.add_argument("--timeout", type=float, default=0.7)
    discover_setup_p.add_argument("--engine-reference", action="store_true", help="Also probe engine 0x01 first as a known-good reference")

    discover_session_p = sub.add_parser("discover-session", help="Try safe KWP StartDiagnosticSession candidates for one module")
    discover_session_p.add_argument("module", help="Address/name/part number, e.g. 03, abs")
    discover_session_p.add_argument("--candidates", default=",".join(f"0x{x:02X}" for x in DEFAULT_SESSION_CANDIDATES), help="Comma-separated sessions, e.g. 0x89,0x81,0x85")
    discover_session_p.add_argument("--timeout", type=float, default=2.0)

    probe_module_p = sub.add_parser("probe-module", help="Read-only TP2.0/KWP probe for one non-engine module")
    probe_module_p.add_argument("module", help="Address/name/part number, e.g. 19, gateway, 17, instruments")
    probe_module_p.add_argument("--no-ident", action="store_true", help="Skip identification requests")
    probe_module_p.add_argument("--no-dtcs", action="store_true", help="Skip DTC read requests")
    probe_module_p.add_argument("--optional-ident", action="store_true", help="Also try extra VCDS-observed/legacy ident IDs")
    probe_module_p.add_argument("--dtc-variants", action="store_true", help="Also try non-primary DTC read variants after 18 02 FF 00")
    probe_module_p.add_argument("--no-session-open", action="store_true", help="Open TP2.0 channel but skip KWP StartDiagnosticSession before read-only probes")

    module_dtc_p = sub.add_parser("module-dtc", help="Read DTCs from a profiled non-engine module")
    module_dtc_p.add_argument("module", help="Address/name, e.g. 03, abs, 17, instruments, 46")

    module_ident_p = sub.add_parser("module-ident", help="Read identification from a profiled non-engine module")
    module_ident_p.add_argument("module", help="Address/name, e.g. 03, abs, 17, instruments, 46")
    module_ident_p.add_argument("--optional-ident", action="store_true", help="Also try extra VCDS-observed/legacy ident IDs")

    cmd_p = sub.add_parser("cmd", help="Send arbitrary short KWP command")
    cmd_p.add_argument("bytes", nargs="+")

    return parser


def verbosity_from_args(args) -> str:
    if args.silent:
        return "silent"
    if args.trace:
        return "trace"
    if args.detail:
        return "detail"
    return "normal"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    colour = Colour(enabled=(not args.no_colour) and (args.force_colour or sys.stdout.isatty()))
    logger = RunLogger(enabled=not args.no_log, log_dir=args.log_dir, action=args.action)
    reporter = Reporter(colour=colour, logger=logger, verbosity=verbosity_from_args(args))
    if logger.error:
        reporter.warn(f"Logging disabled: {logger.error}")
        reporter.info("Tip: fix local log permissions with: sudo chown -R $USER:$USER logs")
    elif logger.ownership_warning:
        reporter.warn(logger.ownership_warning)
    csv_logger = None
    ecu = None

    try:
        reporter.header("BKD TP2.0/KWP diagnostic tool")
        reporter.info(f"Interface: {args.iface}")
        reporter.info(f"Bitrate: {args.bitrate} bit/s")
        reporter.info("Target: Address 01 Engine / BKD EDC16 TP2.0/KWP")
        if logger.path:
            reporter.info(f"Log file: {logger.path}")

        db = DtcDatabase.built_in()
        db.load_csv(args.dtc_db, reporter=reporter)

        labels = None
        if args.label_file:
            labels = parse_label_file(args.label_file)
            if labels.readable:
                reporter.ok(
                    f"Loaded label file: {args.label_file} "
                    f"({len(labels.group_names)} group name(s), "
                    f"{sum(len(v) for v in labels.groups.values())} field label(s))"
                )
            else:
                reporter.warn(f"Label file not usable: {args.label_file}: {labels.error}")

        if args.action == "dtc-template":
            db.write_template(args.path)
            reporter.ok(f"Wrote DTC CSV template: {args.path}")
            return 0

        if args.action == "label-info":
            info = parse_label_file(args.path)
            reporter.header("Label file inspection")
            reporter.line(f"Path:      {args.path}")
            reporter.line(f"Readable:  {reporter.colour.green('yes') if info.readable else reporter.colour.red('no')}")
            if info.error:
                reporter.line(f"Reason:    {reporter.colour.yellow(info.error)}")
            if info.readable:
                reporter.line(f"Lines:     {info.raw_line_count}")
                reporter.line(f"Groups:    {len(info.group_names)}")
                reporter.line(f"Fields:    {sum(len(v) for v in info.groups.values())}")
                shown = 0
                for group in sorted(set(info.group_names) | set(info.groups))[:12]:
                    name = info.group_names.get(group, "")
                    reporter.line(f"  {group:03d} {name}")
                    for field, label in sorted(info.groups.get(group, {}).items()):
                        reporter.line(f"    F{field}: {label}")
                    shown += 1
                if shown == 0:
                    reporter.warn("No group/field labels were found in readable text.")
            return 0

        if args.action in ("analyse-trace", "analyze-trace"):
            run_trace_analysis(reporter, args.path, show_raw=args.raw, max_events=args.max_events, json_out=args.json_out)
            return 0

        if args.action == "map-blocks":
            run_map_blocks(reporter)
            return 0

        if args.action == "presets":
            run_list_presets(reporter)
            return 0

        if args.action == "vehicle":
            run_vehicle_profile(reporter, detail=args.detail)
            return 0

        if args.action == "module-info":
            run_module_info(reporter, args.module)
            return 0

        if args.action == "module-plan":
            run_module_probe_plan(reporter)
            return 0

        if args.action == "autoscan-summary":
            run_autoscan_summary(reporter, path=args.path, faults_only=args.faults_only)
            return 0

        if args.action == "autoscan-faults":
            run_autoscan_faults(reporter, path=args.path)
            return 0

        try:
            session = int(args.session, 16)
        except ValueError:
            reporter.fail(f"Invalid session byte: {args.session}")
            return 2

        experimental_actions = ("discover-setup", "discover-session", "probe-module", "module-dtc", "module-ident")
        if args.action in experimental_actions and not args.experimental_module:
            reporter.fail(f"Refusing experimental non-engine module action '{args.action}' without --experimental-module")
            reporter.warn("These actions may open diagnostic sessions on ABS/gateway/cluster/body modules.")
            reporter.info("Use passive VCDS/ODIS capture first where possible: analyse-trace <candump.log>")
            reporter.info("To proceed deliberately: add --experimental-module")
            return 2

        if not args.no_iface_setup:
            reporter.header("CAN interface setup")
            ensure_can_interface(args.iface, args.bitrate, reporter, force=args.force_iface_setup)
        else:
            reporter.warn("Automatic CAN interface setup skipped by --no-iface-setup")

        if args.action in ("live", "preset") and getattr(args, "csv", False):
            csv_logger = CsvLiveLogger(enabled=True, log_dir=args.log_dir)
            if csv_logger.error:
                reporter.warn(f"CSV logging disabled: {csv_logger.error}")
            elif csv_logger.ownership_warning:
                reporter.warn(csv_logger.ownership_warning)

        if args.action == "discover-setup":
            run_setup_discovery(
                iface=args.iface,
                reporter=reporter,
                module_key=args.module,
                timeout=args.timeout,
                include_engine_reference=args.engine_reference,
            )
            return 0

        if args.action == "discover-session":
            candidate_values = [parse_int_auto(x.strip()) for x in args.candidates.split(",") if x.strip()]
            run_session_discovery(
                iface=args.iface,
                reporter=reporter,
                module_key=args.module,
                candidates=candidate_values,
                timeout=args.timeout,
            )
            return 0

        logical_address = 0x01
        module_profile = None
        open_kwargs = {"logical_address": logical_address}
        if args.action in ("probe-module", "module-dtc", "module-ident"):
            logical_address, module_profile = resolve_module_address(args.module)
            open_kwargs = module_open_kwargs(args.module)

        ecu = TP20KWP(iface=args.iface, reporter=reporter, **open_kwargs)
        start_session = not (args.action == "probe-module" and args.no_session_open)
        open_session = module_session(module_profile, fallback=session) if args.action in ("probe-module", "module-dtc", "module-ident") else session
        ecu.open(session=open_session, start_session=start_session)

        if args.action == "read":
            run_read(ecu, reporter, parse_hex_items(args.cmd), db)
        elif args.action == "clear":
            if not args.yes_clear:
                reporter.fail("Refusing to clear faults without --yes-clear")
                return 2
            run_clear(ecu, reporter, parse_hex_items(args.cmd))
        elif args.action == "quick":
            run_quick(
                ecu, reporter,
                parse_hex_items(args.read_cmd),
                parse_hex_items(args.clear_cmd),
                db,
                yes_clear=args.yes_clear,
                no_prompt=args.no_prompt,
            )
        elif args.action == "ident":
            run_ident(ecu, reporter)
        elif args.action in ("engine-check", "mot-check"):
            run_engine_check(ecu, reporter, db, labels=labels)
        elif args.action == "selftest":
            run_selftest(ecu, reporter, db, labels=labels)
        elif args.action == "block":
            run_block(ecu, reporter, args.number, labels=labels)
        elif args.action == "live":
            run_live(ecu, reporter, args.blocks, args.interval, args.count, args.raw, csv_logger, labels=labels)
        elif args.action == "preset":
            run_preset(ecu, reporter, args.name, args.interval, args.count, args.raw, csv_logger, labels=labels)
        elif args.action == "scan-blocks":
            run_scan_blocks(ecu, reporter, args.start, args.end, args.delay, args.show_empty, args.show_negative, labels=labels)
        elif args.action == "freeze":
            run_freeze_probe(ecu, reporter)
        elif args.action == "readiness":
            run_readiness_probe(ecu, reporter, labels=labels)
        elif args.action == "probe-module":
            run_read_only_probe(
                ecu,
                reporter,
                args.module,
                db,
                ident=not args.no_ident,
                dtcs=not args.no_dtcs,
                optional_ident=args.optional_ident,
                dtc_variants=args.dtc_variants,
            )
        elif args.action == "module-dtc":
            run_module_dtc(ecu, reporter, args.module, db)
        elif args.action == "module-ident":
            run_module_ident(ecu, reporter, args.module, include_optional=args.optional_ident)
        elif args.action == "cmd":
            run_cmd(ecu, reporter, parse_hex_items(args.bytes))
        else:
            parser.error(f"Unhandled action: {args.action}")

        return 0

    except KeyboardInterrupt:
        reporter.warn("Interrupted by user")
        return 130
    except Exception as exc:
        reporter.fail(str(exc))
        return 1
    finally:
        if ecu:
            try:
                # ABS/ESP visibly enters diagnostic communication during active
                # read-only access. Give it a VCDS-like quiet/close window so
                # lamps are less likely to remain flashing until an ignition
                # cycle. This is transport-only cleanup; no KWP services are
                # sent.
                if module_profile and module_profile.address == "03":
                    reporter.warn("ABS/ESP close: draining transport traffic before TP2.0 A8 close")
                    ecu.graceful_close(pre_drain=0.8, post_drain=1.8)
            except Exception as close_exc:
                reporter.warn(f"ABS/ESP graceful close failed/ignored: {close_exc}")
            ecu.close()
        if csv_logger:
            csv_logger.close()
            if csv_logger.path:
                reporter.ok(f"CSV live log saved: {csv_logger.path}")
        if logger.path:
            reporter.ok(f"Session log saved: {logger.path}")
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())

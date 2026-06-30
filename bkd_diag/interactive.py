from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import subprocess

from .commands import run_block, run_clear, run_ident, run_live, run_quick_auto, run_engine_read_auto, run_trace_analysis, run_module_block, run_module_live, run_hvac_catalogue
from .dtc import DtcDatabase, status_bit_text
from .kwp import decode_negative
from .labels import LabelStore
from .hvac_blocks import hvac_label_store
from .module_probe import (
    module_open_kwargs,
    module_session,
    resolve_module_profile,
    run_module_dtc,
    run_module_ident,
)
from .reporting import CsvLiveLogger, Reporter
from .utils import fmt, parse_int_auto
from .tp20 import TP20KWP
from .vehicle_profile import ModuleProfile, find_module

ENGINE_CLEAR_CMD = [0x14, 0xFF, 0x00]
PROVEN_MODULES = ["01", "03", "08", "17", "19", "44", "46"]
ENGINE_BLOCK_SHORTCUTS = [3, 10, 11]


@dataclass(frozen=True)
class InteractiveContext:
    iface: str
    session: int
    experimental_module: bool
    db: DtcDatabase
    labels: LabelStore | None = None
    bitrate: int = 500000
    log_dir: str = "logs"


def _prompt_choice(prompt: str = "Select") -> str:
    return input(f"{prompt}: ").strip()


def _pause() -> None:
    input("\nPress Enter to continue...")


def _menu_item(reporter: Reporter, number: str, text: str, note: str | None = None) -> None:
    c = reporter.colour
    line = f"{c.cyan(number + '.')} {text}"
    if note:
        line += " " + c.dim(note)
    reporter.line(line)


def _status_text(reporter: Reporter, text: str, state: str) -> str:
    c = reporter.colour
    if state == "ok":
        return c.green(text)
    if state == "warn":
        return c.yellow(text)
    if state == "bad":
        return c.red(text)
    return c.dim(text)


def _quiet_reporter(reporter: Reporter) -> Reporter:
    # Used by interactive Auto-Scan summary mode. Protocol details are still
    # available by running start with --detail or by using direct commands.
    return Reporter(
        colour=reporter.colour,
        logger=None,
        verbosity="silent",
        redact_private=getattr(reporter, "redact_private", False),
    )


def _dtc_summary_lines(resp: bytes, db: DtcDatabase, reporter: Reporter | None = None) -> list[str]:
    c = reporter.colour if reporter else None

    def colour(method: str, text: str) -> str:
        return getattr(c, method)(text) if c else text

    if not resp:
        return [colour("red", "DTCs: no response")]

    neg = decode_negative(resp)
    if neg:
        svc, code, name = neg
        return [colour("yellow", f"DTC read negative response: service=0x{svc:02X} code=0x{code:02X} {name}")]

    if resp[0] != 0x58:
        return [colour("red", f"DTC read unexpected response: {fmt(resp)}")]

    if len(resp) < 2:
        return [colour("red", "DTC response 0x58 was truncated before count byte")]

    count = resp[1]
    if count == 0:
        return [colour("green", "DTCs: none")]

    records = resp[2:]
    lines = [colour("yellow", f"DTCs: {count} record(s)")]
    expected = count * 3
    if len(records) < expected:
        lines.append("  " + colour("red", f"incomplete response: expected {expected} record byte(s), got {len(records)}"))
        if records:
            lines.append("  " + colour("dim", f"raw partial: {fmt(records)}"))
        return lines

    for idx in range(0, expected, 3):
        hi, lo, status = records[idx], records[idx + 1], records[idx + 2]
        dtc_num = (hi << 8) | lo
        known = db.lookup.get(dtc_num, {})
        desc = known.get("description") or "Unknown in local lookup table"
        pcode = known.get("pcode") or ""
        prefix = f"  {dtc_num:05d} / 0x{dtc_num:04X}"
        if pcode:
            prefix += f" / {pcode}"
        lines.append(f"{colour('yellow', prefix)}: {colour('bold', desc)}  {colour('dim', f'status=0x{status:02X}')}" )
        bits = status_bit_text(status)
        if bits:
            lines.append("    " + colour("dim", "status bits: ") + colour("yellow", ", ".join(bits)))
    return lines

def _print_autoscan_module_summary(reporter: Reporter, db: DtcDatabase, module: ModuleProfile | None, address: str, resp: bytes | None, error: Exception | None = None) -> None:
    c = reporter.colour
    title = _module_title(module, address)
    reporter.line("")
    reporter.line(c.bold(c.cyan(title)))
    if module:
        part = module.part_number or "unknown"
        reporter.line(f"  {c.dim('Part No:')} {c.green(part) if part != 'unknown' else c.dim(part)}")
    if error is not None:
        reporter.warn(f"  scan failed: {error}")
        return
    if resp is None:
        reporter.warn("  no DTC response captured")
        return
    for line in _dtc_summary_lines(resp, db, reporter=reporter):
        reporter.line("  " + line if not line.startswith("  ") else line)

def _module_title(module: ModuleProfile | None, key: str) -> str:
    if module:
        return f"{module.address} {module.name}"
    return key


def _is_engine(module: ModuleProfile | None, key: str) -> bool:
    return (module.address if module else key.strip().upper().zfill(2)) == "01"


def _open_engine(ctx: InteractiveContext, reporter: Reporter):
    ecu = TP20KWP(iface=ctx.iface, reporter=reporter, logical_address=0x01)
    ecu.open(session=ctx.session, start_session=True)
    return ecu


def _open_module(ctx: InteractiveContext, reporter: Reporter, key: str):
    logical, module = resolve_module_profile(key)
    open_kwargs = module_open_kwargs(key)
    ecu = TP20KWP(iface=ctx.iface, reporter=reporter, **open_kwargs)
    ecu.open(session=module_session(module, fallback=ctx.session), start_session=True)
    return ecu, module


def _close_module(ecu, reporter: Reporter, module: ModuleProfile | None) -> None:
    try:
        if module and module.address == "03":
            reporter.warn("ABS/ESP close: draining transport traffic before TP2.0 A8 close")
            ecu.graceful_close(pre_drain=0.8, post_drain=1.8)
    except Exception as exc:
        reporter.warn(f"ABS/ESP graceful close failed/ignored: {exc}")
    finally:
        ecu.close()


def _run_engine_action(ctx: InteractiveContext, reporter: Reporter, action: str):
    # Measuring-block menus are interactive: do not open the TP2.0 channel
    # before prompting. The engine ECU will close an idle channel with A8 while
    # the user is choosing presets/intervals, which made v0.4.3 live mode fail
    # on the first block. Open a fresh short session only when a block read or
    # live run is actually started.
    if action == "block":
        return _engine_measuring_blocks(ctx, reporter)

    ecu = None
    try:
        ecu = _open_engine(ctx, reporter)
        if action == "ident":
            return run_ident(ecu, reporter)
        elif action == "dtc":
            return run_engine_read_auto(ecu, reporter, ctx.db)
        elif action == "quick":
            return run_quick_auto(ecu, reporter, ENGINE_CLEAR_CMD, ctx.db, yes_clear=False, no_prompt=False)
        elif action == "clear":
            reporter.warn("This clears engine ECU DTCs only. It does not clear non-engine modules.")
            answer = input("Type CLEAR 01 to clear Engine DTCs: ").strip()
            if answer != "CLEAR 01":
                reporter.warn("Clear skipped.")
                return
            return run_clear(ecu, reporter, ENGINE_CLEAR_CMD)
        else:
            raise RuntimeError(f"Unknown engine action: {action}")
    finally:
        if ecu:
            ecu.close()


def _run_module_action(ctx: InteractiveContext, reporter: Reporter, key: str, action: str):
    logical, module = resolve_module_profile(key)
    if not module:
        raise RuntimeError(f"Unknown module: {key}")

    if module.address != "01" and not ctx.experimental_module:
        reporter.fail("Non-engine active module access is disabled without --experimental-module.")
        reporter.info("Restart with: --experimental-module start")
        return

    if action == "block" and module.address == "08":
        return _hvac_measuring_blocks(ctx, reporter)

    ecu = None
    try:
        ecu, module = _open_module(ctx, reporter, key)
        if action == "ident":
            return run_module_ident(ecu, reporter, key, include_optional=False)
        elif action == "dtc":
            return run_module_dtc(ecu, reporter, key, ctx.db)
        elif action == "clear":
            reporter.fail(f"Clear DTCs is disabled for {module.name} / module {module.address} in this build.")
            reporter.warn("Only Engine 01 clear is currently enabled from the interactive menu.")
        elif action == "block":
            reporter.fail(f"Measuring blocks for {module.name} / module {module.address} are not implemented yet.")
            reporter.info("08 Auto HVAC is the first non-engine module with safe measuring-block replay support.")
        else:
            raise RuntimeError(f"Unknown module action: {action}")
    finally:
        if ecu:
            _close_module(ecu, reporter, module)


def _parse_block_list(raw: str) -> list[int] | None:
    blocks: list[int] = []
    for token in raw.replace(",", " ").split():
        try:
            blocks.append(parse_int_auto(token) & 0xFF)
        except ValueError:
            return None
    return blocks or None


def _prompt_live_options(reporter: Reporter) -> tuple[float, int] | None:
    raw_interval = _prompt_choice("Interval seconds [1.0]")
    raw_count = _prompt_choice("Sample cycles, 0 = until Ctrl+C [0]")
    try:
        interval = float(raw_interval) if raw_interval else 1.0
        count = int(raw_count, 0) if raw_count else 0
    except ValueError:
        reporter.warn("Invalid interval/count.")
        return None
    if interval <= 0:
        reporter.warn("Interval must be positive.")
        return None
    if count < 0:
        reporter.warn("Sample count cannot be negative.")
        return None
    return interval, count


def _run_live_from_menu(ctx: InteractiveContext, reporter: Reporter, blocks: list[int]) -> None:
    opts = _prompt_live_options(reporter)
    if opts is None:
        _pause()
        return
    interval, count = opts
    csv_answer = _prompt_choice("Write CSV live log? [y/N]").lower()
    csv_logger = None
    if csv_answer in ("y", "yes"):
        csv_logger = CsvLiveLogger(enabled=True, log_dir=ctx.log_dir)
        if csv_logger.error:
            reporter.warn(f"CSV logging disabled: {csv_logger.error}")
            csv_logger = None
        elif csv_logger.ownership_warning:
            reporter.warn(csv_logger.ownership_warning)
    reporter.info("Live engine measuring blocks. Press Ctrl+C to stop and return to this menu.")
    ecu = None
    try:
        # Open after all prompts, so the ECU is not left idle while the user is
        # deciding which live preset/interval to use.
        ecu = _open_engine(ctx, reporter)
        run_live(
            ecu,
            reporter,
            blocks,
            interval=interval,
            count=count,
            include_raw=False,
            csv_logger=csv_logger,
            labels=ctx.labels,
            dashboard=True,
        )
    except KeyboardInterrupt:
        reporter.warn("Live measuring stopped by user.")
    finally:
        if ecu:
            ecu.close()
        if csv_logger:
            csv_logger.close()
            if csv_logger.path:
                reporter.ok(f"CSV live log saved: {csv_logger.path}")
    _pause()


def _run_block_snapshot_from_menu(ctx: InteractiveContext, reporter: Reporter, block: int) -> None:
    ecu = None
    try:
        ecu = _open_engine(ctx, reporter)
        run_block(ecu, reporter, block, labels=ctx.labels)
    finally:
        if ecu:
            ecu.close()
    _pause()


def _hvac_labels(ctx: InteractiveContext) -> LabelStore:
    if ctx.labels is not None and ctx.labels.readable:
        return ctx.labels
    return hvac_label_store()


def _run_hvac_block_snapshot_from_menu(ctx: InteractiveContext, reporter: Reporter, block: int) -> None:
    ecu = None
    module = None
    try:
        ecu, module = _open_module(ctx, reporter, "08")
        run_module_block(ecu, reporter, "08", block, labels=_hvac_labels(ctx))
    finally:
        if ecu:
            _close_module(ecu, reporter, module)
    _pause()


def _run_hvac_multi_snapshot_from_menu(ctx: InteractiveContext, reporter: Reporter, blocks: list[int]) -> None:
    ecu = None
    module = None
    try:
        ecu, module = _open_module(ctx, reporter, "08")
        for block in blocks:
            run_module_block(ecu, reporter, "08", block, labels=_hvac_labels(ctx))
    finally:
        if ecu:
            _close_module(ecu, reporter, module)
    _pause()


def _run_hvac_live_from_menu(ctx: InteractiveContext, reporter: Reporter, blocks: list[int]) -> None:
    opts = _prompt_live_options(reporter)
    if opts is None:
        _pause()
        return
    interval, count = opts
    csv_answer = _prompt_choice("Write CSV live log? [y/N]").lower()
    csv_logger = None
    if csv_answer in ("y", "yes"):
        csv_logger = CsvLiveLogger(enabled=True, log_dir=ctx.log_dir)
        if csv_logger.error:
            reporter.warn(f"CSV logging disabled: {csv_logger.error}")
            csv_logger = None
        elif csv_logger.ownership_warning:
            reporter.warn(csv_logger.ownership_warning)

    ecu = None
    module = None
    try:
        ecu, module = _open_module(ctx, reporter, "08")
        run_module_live(
            ecu,
            reporter,
            "08",
            blocks,
            interval=interval,
            count=count,
            include_raw=False,
            csv_logger=csv_logger,
            labels=_hvac_labels(ctx),
            dashboard=True,
        )
    except KeyboardInterrupt:
        reporter.warn("Live HVAC measuring stopped by user.")
    finally:
        if ecu:
            _close_module(ecu, reporter, module)
        if csv_logger:
            csv_logger.close()
            if csv_logger.path:
                reporter.ok(f"CSV live log saved: {csv_logger.path}")
    _pause()


def _hvac_measuring_blocks(ctx: InteractiveContext, reporter: Reporter) -> None:
    while True:
        reporter.header("08 Auto HVAC measuring blocks")
        reporter.warn("Read-only VCDS-observed 21 xx measuring-block reads only. No output tests, coding, adaptations or clears.")
        _menu_item(reporter, "1", "Show HVAC measured-value catalogue")
        _menu_item(reporter, "2", "Snapshot useful overview", "001 006 007 008 009")
        _menu_item(reporter, "3", "Live useful overview", "001 006 007 008 009")
        _menu_item(reporter, "4", "Live flap positions", "011 012 013 014 015 016")
        _menu_item(reporter, "5", "Snapshot group 009 rear-window heater")
        _menu_item(reporter, "6", "Custom block snapshot")
        _menu_item(reporter, "7", "Custom live blocks")
        _menu_item(reporter, "8", "Back")
        choice = _prompt_choice()

        if choice in ("8", "b", "back", "q", "quit"):
            return
        if choice == "1":
            run_hvac_catalogue(reporter)
            _pause()
            continue
        if choice == "2":
            _run_hvac_multi_snapshot_from_menu(ctx, reporter, [1, 6, 7, 8, 9])
            continue
        if choice == "3":
            _run_hvac_live_from_menu(ctx, reporter, [1, 6, 7, 8, 9])
            continue
        if choice == "4":
            _run_hvac_live_from_menu(ctx, reporter, [11, 12, 13, 14, 15, 16])
            continue
        if choice == "5":
            _run_hvac_block_snapshot_from_menu(ctx, reporter, 9)
            continue
        if choice == "6":
            raw = _prompt_choice("Block number, e.g. 009")
            try:
                block = parse_int_auto(raw)
            except ValueError:
                reporter.warn("Invalid block number.")
                _pause()
                continue
            _run_hvac_block_snapshot_from_menu(ctx, reporter, block)
            continue
        if choice == "7":
            raw = _prompt_choice("Blocks, e.g. 001 006 009")
            blocks = _parse_block_list(raw)
            if not blocks:
                reporter.warn("Invalid block list.")
                _pause()
                continue
            _run_hvac_live_from_menu(ctx, reporter, blocks)
            continue
        reporter.warn("Unknown selection.")
        _pause()


def _engine_measuring_blocks(ctx: InteractiveContext, reporter: Reporter) -> None:
    while True:
        reporter.header("Engine measuring blocks")
        _menu_item(reporter, "1", "Live core preset", "001 003 004 011")
        _menu_item(reporter, "2", "Live air/boost preset", "003 010 011")
        _menu_item(reporter, "3", "Live custom blocks")
        _menu_item(reporter, "4", "Block 003 - air/EGR snapshot")
        _menu_item(reporter, "5", "Block 010 - air/pressure snapshot")
        _menu_item(reporter, "6", "Block 011 - boost control snapshot")
        _menu_item(reporter, "7", "Custom block snapshot")
        _menu_item(reporter, "8", "Back")
        choice = _prompt_choice()

        if choice in ("8", "b", "back", "q", "quit"):
            return
        if choice == "1":
            _run_live_from_menu(ctx, reporter, [1, 3, 4, 11])
            continue
        if choice == "2":
            _run_live_from_menu(ctx, reporter, [3, 10, 11])
            continue
        if choice == "3":
            raw = _prompt_choice("Blocks, e.g. 003 010 011")
            blocks = _parse_block_list(raw)
            if not blocks:
                reporter.warn("Invalid block list.")
                _pause()
                continue
            _run_live_from_menu(ctx, reporter, blocks)
            continue
        if choice in ("4", "5", "6"):
            _run_block_snapshot_from_menu(ctx, reporter, ENGINE_BLOCK_SHORTCUTS[int(choice) - 4])
            continue
        if choice == "7":
            raw = _prompt_choice("Block number, e.g. 003")
            try:
                block = parse_int_auto(raw)
            except ValueError:
                reporter.warn("Invalid block number.")
                _pause()
                continue
            _run_block_snapshot_from_menu(ctx, reporter, block)
            continue
        reporter.warn("Unknown selection.")
        _pause()


def _print_module_status(reporter: Reporter, module: ModuleProfile, experimental_enabled: bool) -> None:
    c = reporter.colour
    if module.address in PROVEN_MODULES:
        read_status = c.green("proven")
    else:
        read_status = c.dim("not profiled")
    if module.address != "01" and not experimental_enabled:
        read_status += c.dim("; requires --experimental-module")

    clear_status = c.green("enabled") if module.address == "01" else c.red("disabled")
    if module.address == "01":
        block_status = c.green("engine live/snapshot")
    elif module.address == "08":
        block_status = c.green("HVAC read-only") if experimental_enabled else c.dim("HVAC read-only; needs --experimental-module")
    else:
        block_status = c.yellow("not implemented")

    reporter.line(f"Read DTCs:        {read_status}")
    reporter.line(f"Clear DTCs:       {clear_status}")
    reporter.line(f"Measuring blocks: {block_status}")
    if module.address == "03":
        reporter.line("Notes:            " + c.yellow("ABS/ESP graceful close enabled"))
    if module.address == "46":
        reporter.line("Notes:            " + c.yellow("split DTC response handling enabled"))

def _select_module(ctx: InteractiveContext, reporter: Reporter) -> None:
    while True:
        reporter.header("Select module")
        for idx, address in enumerate(PROVEN_MODULES, 1):
            module = find_module(address)
            if module:
                marker = "" if (address == "01" or ctx.experimental_module) else "  [needs --experimental-module]"
                number = str(idx)
                name = reporter.colour.bold(f"{module.address} {module.name}")
                _menu_item(reporter, number, name, marker.strip() if marker else None)
        _menu_item(reporter, str(len(PROVEN_MODULES) + 1), "Back")
        choice = _prompt_choice()

        if choice in (str(len(PROVEN_MODULES) + 1), "b", "back", "q", "quit"):
            return
        try:
            module_key = PROVEN_MODULES[int(choice) - 1]
        except (ValueError, IndexError):
            # Also allow direct typing: 03, abs, gateway, etc.
            module = find_module(choice)
            if not module or module.address not in PROVEN_MODULES:
                reporter.warn("Unknown module selection.")
                _pause()
                continue
            module_key = module.address

        _module_menu(ctx, reporter, module_key)


def _module_menu(ctx: InteractiveContext, reporter: Reporter, key: str) -> None:
    module = find_module(key)
    if not module:
        reporter.warn(f"Unknown module: {key}")
        return

    while True:
        reporter.header(f"Module {_module_title(module, key)}")
        _print_module_status(reporter, module, ctx.experimental_module)
        reporter.line("")
        _menu_item(reporter, "1", "Read identification")
        _menu_item(reporter, "2", "Read DTCs")
        _menu_item(reporter, "3", "Clear DTCs")
        _menu_item(reporter, "4", "Measuring blocks")
        _menu_item(reporter, "5", "Back")
        choice = _prompt_choice()

        if choice in ("5", "b", "back", "q", "quit"):
            return

        try:
            if module.address == "01":
                action = {"1": "ident", "2": "dtc", "3": "clear", "4": "block"}[choice]
                _run_engine_action(ctx, reporter, action)
            else:
                action = {"1": "ident", "2": "dtc", "3": "clear", "4": "block"}[choice]
                _run_module_action(ctx, reporter, module.address, action)
        except KeyError:
            reporter.warn("Unknown selection.")
        except KeyboardInterrupt:
            reporter.warn("Interrupted; returning to module menu.")
        except Exception as exc:
            reporter.fail(str(exc))
        _pause()


def _autoscan_read_only(ctx: InteractiveContext, reporter: Reporter) -> None:
    modules = list(PROVEN_MODULES)
    if not ctx.experimental_module:
        reporter.warn("Autoscan will read Engine 01 only because --experimental-module was not supplied.")
        modules = ["01"]
    else:
        reporter.warn("Read-only autoscan opens each proven module and reads DTCs. No clears/coding/adaptations are sent.")
        answer = input("Type READ ONLY to continue: ").strip()
        if answer != "READ ONLY":
            reporter.warn("Autoscan skipped.")
            return

    # Default to a concise workshop report. Run with --detail or --trace if the
    # transport/preamble dialogue is what you are debugging.
    show_protocol = reporter.verbosity >= 2
    work_reporter = reporter if show_protocol else _quiet_reporter(reporter)

    reporter.header("Auto-Scan read-only summary")
    if not show_protocol:
        reporter.info("Protocol details hidden; run start with --detail for the full TP2.0/KWP dialogue.")

    for address in modules:
        module = find_module(address)
        resp = None
        error = None
        try:
            if address == "01":
                resp = _run_engine_action(ctx, work_reporter, "dtc")
            else:
                resp = _run_module_action(ctx, work_reporter, address, "dtc")
        except KeyboardInterrupt:
            reporter.warn("Autoscan interrupted by user.")
            return
        except Exception as exc:
            error = exc
        _print_autoscan_module_summary(reporter, ctx.db, module, address, resp, error)
        if address == "03" and error is None:
            reporter.line("  Close: ABS/ESP graceful close path used")


def _run_ip_command(args: list[str], reporter: Reporter) -> bool:
    cmd = ["ip"] + args
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True
    except FileNotFoundError:
        reporter.fail("ip command not found. Install iproute2 or restore CAN interface manually.")
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        reporter.fail(f"ip command failed: {' '.join(cmd)}")
        if err:
            reporter.warn(err)
    return False


def _set_can_listen_only(ctx: InteractiveContext, reporter: Reporter) -> bool:
    reporter.header("CAN listen-only setup")
    reporter.warn("Passive capture mode only. Do not run active diagnostics while VCDS/ODIS is connected.")
    if not _run_ip_command(["link", "set", ctx.iface, "down"], reporter):
        return False
    if not _run_ip_command(["link", "set", ctx.iface, "type", "can", "bitrate", str(ctx.bitrate), "listen-only", "on"], reporter):
        return False
    if not _run_ip_command(["link", "set", ctx.iface, "up"], reporter):
        return False
    reporter.ok(f"{ctx.iface} set to {ctx.bitrate} bit/s listen-only")
    return True


def _restore_can_active(ctx: InteractiveContext, reporter: Reporter) -> bool:
    reporter.header("Restore CAN active mode")
    ok = True
    ok = _run_ip_command(["link", "set", ctx.iface, "down"], reporter) and ok
    ok = _run_ip_command(["link", "set", ctx.iface, "type", "can", "bitrate", str(ctx.bitrate)], reporter) and ok
    ok = _run_ip_command(["link", "set", ctx.iface, "up"], reporter) and ok
    if ok:
        reporter.ok(f"{ctx.iface} restored to active {ctx.bitrate} bit/s mode")
    return ok


def _safe_capture_name(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw.strip())
    return cleaned.strip("._-") or "capture"


def _passive_vcds_capture(ctx: InteractiveContext, reporter: Reporter, default_stem: str | None = None, guide_lines: list[str] | None = None) -> None:
    if shutil.which("candump") is None:
        reporter.fail("candump not found. Install can-utils first.")
        return

    reporter.header("Passive VCDS splitter capture")
    reporter.warn("Connect the Linux adapter through the splitter in listen-only mode.")
    reporter.warn("Start VCDS after this capture starts. Stop capture with Ctrl+C.")
    if guide_lines:
        for line in guide_lines:
            reporter.info(line)
    default_name = default_stem or ("vcds_capture_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    name = _prompt_choice(f"Capture filename stem [{default_name}]") or default_name
    stem = _safe_capture_name(name)
    out_dir = Path("captures")
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{stem}.log"

    if path.exists():
        reporter.fail(f"Refusing to overwrite existing capture: {path}")
        return

    if not _set_can_listen_only(ctx, reporter):
        return

    proc = None
    try:
        reporter.header("Capture running")
        reporter.info(f"Writing: {path}")
        reporter.info("Press Ctrl+C to stop and restore active CAN mode")
        proc = subprocess.Popen(
            ["candump", "-tz", "-x", ctx.iface],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with path.open("w", encoding="utf-8") as f:
            assert proc.stdout is not None
            for line in proc.stdout:
                f.write(line)
                f.flush()
                reporter.line(line.rstrip("\n"), log=False)
    except KeyboardInterrupt:
        reporter.warn("Capture stopped by user.")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        _restore_can_active(ctx, reporter)
        if path.exists():
            reporter.ok(f"Capture saved: {path}")


def _guided_measuring_block_capture(ctx: InteractiveContext, reporter: Reporter) -> None:
    reporter.header("Guided VCDS measuring-block capture")
    module = _prompt_choice("VCDS module address, e.g. 08") or "08"
    group = _prompt_choice("Measuring block group, e.g. 001") or "001"
    scenario = _prompt_choice("Scenario note, e.g. idle_blower_low_high") or "measuring_block"
    module_clean = _safe_capture_name(module.zfill(2))
    group_clean = _safe_capture_name(group.zfill(3))
    scenario_clean = _safe_capture_name(scenario)
    default_stem = f"vcds_{module_clean}_group{group_clean}_{scenario_clean}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    guide = [
        f"In VCDS open Address {module_clean} and Measuring Blocks group {group_clean}.",
        "Capture idle/baseline first, then change one physical state, then return to baseline.",
        "For HVAC examples: blower low/high, temperature LO/HI, A/C on/off, recirc on/off.",
        "Stop capture with Ctrl+C, then analyse the trace and compare raw payload changes.",
    ]
    _passive_vcds_capture(ctx, reporter, default_stem=default_stem, guide_lines=guide)


def _analyse_trace_menu(ctx: InteractiveContext, reporter: Reporter) -> None:
    reporter.header("Analyse existing trace")
    path = _prompt_choice("Path to candump log")
    if not path:
        reporter.warn("No path supplied.")
        return
    json_answer = _prompt_choice("Write JSON summary too? [y/N]").lower()
    json_out = None
    if json_answer in ("y", "yes"):
        src = Path(path)
        json_out = str(src.with_suffix(src.suffix + ".summary.json"))
    run_trace_analysis(reporter, path, show_raw=False, max_events=0, json_out=json_out)


def _show_capture_checklist(reporter: Reporter) -> None:
    reporter.header("Passive capture checklist")
    reporter.line("1. Linux adapter must be listen-only when VCDS/ODIS is also connected.")
    reporter.line("2. Do not run active bkd-tp20-diag commands while VCDS/ODIS is connected.")
    reporter.line("3. Start candump first, then open the module/action in VCDS.")
    reporter.line("4. Capture one thing at a time: module open, DTC read, one measuring block group, etc.")
    reporter.line("5. Stop with Ctrl+C, restore active CAN mode, then run analyse-trace.")
    reporter.line("6. Keep captures private; they may include VIN/module serial data.")


def _capture_tools_menu(ctx: InteractiveContext, reporter: Reporter) -> None:
    while True:
        reporter.header("Capture / trace tools")
        _menu_item(reporter, "1", "Passive VCDS splitter capture")
        _menu_item(reporter, "2", "Guided VCDS measuring-block capture")
        _menu_item(reporter, "3", "Analyse existing trace")
        _menu_item(reporter, "4", "Show capture checklist")
        _menu_item(reporter, "5", f"Restore {ctx.iface} active {ctx.bitrate // 1000}k mode")
        _menu_item(reporter, "6", "Back")
        choice = _prompt_choice()
        try:
            if choice == "1":
                _passive_vcds_capture(ctx, reporter)
                _pause()
            elif choice == "2":
                _guided_measuring_block_capture(ctx, reporter)
                _pause()
            elif choice == "3":
                _analyse_trace_menu(ctx, reporter)
                _pause()
            elif choice == "4":
                _show_capture_checklist(reporter)
                _pause()
            elif choice == "5":
                _restore_can_active(ctx, reporter)
                _pause()
            elif choice in ("6", "b", "back", "q", "quit"):
                return
            else:
                reporter.warn("Unknown selection.")
                _pause()
        except KeyboardInterrupt:
            reporter.warn("Interrupted; returning to capture menu.")

def run_interactive_start(ctx: InteractiveContext, reporter: Reporter) -> None:
    reporter.header("Interactive start menu")
    reporter.info("Existing direct CLI commands still work; this menu is a safer wrapper around proven paths.")
    if not ctx.experimental_module:
        reporter.warn("Non-engine modules are visible but disabled until you restart with --experimental-module.")

    while True:
        reporter.header("Main menu")
        _menu_item(reporter, "1", "Auto-Scan read-only")
        _menu_item(reporter, "2", "Select module")
        _menu_item(reporter, "3", "Engine quick check")
        _menu_item(reporter, "4", "Engine measuring blocks")
        _menu_item(reporter, "5", "Capture / trace tools")
        _menu_item(reporter, "6", "Exit")
        choice = _prompt_choice()

        try:
            if choice == "1":
                _autoscan_read_only(ctx, reporter)
                _pause()
            elif choice == "2":
                _select_module(ctx, reporter)
            elif choice == "3":
                _run_engine_action(ctx, reporter, "quick")
                _pause()
            elif choice == "4":
                _run_engine_action(ctx, reporter, "block")
            elif choice == "5":
                _capture_tools_menu(ctx, reporter)
            elif choice in ("6", "q", "quit", "exit"):
                reporter.ok("Goodbye.")
                return
            else:
                reporter.warn("Unknown selection.")
                _pause()
        except KeyboardInterrupt:
            reporter.warn("Interrupted; returning to main menu.")
        except EOFError:
            reporter.warn("Input closed; exiting.")
            return

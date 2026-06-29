from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import ANSI_RE, fmt


VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact_private_text(text: str) -> str:
    """Redact common private identifiers from user-visible output and logs.

    The primary target is live VIN output. Email redaction is included for
    pasted notes/report paths that may contain account details. Raw CAN hex is
    intentionally not decoded/redacted here.
    """
    text = VIN_RE.sub("[REDACTED-VIN]", text)
    text = EMAIL_RE.sub("[REDACTED-EMAIL]", text)
    return text

LEVELS = {
    "silent": 0,
    "normal": 1,
    "detail": 2,
    "trace": 3,
}


def _sudo_owner() -> tuple[int, int] | None:
    """Return the real user behind sudo, if this process is running as sudo/root.

    The diagnostic commands often need sudo for CAN interface setup. Without this,
    ./logs and the generated log files end up owned by root, then later non-sudo
    helper commands cannot write logs.
    """
    if os.name != "posix":
        return None

    try:
        if os.geteuid() != 0:
            return None
    except AttributeError:
        return None

    uid_s = os.environ.get("SUDO_UID")
    gid_s = os.environ.get("SUDO_GID")
    if not uid_s or not gid_s:
        return None

    try:
        uid = int(uid_s)
        gid = int(gid_s)
    except ValueError:
        return None

    if uid <= 0:
        return None

    return uid, gid


def _is_safe_local_log_path(path: Path) -> bool:
    """Only auto-chown local project-style log paths, not arbitrary system dirs."""
    try:
        if not path.is_absolute():
            return True

        resolved = path.resolve()
        cwd = Path.cwd().resolve()
        try:
            return resolved == cwd or resolved.is_relative_to(cwd)
        except AttributeError:  # Python 3.9 compatibility
            return str(resolved) == str(cwd) or str(resolved).startswith(str(cwd) + os.sep)
    except OSError:
        return False


def _reown_for_sudo_user(path: str | Path) -> str | None:
    """Chown a local log path back to the original sudo user.

    Returns an error string instead of raising; logging must never stop diagnostics.
    """
    owner = _sudo_owner()
    if owner is None:
        return None

    p = Path(path)
    if not _is_safe_local_log_path(p):
        return None

    try:
        os.chown(p, owner[0], owner[1])
    except OSError as exc:
        return str(exc)

    return None



class Colour:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def c(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def red(self, text: str) -> str: return self.c("31", text)
    def green(self, text: str) -> str: return self.c("32", text)
    def yellow(self, text: str) -> str: return self.c("33", text)
    def blue(self, text: str) -> str: return self.c("34", text)
    def magenta(self, text: str) -> str: return self.c("35", text)
    def cyan(self, text: str) -> str: return self.c("36", text)
    def bold(self, text: str) -> str: return self.c("1", text)
    def dim(self, text: str) -> str: return self.c("2", text)


class RunLogger:
    def __init__(self, enabled: bool = True, log_dir: str = "logs", action: str = "run"):
        self.enabled = enabled
        self.path: str | None = None
        self.file = None
        self.error: str | None = None
        self.ownership_warning: str | None = None

        if not enabled:
            return

        try:
            log_dir_path = Path(log_dir)
            os.makedirs(log_dir_path, exist_ok=True)

            chown_error = _reown_for_sudo_user(log_dir_path)
            if chown_error:
                self.ownership_warning = f"Could not set log directory owner: {chown_error}"

            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            safe_action = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in action)
            self.path = str(log_dir_path / f"bkd_{stamp}_{safe_action}.log")
            self.file = open(self.path, "w", encoding="utf-8")

            chown_error = _reown_for_sudo_user(self.path)
            if chown_error and not self.ownership_warning:
                self.ownership_warning = f"Could not set log file owner: {chown_error}"

        except OSError as exc:
            # Diagnostics should still run if logging is not writable.
            self.enabled = False
            self.path = None
            self.file = None
            self.error = str(exc)

    def write(self, text: str = "") -> None:
        if self.file:
            self.file.write(ANSI_RE.sub("", text) + "\n")
            self.file.flush()

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None


class Reporter:
    def __init__(self, colour: Colour, logger: RunLogger | None = None, verbosity: str = "normal", redact_private: bool = False):
        if verbosity not in LEVELS:
            raise ValueError(f"Unknown verbosity: {verbosity}")
        self.colour = colour
        self.logger = logger
        self.verbosity_name = verbosity
        self.verbosity = LEVELS[verbosity]
        self.redact_private = redact_private

    def line(self, text: str = "", level: int = 1, log: bool = True) -> None:
        if self.redact_private:
            text = redact_private_text(text)
        if self.verbosity >= level:
            print(text, flush=True)
        if log and self.logger:
            self.logger.write(text)

    def trace(self, text: str) -> None:
        self.line(text, level=3)

    def detail(self, text: str = "") -> None:
        self.line(text, level=2)

    def header(self, text: str) -> None:
        self.line("", level=1)
        self.line(self.colour.bold(self.colour.cyan(f"== {text} ==")), level=1)

    def info(self, text: str) -> None:
        self.line(self.colour.cyan("• ") + text, level=1)

    def ok(self, text: str) -> None:
        self.line(self.colour.green("✓ ") + text, level=1)

    def warn(self, text: str) -> None:
        self.line(self.colour.yellow("! ") + text, level=1)

    def fail(self, text: str) -> None:
        self.line(self.colour.red("✗ ") + text, level=0)


class CsvLiveLogger:
    def __init__(self, enabled: bool = False, log_dir: str = "logs"):
        self.path: str | None = None
        self.file = None
        self.writer = None
        self.error: str | None = None
        self.ownership_warning: str | None = None

        if not enabled:
            return

        try:
            log_dir_path = Path(log_dir)
            os.makedirs(log_dir_path, exist_ok=True)

            chown_error = _reown_for_sudo_user(log_dir_path)
            if chown_error:
                self.ownership_warning = f"Could not set log directory owner: {chown_error}"

            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
            self.path = str(log_dir_path / f"bkd_{stamp}_live.csv")
            self.file = open(self.path, "w", encoding="utf-8", newline="")
            self.writer = csv.writer(self.file)
            self.writer.writerow([
                "timestamp", "block", "field", "label", "type", "raw",
                "value_u16", "value_s16", "decoded_value", "unit", "kind", "status"
            ])

            chown_error = _reown_for_sudo_user(self.path)
            if chown_error and not self.ownership_warning:
                self.ownership_warning = f"Could not set CSV log owner: {chown_error}"

        except OSError as exc:
            self.path = None
            self.file = None
            self.writer = None
            self.error = str(exc)

    def write_sample(self, timestamp: str, block_num: int, fields: list[dict[str, Any]], text_value: str | None = None) -> None:
        if not self.writer:
            return

        if text_value is not None:
            self.writer.writerow([
                timestamp, f"{block_num:03d}", "", "text", "", "", "", "",
                text_value, "text", "text/version", "text",
            ])
            self.file.flush()
            return

        for field in fields:
            decoded = field.get("decoded")
            self.writer.writerow([
                timestamp,
                f"{block_num:03d}",
                field.get("index", ""),
                field.get("label", ""),
                f"0x{field['type']:02X}" if "type" in field else "",
                fmt(field.get("raw", b"")),
                field.get("unsigned", ""),
                field.get("signed", ""),
                decoded.get("value") if decoded else "",
                decoded.get("unit") if decoded else "",
                decoded.get("kind") if decoded else "",
                field.get("status", ""),
            ])

        self.file.flush()

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None

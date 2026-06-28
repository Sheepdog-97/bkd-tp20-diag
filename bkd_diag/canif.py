from __future__ import annotations

import shutil
import subprocess

from .reporting import Reporter


def can_interface_status(iface: str) -> str:
    if shutil.which("ip") is None:
        raise RuntimeError("Could not find the `ip` command from iproute2")

    proc = subprocess.run(
        ["ip", "-details", "link", "show", "dev", iface],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"CAN interface {iface!r} not found or not readable: {detail}")
    return proc.stdout


def can_interface_looks_up(status_text: str) -> bool:
    first_line = status_text.splitlines()[0] if status_text.splitlines() else ""
    return "<" in first_line and "UP" in first_line.split(">", 1)[0]


def can_interface_has_bitrate(status_text: str, bitrate: int) -> bool:
    return f"bitrate {int(bitrate)}" in status_text


def run_ip_command(args: list[str]) -> None:
    proc = subprocess.run(["ip"] + args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        if "Operation not permitted" in detail or "RTNETLINK answers: Operation not permitted" in detail:
            raise RuntimeError(
                "Permission denied while configuring CAN interface. "
                "Run with sudo, or grant CAP_NET_ADMIN to Python."
            )
        raise RuntimeError(f"`ip {' '.join(args)}` failed: {detail}")


def ensure_can_interface(iface: str, bitrate: int, reporter: Reporter, force: bool = False) -> None:
    bitrate = int(bitrate)
    status = can_interface_status(iface)
    is_up = can_interface_looks_up(status)
    has_bitrate = can_interface_has_bitrate(status, bitrate)

    if is_up and has_bitrate and not force:
        reporter.ok(f"CAN interface {iface} already up at {bitrate} bit/s")
        return

    if is_up and not has_bitrate:
        reporter.warn(f"CAN interface {iface} is up but does not appear to be at {bitrate} bit/s")
    elif not is_up:
        reporter.info(f"CAN interface {iface} is down; bringing it up at {bitrate} bit/s")
    elif force:
        reporter.info(f"Force-reconfiguring CAN interface {iface} at {bitrate} bit/s")

    run_ip_command(["link", "set", iface, "down"])
    run_ip_command(["link", "set", iface, "type", "can", "bitrate", str(bitrate)])
    run_ip_command(["link", "set", iface, "up"])

    status_after = can_interface_status(iface)
    if not can_interface_looks_up(status_after):
        raise RuntimeError(f"Tried to bring {iface} up, but it still does not look UP")

    reporter.ok(f"CAN interface {iface} configured at {bitrate} bit/s")

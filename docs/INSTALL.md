# Install and setup

## Recommended first run: no install

On modern Debian/Ubuntu systems, system Python is often externally managed by the distribution. That means this may fail:

```bash
python3 -m pip install -e .
```

with an `externally-managed-environment` / PEP 668 error.

For this project, you do **not** need to install anything to run the tool from the project directory:

```bash
cd bkd_tp20_project
python3 -m bkd_diag.cli --help
python3 -m bkd_diag.cli --no-log presets
```

Active CAN commands can also be run directly:

```bash
sudo python3 -m bkd_diag.cli --iface can0 ident
sudo python3 -m bkd_diag.cli --iface can0 quick
```

This is the simplest and safest development workflow.

## Optional venv install

Use this only if you specifically want the `bkd-diag` console command.

```bash
cd bkd_tp20_project
sudo apt install python3-venv python3-full -y
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
bkd-diag --help
```

When using `sudo`, call the venv Python explicitly:

```bash
sudo .venv/bin/python -m bkd_diag.cli --iface can0 ident
sudo .venv/bin/bkd-diag --iface can0 ident
```

Do not use `--break-system-packages` for normal development.

## Requirements

- Linux with SocketCAN
- Python 3.10+ recommended
- `iproute2` tools: `ip`
- `can-utils` for capture work: `candump`, `cansend`
- A SocketCAN-compatible CAN adapter
- OBD pigtail, breakout, or splitter

Useful system packages:

```bash
sudo apt update
sudo apt install can-utils iproute2 git -y
```

Add venv support only if needed:

```bash
sudo apt install python3-venv python3-full -y
```

## CAN setup

The tool can bring `can0` up automatically for active diagnostic commands when run with `sudo`:

```bash
sudo python3 -m bkd_diag.cli --iface can0 ident
```

Manual active setup:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
```

Confirm state:

```bash
ip -details link show can0
```

## DSD / simple CAN-USB wiring

Typical OBD diagnostic CAN wiring:

```text
OBD pin 6   CAN-H
OBD pin 14  CAN-L
OBD pin 4/5 ground
OBD pin 16  +12 V only if your adapter needs vehicle power
```

The DSD adapter used during development was USB-powered, so pin 16 was not required.

## Passive listen-only sniff mode

Use this with an OBD splitter when VCDS/ODIS is the active tester and the Linux CAN adapter is only sniffing:

```bash
mkdir -p captures
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only on
sudo ip link set can0 up
candump -tz -x can0 | tee captures/vcds_03_abs_open_faults.log
```

Return to active mode before using this tool for active diagnostics:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
```

## Log ownership

Commands normally run with `sudo`, but generated local `logs/` files should be handed back to the original sudo user. If you have old root-owned logs from earlier versions, fix them once:

```bash
sudo chown -R "$USER:$USER" logs
```

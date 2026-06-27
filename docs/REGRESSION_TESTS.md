# Known-good regression test sequence

This is the v0.3.7/v0.3.8 pre-splitter regression sequence. It checks offline commands, trace parsing, engine diagnostics, live CSV logging, log ownership, and experimental-module guardrails.

Run from the project directory:

```bash
cd bkd_tp20_project
```

## 1. Offline tests

No car and no sudo required:

```bash
python3 -m bkd_diag.cli --help
python3 -m bkd_diag.cli --no-log presets
python3 -m bkd_diag.cli --no-log map-blocks
python3 -m bkd_diag.cli --no-log vehicle --detail
python3 -m bkd_diag.cli --no-log module-info 01
python3 -m bkd_diag.cli --no-log module-info 03
python3 -m bkd_diag.cli --no-log module-info 56
python3 -m bkd_diag.cli --no-log autoscan-faults
```

Trace analyser:

```bash
python3 -m bkd_diag.cli --no-log analyse-trace examples/sample_abs_tp20_trace.log
python3 -m bkd_diag.cli --no-log analyse-trace examples/sample_abs_tp20_trace.log --raw --max-events 8
python3 -m bkd_diag.cli --no-log analyse-trace examples/sample_abs_tp20_trace.log --json-out /tmp/sample_abs_summary.json
cat /tmp/sample_abs_summary.json
```

Expected JSON should include:

```json
"tester_to_ecu_can_id": "0x790"
```

Expected service counts include:

```text
StartDiagnosticSession request
ReadDTC request
ReadDTC positive response
```

## 2. Experimental guard

This should refuse and should not touch CAN:

```bash
python3 -m bkd_diag.cli --no-iface-setup --no-log probe-module 03
```

Expected:

```text
Refusing experimental non-engine module action 'probe-module' without --experimental-module
```

## 3. Engine live smoke tests

Car connected, ignition on, diagnostic CAN adapter on OBD pins 6/14:

```bash
sudo python3 -m bkd_diag.cli --iface can0 ident
sudo python3 -m bkd_diag.cli --iface can0 quick
sudo python3 -m bkd_diag.cli --iface can0 engine-check
sudo python3 -m bkd_diag.cli --iface can0 block 3
sudo python3 -m bkd_diag.cli --iface can0 block 11
```

Expected:

```text
TP2.0 channel setup accepted
TP2.0 channel parameters accepted
KWP session opened: 10 89 → 50 89
```

Engine identity should decode live from the car. Example development ECU:

```text
03G 906 016 AJ
7341
028 101 173 0
R4 2,0L EDC G000SG
```

Expected no-fault quick result:

```text
No DTCs reported by the engine ECU
```

## 4. Live preset and CSV logging

```bash
sudo python3 -m bkd_diag.cli --iface can0 preset boost --count 3 --interval 0.5 --csv
ls -la logs | tail
find logs -maxdepth 1 -type f -user root -print
```

Expected:

- live block 010/011 lines print
- a `*_live.csv` file is created
- a `*_preset.log` file is created
- no new root-owned log/CSV files are printed by the `find` command

If older logs are root-owned from previous versions:

```bash
sudo chown -R "$USER:$USER" logs
```

## 5. Trace mode sanity

```bash
sudo python3 -m bkd_diag.cli --iface can0 --trace block 11
```

Expected raw TP2.0/KWP sequence includes setup, channel params, session open, block request, and close.

## 6. Active experimental guard with sudo

This should still refuse unless deliberately unlocked:

```bash
sudo python3 -m bkd_diag.cli --iface can0 probe-module 03
```

Expected:

```text
Refusing experimental non-engine module action 'probe-module' without --experimental-module
```

Do not add `--experimental-module` until after passive VCDS/ODIS capture has been reviewed.

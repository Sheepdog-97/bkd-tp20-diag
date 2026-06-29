# Known-good regression test sequence

This is the v0.4.5 regression sequence. It checks offline commands, trace parsing,
engine diagnostics, VCDS-derived read-only module diagnostics, log ownership,
experimental-module guardrails, and privacy checks.

Run from the project directory:

```bash
cd ~/github/bkd-tp20-diag
```

## 1. Offline tests

No car and no sudo required:

```bash
python3 -m compileall -q bkd_diag
python3 -m bkd_diag.cli --help
python3 -m bkd_diag.cli --no-log presets
python3 -m bkd_diag.cli --no-log map-blocks
python3 -m bkd_diag.cli --no-log vehicle --detail
python3 -m bkd_diag.cli --no-log module-plan
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 01
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 03
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 08
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 17
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 19
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 44
python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 46
python3 -m bkd_diag.cli --no-log autoscan-faults
printf '6\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup start
printf '1\nNO\n\n6\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup --experimental-module start
printf '5\n3\n\n5\n6\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup start
printf '6\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup --redact-private start
printf '6\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup --force-colour start
printf '6\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup --no-colour start
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

These should refuse and should not touch CAN:

```bash
python3 -m bkd_diag.cli --no-iface-setup --no-log probe-module 03
python3 -m bkd_diag.cli --no-iface-setup --no-log module-dtc 03
python3 -m bkd_diag.cli --no-iface-setup --no-log module-ident 17
```

Expected:

```text
Refusing experimental non-engine module action
```

## 3. Engine live smoke tests

Car connected, ignition on, diagnostic CAN adapter on OBD pins 6/14:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 ident
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 quick
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 engine-check
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 block 3
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 block 11
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
No DTCs reported by engine ECU
```

## 4. Live preset and CSV logging

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 preset boost --count 3 --interval 0.5 --csv
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
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --trace block 11
```

Expected raw TP2.0/KWP sequence includes setup, channel params, session open, block
request, and close.

## 6. Active read-only module regression

Parked only, stable battery, no VCDS/ODIS connected, one command at a time:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 08
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 17
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 44
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 19
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 46
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 03
```

Known-good live results on the development vehicle:

```text
08 Auto HVAC:           DTC 00229 / raw 00 E5 / status 0x62 observed
17 Instruments:         no DTCs observed
44 Steering Assist:     no DTCs observed
19 CAN Gateway:         DTCs 01305 / 01304 observed
46 Central Convenience: DTC 01135 / raw 04 6F / status 0x24 observed
03 ABS Brakes:          no DTCs observed; ABS/ESP lamps should not remain flashing after exit
```

For ABS, expected clean-exit wording includes:

```text
ABS/ESP close: draining transport traffic before TP2.0 A8 close
```

If ABS/ESP lamps remain flashing after exit, cycle ignition and stop active ABS
testing until the close path is reviewed.

Do not run clear, coding, adaptation, basic settings or output tests as part of this
regression set.

## 6. Interactive menu smoke test

Parked only. This checks the v0.4.0 menu wrapper without changing the proven
direct CLI paths. Start without `--experimental-module` first to confirm
non-engine modules are visibly gated:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 start
```

Then start with the gate enabled and use the menu to select one known-good
module, read DTCs, and exit:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module start
```

Recommended first interactive path:

```text
Select module -> 08 Auto HVAC -> Read DTCs -> Back -> Exit
```

Non-engine clear DTC and non-engine measuring blocks should display disabled/not
implemented messages in this build.

## 7. Privacy and publish checks

```bash
git grep -nE 'YOUR_REAL_VIN|YOUR_REG|your-name|your-email|your-handle' || echo "No tracked personal strings found"
git ls-files | grep -E 'logs|captures|private|\.venv|egg-info|__pycache__' || echo "No private/generated paths tracked"
```

## v0.5.0 checks

Direct read-only Auto-Scan should be available and able to write all report formats:

```bash
python3 -m bkd_diag.cli --no-log --no-iface-setup autoscan --help
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module --redact-private autoscan \
  --txt-out reports/autoscan.txt \
  --json-out reports/autoscan.json \
  --md-out reports/autoscan.md
```

Interactive live engine measuring blocks should offer CSV logging and show current,
min, max, and delta values in dashboard mode:

```text
start -> Engine measuring blocks -> Live air/boost preset
```

Guided VCDS measuring-block capture should be visible under:

```text
start -> Capture / trace tools -> Guided VCDS measuring-block capture
```

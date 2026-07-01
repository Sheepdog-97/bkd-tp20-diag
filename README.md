# BKD TP2.0 Diagnostic Tool

Linux SocketCAN diagnostic tool for VW/SEAT/Audi/Skoda TP2.0 transport carrying
KWP2000, developed against a SEAT Leon 1P / PQ35 BKD 2.0 TDI EDC16 engine ECU.

This is not a universal VAG scanner. The stable supported target is **Engine 01**
on the BKD EDC16 ECU. From v0.7.0, Engine 01 DTC reads go through a small
identity-based profile resolver so proven TP2.0/KWP engine families can add their
own read-only DTC strategy without changing transport code. Several non-engine
PQ35 modules are now proven on the development car for **read-only identification
and DTC reads**, but they remain explicitly gated and vehicle-specific.

This project is **TP2.0/KWP2000 over CAN only**. It does not speak KW1281/K-line,
so MK4-era cars/controllers such as early EDC15 ASZ/038906019 setups are outside
the current transport scope.

License: **GPL-3.0-or-later**. See `LICENSE`.

## Current status

Current package version: **v0.8.1**.


| Area | Status |
|---|---|
| Engine 01 BKD EDC16 | Stable/useful |
| Engine DTC read | Profile-resolved; BKD/EDC16 and captured MED9.5.10 variant supported |
| Engine DTC clear | Proven, explicit confirmation required |
| ECU identification | Proven |
| Measuring blocks | Proven for useful BKD groups; labels are still conservative |
| Live CSV logging | Working |
| Engine live measuring-block dashboard | Working in interactive menu |
| 08 Auto HVAC measured values | Read-only group catalogue/live dashboard working for captured groups |
| Passive CAN correlation | Offline candidate finder from diagnostic CSV truth + candump trace |
| 03 ABS Brakes | Read-only active DTC/ID proven; ABS/ESP clean close tested in v0.3.16 |
| 08 Auto HVAC | Read-only active DTC/ID proven; observed DTC 00229 / 0x00E5 |
| 17 Instruments | Read-only active DTC/ID proven |
| 19 CAN Gateway | Read-only active DTC/ID proven; observed DTCs 01304/01305 |
| 44 Steering Assist | Read-only active DTC/ID proven; safety-sensitive |
| 46 Central Convenience | Read-only active DTC/ID proven; split DTC response merge tested, observed 01135 / 0x046F |
| Airbag/immobilizer/other modules | Do not actively probe unless you understand the risk |

## Supported development vehicle profile

Public example data is anonymised.

| Item | Value |
|---|---|
| Platform | SEAT Leon 1P / PQ35 |
| Engine | BKD 2.0 TDI |
| Engine ECU | `03G 906 016 AJ` |
| ECU family | Bosch EDC16 |
| Protocol proven | VW TP2.0 + KWP2000 over CAN |
| OBD CAN | 500 kbit/s on pins 6/14 |
| Example VIN | `VSSZZZ1PZ6R000000` anonymised |

## Engine profile resolver

Engine 01 is opened the same way, but DTC reads are now selected from a tiny
evidence-based resolver:

```text
03G906016 / EDC / BKD    -> BKD / EDC16       -> 18 02 FF 00
03C906056 / MED9         -> MED9.5.10 petrol  -> 18 00 FF 00
unknown TP2.0/KWP engine -> conservative fallback, read-only only
```

List the built-in rules:

```bash
python3 -m bkd_diag.cli --no-log engine-profiles
```

Detect the connected Engine 01 profile using read-only identity requests:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 engine-profile
```

Adding another engine family should mean adding one profile entry after a VCDS or
ODIS capture proves the identity match and DTC-read variant. Do not add guessed
write/clear/coding behaviour.

## Passive CAN correlation

`correlate` is an offline helper for finding passive CAN signal candidates from
diagnostic CSV truth. It is the bridge between active workshop diagnostics and a
passive Open MMI runtime.

Example: use HVAC group 001 vehicle speed as truth and compare it to a passive
`candump` trace:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --truth-field "Vehicle Speed" \
  --can captures/passive_speed_drive.log \
  --md-out captures/speed_candidates.md \
  --json-out captures/speed_candidates.json
```

List available numeric truth fields first:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --can captures/passive_speed_drive.log \
  --list-truth-fields
```


Run the guided validation profile after a paired HVAC live CSV and passive Open MMI comfort/infotainment `candump` capture. For this project the passive tablet bus is 100 kbit/s; the diagnostic truth side remains 500 kbit/s:

```bash
python3 -m bkd_diag.cli --no-log passive-validate \
  --truth latest \
  --can latest \
  --profile pq35-infotainment
```

This finds the timing offset from the confirmed dimmer anchor and validates the known dimmer, blower-load and vehicle-speed signals in one Markdown/JSON report.

Tablet passive capture setup for the Open MMI comfort/infotainment bus:

```bash
sudo ip link set can0 down 2>/dev/null || true
sudo ip link set can0 type can bitrate 100000 listen-only on
sudo ip link set can0 up

candump -tz -x can0 | tee captures/comfort_validation_$(date +%Y%m%d_%H%M%S).log
```


The helper skips known TP2.0/KWP diagnostic CAN IDs by default so it does not
rediscover its own active measuring-block responses. Results are candidates, not
proof; validate with a second capture before using a signal.

See `docs/PASSIVE_CORRELATION.md`.

## Safety

This is experimental vehicle diagnostic software. Use at your own risk.

Mature/safe default scope:

```text
Engine 01 only:
  read faults
  clear faults only with explicit confirmation
  read identification
  read measuring blocks
  live/CSV logging
```

Direct non-engine module commands are refused unless you add `--experimental-module`.
The interactive menu asks for a typed read-only confirmation when you enter a
non-engine module path, so normal menu startup can stay short. The profiled
03/08/17/19/44/46 modules have been proven on the development car for read-only
identification and DTC reads, but they are still not a universal VAG compatibility
claim.

ABS/ESP can visibly enter diagnostic communication during an active session. From
v0.3.16 the tool performs a VCDS-like drain/close path for ABS; if ABS/ESP lamps
remain flashing after a run, cycle ignition and stop active ABS testing until the
exit path is reviewed.

Do not operate a laptop while driving. For road logging, have a second person handle
the laptop.

See `docs/SAFETY.md`.

## Install

Run from the project directory:

```bash
python3 -m bkd_diag.cli --help
```

Optional editable install:

```bash
python3 -m pip install -e .
bkd-diag --help
```

See `docs/INSTALL.md` for SocketCAN setup, DSD wiring, and listen-only sniff mode.


## Interactive start menu

For normal workshop use, start the interactive menu instead of copying individual
commands from the docs. The menu now starts offline-safe: it does not configure
`can0` until you choose a live diagnostic/capture action.

```bash
python3 -m bkd_diag.cli start
```

The menu asks whether to redact private identifiers at startup. Non-engine module
paths ask for typed read-only confirmation at the moment you enter them, so the
old normal startup flags are no longer needed for menu use. Use `sudo` only when
you are about to run live CAN actions and your local SocketCAN permissions require it.

The menu is module-first:

```text
Main menu
  Auto-Scan read-only
  Select module
  Engine quick check
  Engine measuring blocks
  Capture / trace tools

Module menu
  Read identification
  Read DTCs
  Clear DTCs
  Measuring blocks
```

Current interactive scope:

| Module/action | Status |
|---|---|
| Engine 01 read DTCs | Enabled |
| Engine 01 clear DTCs | Enabled with typed confirmation |
| Engine 01 measuring block snapshots | Enabled for known/custom groups |
| 03/08/17/19/44/46 read identification | Menu asks for read-only confirmation; direct commands still need `--experimental-module` |
| 03/08/17/19/44/46 read DTCs | Menu asks for read-only confirmation; direct commands still need `--experimental-module` |
| Non-engine clear DTCs | Disabled in this build |
| 08 Auto HVAC measuring blocks | Menu asks for read-only confirmation; direct commands still need `--experimental-module`; read-only catalogue/live dashboard |
| Other non-engine measuring blocks | Disabled until VCDS captures prove labels/behaviour |

Auto-Scan from the menu is concise by default. Start with `--detail` if you want
the full TP2.0/KWP protocol dialogue during Auto-Scan:

```bash
python3 -m bkd_diag.cli --detail start
```

Direct CLI commands still accept `--redact-private` and `--experimental-module` for
scripting. The interactive menu prompts for those decisions instead.

The original direct CLI commands remain available for scripting and regression
testing.

## Core engine commands

```bash
sudo python3 -m bkd_diag.cli --iface can0 ident
sudo python3 -m bkd_diag.cli --iface can0 quick
sudo python3 -m bkd_diag.cli --iface can0 engine-check
sudo python3 -m bkd_diag.cli --iface can0 mot-check

sudo python3 -m bkd_diag.cli --iface can0 block 3
sudo python3 -m bkd_diag.cli --iface can0 block 11
sudo python3 -m bkd_diag.cli --iface can0 live 3 11 --interval 1 --csv
sudo python3 -m bkd_diag.cli --iface can0 scan-blocks --start 0 --end 80
```

`engine-check` / `mot-check` are read-only snapshots. They report engine DTC state,
VIN/ECU identity, MAF/EGR block 003, boost block 011, and raw/candidate readiness
block 017.

## Output modes

Default mode is readable and does not print raw TX/RX frames.

```bash
sudo python3 -m bkd_diag.cli --iface can0 selftest
```

More detail:

```bash
sudo python3 -m bkd_diag.cli --iface can0 --detail block 11
```

Full raw trace:

```bash
sudo python3 -m bkd_diag.cli --iface can0 --trace block 11
```

Quiet mode:

```bash
sudo python3 -m bkd_diag.cli --iface can0 --silent quick
```

## Presets

```bash
python3 -m bkd_diag.cli presets
sudo python3 -m bkd_diag.cli --iface can0 preset core --count 1
sudo python3 -m bkd_diag.cli --iface can0 preset boost --interval 0.5 --csv
sudo python3 -m bkd_diag.cli --iface can0 preset road --interval 0.5 --csv
```

Current presets:

```text
core       001 003 004 011
air        003 010 011
boost      010 011
injectors  013 018 023
startup    001 004 005 012 051
cooling    062 063 064
cruise     009 022 028
readiness  017
version    080 081 082
road       003 010 011
```

See `docs/WORKFLOWS.md` for “road log boost”, “MAF/EGR check”, and “before MOT”
workflows. See `docs/REGRESSION_TESTS.md` for the known-good test sequence.

## Trace capture and analysis

Passive VCDS/ODIS capture is the preferred way to learn non-engine module dialects.
From v0.4.2, the interactive menu uses semantic ANSI colour for clean/pass, warning/DTC, disabled/risky and heading states. Use `--no-colour` / `--no-color` for plain output, or `--force-colour` / `--force-color` when piping to a terminal that supports ANSI.

From v0.4.5, `Engine measuring blocks` in the interactive menu supports live polling for the proven engine presets and custom block lists. Non-engine measuring blocks remain disabled until VCDS-captured module block requests are added.

From v0.4.1, the interactive menu has `Capture / trace tools` for guided listen-only
capture and trace analysis. The manual equivalent is:

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only on
sudo ip link set can0 up

candump -tz -x can0 | tee captures/vcds_03_abs_open_faults.log
```

Analyse the trace:

```bash
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log --raw --max-events 120
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log --json-out captures/vcds_03_abs_summary.json
```

Test the analyser without a car:

```bash
python3 -m bkd_diag.cli --no-log analyse-trace examples/sample_abs_tp20_trace.log --json-out /tmp/sample_abs_summary.json
```

See `docs/TRACE_CAPTURE.md`, `docs/SPLITTER_CAPTURE_CHECKLIST.md`, `docs/VCDS_MODULE_PROFILES.md`, and `docs/ENGINE_PROFILES.md`.

## Read-only non-engine modules

Active non-engine access is gated, but VCDS splitter captures plus live active tests
have now proven read-only TP2.0/KWP DTC/ID workflows for 03, 08, 17, 19, 44 and 46
on the development vehicle.

```bash
python3 -m bkd_diag.cli module-plan
python3 -m bkd_diag.cli module-info 17

sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 03
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-ident 17
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module probe-module 46
```

Without `--experimental-module`, active non-engine commands stop before CAN setup.
These commands are read-only: no clear, coding, adaptation, output tests or basic
settings.

See `docs/VCDS_MODULE_PROFILES.md`.

## DTC lookup CSV

The tool always reads raw DTCs even if the friendly lookup is missing. Built-in
lookup entries include the BKD MAF/G70 test fault, the captured MED9.5.10 P3078
fault, and observed/confirmed module DTCs from 03 ABS, 08 HVAC, 19 Gateway, and
46 Central Convenience.

Create a starter CSV from the built-in lookup table:

```bash
python3 -m bkd_diag.cli dtc-template dtcs.csv
```

Use an additional CSV:

```bash
sudo python3 -m bkd_diag.cli --iface can0 --dtc-db dtcs.csv quick
```

## Label files

Plain `.lbl` files can provide better labels. Compiled `.clb` files are detected and
skipped because they are not directly parseable.

```bash
python3 -m bkd_diag.cli label-info /path/to/03G-906-016-BKD.lbl
sudo python3 -m bkd_diag.cli --iface can0 --label-file /path/to/03G-906-016-BKD.lbl block 3
```

## Log permissions

Commands that touch the CAN interface often need `sudo`. From v0.3.5, local log dirs
and newly created log/CSV files are handed back to the original sudo user where
possible.

Fix old root-owned logs once with:

```bash
sudo chown -R "$USER:$USER" logs
```

Or skip logs:

```bash
python3 -m bkd_diag.cli --no-log map-blocks
```

## Publishing checklist

See `docs/PUBLISHING.md` and `docs/GITHUB_PUSH.md`.

Do not publish private `logs/`, `captures/`, VINs, registration numbers, customer
names, workshop names, or raw traces that identify a vehicle/customer.


## v0.5.0 workflow additions

### Direct read-only Auto-Scan

Run a live read-only scan from the CLI:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module --redact-private autoscan
```

Export reports:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module --redact-private autoscan \
  --txt-out reports/autoscan.txt \
  --json-out reports/autoscan.json \
  --md-out reports/autoscan.md
```

The live Auto-Scan remains read-only: no clear, coding, adaptation, output tests,
or basic settings are sent.

### Live engine dashboard

The interactive engine measuring-block dashboard now tracks current, min, max,
and delta values. It can also write a CSV log from the menu.

### Guided measuring-block capture

Use:

```text
start -> Capture / trace tools -> Guided VCDS measuring-block capture
```

This is the preferred workflow for learning future HVAC/Instruments/Convenience
measuring blocks from VCDS splitter captures. See
`docs/HVAC_MEASURING_BLOCK_WORKFLOW.md`.


### 08 Auto HVAC measured values

`v0.6.2` adds a read-only HVAC measured-value catalogue and safe measuring-block reads for the profiled 08 Auto HVAC module.

```bash
python3 -m bkd_diag.cli hvac-catalogue

sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli \
  --iface can0 \
  --experimental-module \
  module-block 08 009

sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli \
  --iface can0 \
  --experimental-module \
  module-live 08 001 006 007 008 009 --csv
```

In an interactive terminal `module-live` redraws an in-place dashboard while the
CSV remains the full sample history. Add `--journal` for the older scrolling
sample-by-sample output.

This is read-only diagnostic polling (`21 xx` / `61 xx`) and is intended as an oracle for passive Open MMI signal discovery. It does not add HVAC control, output tests, coding, adaptation, or CAN replay.


### Passive correlation timing anchors

Use a known passive signal to align diagnostic CSV time with a passive `candump`
trace before ranking unknown candidates. For PQ35 comfort/infotainment CAN at 100 kbit/s, the
seeded dimmer anchor is:

```text
0x470 byte[2] u8 = dimming Terminal 58d percentage
```

Example: calculate the offset from the dimmer truth field, then apply it to a
vehicle-speed search in the same capture pair:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --truth-field "001.F3 Vehicle Speed" \
  --can captures/comfort_passive_YYYY.log \
  --known-signal dimmer_470_b2 \
  --auto-offset \
  --window 1.0 \
  --md-out captures/speed_candidates_aligned.md
```

List seeded signals:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --can captures/comfort_passive_YYYY.log \
  --list-known-signals
```

Validated PQ35 signals currently include:

- `dimmer_470_b2`: `0x470 byte[2]` = dimmer percent.
- `blower_3e1_b4`: `0x3E1 byte[4]` = HVAC blower/turbine load, `raw * 100 / 255`.
- `speed_351_u16le_b1_200`, `speed_527_u16le_b1_200`, `speed_359_u16le_b1_200`: vehicle speed, `u16le[1:3] / 200 km/h`.

Unvalidated seeds remain passive research data until validated by a second
capture with deliberate state changes.


## Open MMI export

After a successful passive validation report, generate a reviewable Open MMI comfort-bus overlay:

```bash
python3 -m bkd_diag.cli --no-log openmmi-export \
  --validation latest \
  --out-dir exports/openmmi \
  --include-speed-duplicates
```

The export is offline/passive only and targets the PQ35 comfort/infotainment CAN (`can0`, 100 kbit/s, listen-only recommended).

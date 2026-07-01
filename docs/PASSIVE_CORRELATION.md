# Passive CAN correlation helper

`correlate` is an offline helper for turning active diagnostic truth into passive
CAN signal candidates.

It does **not** inject traffic and it does **not** prove a signal by itself.  It
compares a numeric live diagnostic CSV field, such as HVAC group 001 vehicle
speed, with a passive `candump` trace captured at the same time.

```text
diagnostic CSV truth
  + passive candump
  -> ranked candidate CAN IDs / bytes / scales
```

## Recommended capture pattern

Run a diagnostic live CSV for one clear truth source:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli \
  --iface can0 \
  --experimental-module \
  --redact-private \
  module-live 08 001 --csv
```

In another terminal, capture passive broadcast traffic on the bus segment you want
to map:

```bash
candump -tz -x can0 | tee captures/passive_speed_drive.log
```

Use a simple repeatable pattern.  For speed, for example:

```text
stationary 10s
roll slowly
hold a steady low speed
stop
roll slightly faster
stop
```

Do not operate the laptop while driving.  Use a second person or a safe controlled
workshop/rolling-road setup.

## List truth fields

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --can captures/passive_speed_drive.log \
  --list-truth-fields
```

Example fields:

```text
001.F1 Compressor Shut-Off Code
001.F2 Engine Speed
001.F3 Vehicle Speed
```

## Correlate one field

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --truth-field "Vehicle Speed" \
  --can captures/passive_speed_drive.log \
  --md-out captures/speed_candidates.md \
  --json-out captures/speed_candidates.json
```

The output ranks possible signals and prints a simple linear fit:

```text
truth ≈ slope*raw + intercept
```

For example, a speed candidate with `truth ≈ 0.01*raw + 0` means the passive raw
integer may be centi-km/h.

## Timing options

The helper normalises the first diagnostic CSV sample and first CAN frame to zero.
This works best when both captures start at roughly the same time.

Use these when needed:

```bash
--window 0.50    # accept CAN samples up to ±0.5s from the truth sample
--offset 1.25    # CAN time + 1.25s ~= truth time
```

If no candidates appear, try a larger `--window`, a small positive/negative
`--offset`, or a capture with stronger signal changes.

## Diagnostic IDs are skipped by default

Known TP2.0/KWP diagnostic IDs are skipped by default so the helper does not just
rediscover the active measuring-block responses that produced the CSV.

Use this only for debugging the helper itself:

```bash
--include-diagnostic-ids
```

## Status/boolean fields

For on/off signals, add bit candidates:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --truth-field "Rear Window Heater" \
  --can captures/passive_rear_heater.log \
  --bits \
  --md-out captures/rear_heater_candidates.md
```

## Validation rules

Treat a high correlation as a candidate only.  Before using a signal in Open MMI:

1. Repeat the capture with a different pattern.
2. Filter to the candidate CAN ID and confirm the byte/bit manually.
3. Check that the signal updates when the diagnostic truth updates.
4. Check that unrelated actions do not produce the same shape.
5. Keep Open MMI runtime passive by default.

## Known-signal timing alignment

The first diagnostic CSV sample and first passive CAN frame are normalised to
zero, but in real captures they often start several seconds apart. Use a known
passive signal to find the offset, then apply that offset to unknown signal
searches.

Seeded PQ35 dimmer anchor:

```text
dimmer_470_b2:
  CAN 0x470 byte[2] u8 = dimming Terminal 58d percentage
  expected truth field: 008.F3 Dimming Terminal 58d
```

List seeded signals:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --can captures/infotainment_passive_YYYY.log \
  --list-known-signals
```

Find offset from the dimmer anchor and then search speed candidates with that
same offset:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --truth-field "001.F3 Vehicle Speed" \
  --can captures/infotainment_passive_YYYY.log \
  --known-signal dimmer_470_b2 \
  --auto-offset \
  --window 1.0 \
  --md-out captures/speed_candidates_aligned.md \
  --json-out captures/speed_candidates_aligned.json
```

The offset sweep defaults to `-12:12:0.5`. Override it when needed:

```bash
--offset-sweep -20:20:0.25
```

For direct dimmer validation only:

```bash
python3 -m bkd_diag.cli --no-log correlate \
  --truth logs/bkd_YYYY_live.csv \
  --truth-field "008.F3" \
  --can captures/infotainment_passive_YYYY.log \
  --known-signal dimmer_470_b2 \
  --auto-offset \
  --window 1.0 \
  --can-id 0x470
```

## Seeded candidates

The built-in seed catalogue currently includes:

- `dimmer_470_b2`: confirmed timing anchor, `0x470 byte[2]`.
- `speed_351_b1_candidate`: low-speed vehicle-speed candidate, `0x351 byte[1]`.
- `speed_527_b1_candidate`: duplicate/derived vehicle-speed candidate, `0x527 byte[1]`.
- `blower_3e1_b4_candidate`: HVAC blower/turbine-load candidate, `0x3E1 byte[4]`.

Candidates are not runtime truth. Validate with another capture before adding a
signal to Open MMI.

## Guided passive validation

From v0.8.2, the common PQ35 Open MMI validation workflow is wrapped by
`passive-validate`. It finds the timing offset from the confirmed dimmer anchor,
then validates the known dimmer, blower and speed signals in one report.

```bash
python3 -m bkd_diag.cli --no-log passive-validate \
  --truth latest \
  --can latest \
  --profile pq35-infotainment
```

Equivalent explicit form:

```bash
python3 -m bkd_diag.cli --no-log passive-validate \
  --truth logs/bkd_YYYY_live.csv \
  --can captures/infotainment_validation_YYYY.log \
  --profile pq35-infotainment
```

The interactive wrapper is under:

```text
start -> Capture / trace tools -> Passive CAN validation wizard
```

The profile currently validates:

- `dimmer_470_b2`: `0x470 byte[2]`, dimming Terminal 58d %, raw = percent.
- `blower_3e1_b4`: `0x3E1 byte[4]`, HVAC blower/turbine load %, raw * 100 / 255.
- `speed_351_u16le_b1_200`: `0x351 u16le[1:3] / 200`, vehicle speed km/h.
- `speed_527_u16le_b1_200`: `0x527 u16le[1:3] / 200`, vehicle speed km/h.
- `speed_359_u16le_b1_200`: `0x359 u16le[1:3] / 200`, vehicle speed km/h.

`passive-validate` writes Markdown and JSON reports to `captures/` by default.
Use `--no-report` for a terminal summary only.

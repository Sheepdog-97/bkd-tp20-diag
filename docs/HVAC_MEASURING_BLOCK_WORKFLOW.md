# HVAC measuring-block discovery workflow

This workflow turns VCDS measuring-block traffic into conservative, proven
`bkd-tp20-diag` replay/decoder support. Start with Address 08 Auto HVAC because
it is lower risk than ABS/steering and has useful Open MMI signals.

## Goal

For each candidate HVAC group, collect enough evidence to answer:

- which KWP request VCDS sends
- which response service/group comes back
- which fields change when a real HVAC state changes
- scale/unit where it can be proven
- whether the data is useful for passive CAN correlation later

## Capture setup

Use the interactive menu:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --redact-private start
```

Then choose:

```text
5. Capture / trace tools
2. Guided VCDS measuring-block capture
```

Suggested filename stem format:

```text
vcds_08_group001_idle_blower_low_high_YYYYMMDD_HHMMSS.log
```

The tool will put `can0` into listen-only mode, run `candump`, and restore active
500k mode when stopped with Ctrl+C.

## One capture, one variable

Capture one group and one physical change at a time. For example:

```text
Address 08 Auto HVAC / group 001
  10 seconds baseline
  blower low -> high
  blower high -> low
  10 seconds baseline
```

Good first scenarios:

```text
blower low/high
A/C button off/on
recirculation off/on
temperature LO/HI
fan off/auto/manual
outside temperature stable baseline
```

Avoid changing several controls at once. It makes decoding much harder.

## Analyse

After capture:

```bash
python3 -m bkd_diag.cli analyse-trace captures/<capture>.log --raw --json-out captures/<capture>.summary.json
```

Record:

```text
module address
measuring group
request bytes
response bytes
fields that changed
physical action that caused the change
confidence level
```

## Acceptance criteria before adding support

Do not add a decoded field just because it looks plausible. Add it when:

```text
1. VCDS request/response is captured clearly.
2. The same group can be replayed by bkd-tp20-diag.
3. A field changes with one known real-world action.
4. The change is repeatable in at least two captures or two runs.
5. Unknown scales are labelled raw/candidate, not final units.
```

## Suggested implementation order

```text
v0.5.x   capture and analyse HVAC groups
v0.6.x   replay one known HVAC group with raw fields only
v0.6.x+  add named fields one-by-one as evidence improves
```

Keep non-engine measuring blocks behind `--experimental-module` until the replay
and close behaviour is boring.

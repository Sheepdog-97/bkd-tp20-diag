# Engine 01 profile resolver

The project began as a BKD / EDC16 tool, but PQ35 Engine 01 is still just a
TP2.0/KWP endpoint. Different engine ECU families can use different KWP DTC-read
subfunctions after the same transport/session open.

v0.7.0 adds a deliberately small engine profile resolver:

1. Open Engine 01 via TP2.0/KWP.
2. Read a small identity set with `1A 9B`, `1A 91`, and `1A 86`.
3. Match part/component text against known evidence-backed profiles.
4. Use that profile's read-only DTC request.
5. For unknown profiles, only try a fallback DTC-read variant if the ECU says the
   first request is unsupported.

This is not a Ross-Tech label database and should not try to become one. A new
profile should be added only after a VCDS/ODIS capture proves the ECU identity and
read-only DTC-read behaviour.

## Current profiles

| Profile | Match evidence | DTC read |
|---|---|---|
| `bkd_edc16` | `03G906016`, `EDC`, `BKD` | `18 02 FF 00` |
| `med9_5_10` | `03C906056`, `MED9` | `18 00 FF 00` |

Unknown TP2.0/KWP engines use:

```text
18 02 FF 00
then, only if unsupported:
18 00 FF 00
```

## Commands

List profile rules without touching CAN:

```bash
python3 -m bkd_diag.cli --no-log engine-profiles
```

Detect the connected engine using read-only identity requests:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 engine-profile
```

Read engine DTCs using the resolver:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --redact-private read
```

Override the resolver deliberately when reproducing a capture:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 read --cmd 18 02 FF 00
```

## Adding another engine ECU family

1. Capture VCDS/ODIS opening Engine 01 and reading DTCs.
2. Confirm the identity strings and the exact DTC-read request/response.
3. Add one `EngineProfile` in `bkd_diag/engine_profiles.py`.
4. Add any confirmed DTC lookup entries in `bkd_diag/dtc.py` and `data/dtcs.csv`.
5. Keep clears/coding/adaptation/basic settings out of the profile unless each is
   separately captured, understood, and explicitly gated.

Profiles are read-strategy metadata, not permission to send write/control
services.

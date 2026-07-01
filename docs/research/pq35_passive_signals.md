# PQ35 passive CAN signal seeds

These are user-observed and diagnostic-validated PQ35 comfort/infotainment CAN notes
for Open MMI research. They are not transmit recipes. Keep runtime passive and
profile-gated.

## Validation method

The 2026-07-01 validation used:

```text
diagnostic truth: 08 Auto HVAC live CSV, groups 001/007/008
passive trace:    Open MMI tablet candump on comfort/infotainment CAN at 100 kbit/s
alignment anchor: 0x470 byte[2] dimmer percentage
auto-offset:      -3.000s for the validation capture pair
passive bus:      comfort/infotainment CAN, 100 kbit/s
diagnostic bus:   TP2.0/KWP diagnostic CAN, 500 kbit/s
```

The validation workflow is now available as:

```bash
python3 -m bkd_diag.cli passive-validate \
  --truth latest \
  --can latest \
  --profile pq35-infotainment
```

or interactively:

```text
start -> Capture / trace tools -> Passive CAN validation wizard
```

## Confirmed signals for this PQ35 profile

These confirmed signals were validated on the 100 kbit/s comfort/infotainment bus used by the Open MMI tablet. The diagnostic CSV truth came from the separate 500 kbit/s TP2.0/KWP diagnostic side.

| Signal | CAN | Raw | Meaning | Formula | Validation |
|---|---:|---|---|---|---|
| `dimmer_470_b2` | `0x470` | `byte[2]` | Dimming Terminal 58d | `raw %` | corr `+1.000`, raw `30..100`, RMSE `0.503` |
| `blower_3e1_b4` | `0x3E1` | `byte[4]` | HVAC blower/turbine load | `raw * 100 / 255 %` | corr `+0.998`, raw `0..239`, RMSE `1.5` |
| `speed_351_u16le_b1_200` | `0x351` | `u16le[1:3]` | vehicle speed | `raw / 200 km/h` | corr `+0.995`, range `0..47 km/h` |
| `speed_527_u16le_b1_200` | `0x527` | `u16le[1:3]` | vehicle speed duplicate/related | `raw / 200 km/h` | corr `+0.996`, range `0..47 km/h` |
| `speed_359_u16le_b1_200` | `0x359` | `u16le[1:3]` | vehicle speed duplicate/related | `raw / 200 km/h` | corr `+0.995`, range `0..47 km/h` |

The earlier `0x351 byte[1]` and `0x527 byte[1]` low-speed candidates are now
**deprecated**. They looked plausible over `0..4 km/h`, but the wider `0..47
km/h` validation proved the useful speed representation is the 16-bit
little-endian value over bytes 1-2.

## Observed / candidate states still needing validation

These have been observed manually but need capture-backed validation before they
become Open MMI runtime signals.

- `0x621 byte[0] bit 5`: handbrake on/off.
- `0x635 byte[0]`: likely illumination/dimmer level; validation showed it tracks `30..100%`, so avoid treating it as only a lights-on boolean.
- `0x351 byte[0] bit 1`: reverse/not reverse.
- `0x531`: lighting/indicator/brake enum-style state bytes.
- `0x470`: door/boot/bonnet/bulb-warning and dimmer state bytes.
- `0x181`: window switch observations.
- `0x2C1`: wiper/washer/horn observations.
- `0x3C3`: steering angle candidate, scale about `0.04375°/count`; byte 1 bit 7 appears directional.
- `0x5C1`: steering wheel/stalk/cluster button observations.
- `0x65F`: VIN broadcast observed; redact before sharing captures.
- `0x601`: mirror fold/adjust/heated mirror observations.

## Safety

Do not replay, spoof or transmit these frames from Open MMI. This file is for
passive decoding and correlation only.

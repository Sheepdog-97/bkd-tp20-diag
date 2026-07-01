# PQ35 passive CAN signal seeds

These are user-observed passive comfort/infotainment CAN notes for Open MMI
research. They are not transmit recipes. Keep runtime passive and profile-gated.

## Confirmed timing anchor

| Signal | CAN | Raw | Meaning | Status |
|---|---:|---|---|---|
| `dimmer_470_b2` | `0x470` | `byte[2]` | dimming Terminal 58d, `0x00..0x64` = `0..100%` | confirmed timing anchor |

The 2026-07-01 paired diagnostic/passive capture aligned best at `-6.0s` using
HVAC truth field `008.F3 Dimming Terminal 58d` against `0x470 byte[2]`:

```text
corr +0.992
truth ≈ 1.09*raw - 2.74
rmse 1.11
```

Use this known signal to calculate timing offset before blind candidate ranking.

## Current candidates

| Signal | CAN | Raw | Candidate meaning | Status |
|---|---:|---|---|---|
| `speed_351_b1_candidate` | `0x351` | `byte[1]` | vehicle speed, approx `raw * 0.0213 km/h` | candidate |
| `speed_527_b1_candidate` | `0x527` | `byte[1]` | vehicle speed/duplicate speed, approx `raw * 0.0213 km/h` | candidate |
| `blower_3e1_b4_candidate` | `0x3E1` | `byte[4]` | HVAC blower/turbine load, approx `raw * 100/255 %` | candidate |

Validation still needed:

```text
speed:  0 -> 10 -> 20 -> 30 km/h -> stop
blower: low -> medium -> high -> medium -> low
```

## User-supplied observed states

These have been observed manually but need capture-backed validation before they
become Open MMI runtime signals.

- `0x621 byte[0] bit 5`: handbrake on/off.
- `0x635 byte[0] bit 6`: lights on/off.
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

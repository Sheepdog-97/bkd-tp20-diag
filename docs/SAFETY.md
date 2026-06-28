# Safety notes

This is experimental vehicle diagnostic software.

## Safe default scope

The mature supported path is Engine 01 on the BKD EDC16 ECU over VW TP2.0/KWP2000.

Supported engine operations:

- read DTCs
- clear DTCs only with explicit confirmation
- read ECU identification
- read measuring blocks
- live logging / CSV logging

## Read-only non-engine module scope

ABS, airbag, steering, immobilizer, gateway, cluster, and body modules are safety or
security relevant. Active non-engine probing is gated with `--experimental-module`.

The development vehicle now has VCDS-derived and live-tested read-only profiles for:

```text
03 ABS Brakes
08 Auto HVAC
17 Instruments
19 CAN Gateway
44 Steering Assist
46 Central Convenience
```

Allowed scope for these profiles:

```text
read identification
read DTCs
close the diagnostic session
```

This is still vehicle-specific evidence, not a universal VAG compatibility claim.
Do not run experimental module commands unless you understand what the tool is
sending.

## ABS/ESP close behaviour

ABS/ESP may visibly enter diagnostic communication during active access. From
v0.3.16 the tool uses an ABS-specific graceful close path: drain transport traffic,
answer/ACK pending control frames where needed, send TP2.0 `A8`, then drain briefly
before closing the socket.

If ABS/ESP lamps remain flashing after tool exit:

```text
cycle ignition
stop active ABS testing
review the close/trace behaviour before trying again
```

Do not drive if ABS/ESP warning lamps remain on unexpectedly.

## Driving

Do not operate a laptop while driving. For road logging, have a second person operate
the laptop or set up logging before moving.

## Coding/adaptation/basic settings

This project does not currently implement coding, adaptation, basic settings, output
tests, immobilizer functions, brake bleeding, or guided functions.

Not allowed in this project stage:

```text
clear DTCs on non-engine modules
coding
adaptation
basic settings
output tests
security access
ABS bleeding/calibration routines
airbag/immobilizer experiments
```

Keep active diagnostic tooling separate from any always-on Open MMI runtime.

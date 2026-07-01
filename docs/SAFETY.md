# Safety notes

This is experimental vehicle diagnostic software.

## Safe default scope

The mature supported path is Engine 01 on the BKD EDC16 ECU over VW TP2.0/KWP2000 over CAN. KW1281/K-line controllers are out of scope for this tool.

Supported engine operations:

- read DTCs
- clear DTCs only with explicit confirmation
- read ECU identification
- read measuring blocks
- live logging / CSV logging

## Read-only non-engine module scope

ABS, airbag, steering, immobilizer, gateway, cluster, and body modules are safety or
security relevant. Active non-engine probing is gated. Direct commands require `--experimental-module`; the interactive menu asks for typed read-only confirmation at the point of access.

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

## Interactive menu safety

From v0.4.0, `start` provides a module-first interactive menu. From v0.4.1 the menu also includes capture/trace tools and concise Auto-Scan output by default. v0.4.2 only adds semantic colour; it does not widen diagnostic scope. It is a usability
wrapper around the existing proven commands, not a broader permission model.

The menu deliberately keeps these limits:

```text
Engine 01 clear DTCs: allowed with typed confirmation
Non-engine clear DTCs: disabled
Engine 01 measuring blocks: allowed
Non-engine measuring blocks: disabled until VCDS-captured requests are proven
```

Starting the menu no longer configures `can0` immediately. Offline analysis and
passive validation paths stay offline; live diagnostic paths configure the interface
only when selected. The menu asks for private-identifier redaction at startup and
asks for typed read-only confirmation before non-engine active access. Direct CLI
commands still support `--redact-private` and require `--experimental-module` for
non-engine active module commands.

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

## 08 Auto HVAC measuring blocks

v0.6.0 adds active read-only 08 Auto HVAC measuring-block reads.  These are
limited to KWP `21 xx` requests on the profiled 08 TP2.0 channel.  The feature is
intended to create ground-truth logs for passive Open MMI reverse engineering.

This feature does **not** add HVAC control.  It does not send output tests,
coding, adaptation, basic settings, security access, DTC clear commands, or
passive CAN replay/spoofing frames.

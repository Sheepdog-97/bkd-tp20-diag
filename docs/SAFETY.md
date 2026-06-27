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

## Experimental module scope

ABS, airbag, steering, immobilizer, gateway, cluster, and body modules are safety or
security relevant. Active non-engine probing is gated with `--experimental-module`.

Do not run experimental module commands unless you understand what the tool is sending.

## Driving

Do not operate a laptop while driving. For road logging, have a second person operate
the laptop or set up logging before moving.

## Coding/adaptation/basic settings

This project does not currently implement coding, adaptation, basic settings, output
tests, immobilizer functions, brake bleeding, or guided functions.

# VCDS-derived TP2.0 module profiles

These profiles come from passive splitter captures of VCDS opening the controller,
reading identification, and entering Fault Codes - 02. They are read-only evidence
for this development vehicle, not a universal VAG compatibility claim.

## Common observed flow

Across the captured modules VCDS used the same TP2.0/KWP shape:

```text
0x200 setup request with module logical address
0x200 + logical setup response with D0
A0 0F 8A FF 32 FF channel parameters
A1 ... channel parameter/test response
10 89 StartDiagnosticSession
50 89 positive session response
1A xx identification reads
18 02 FF 00 read DTCs
A3/A1 channel tests during longer waits
A8 close
```

## Captured profiles

| VCDS address | Module | TP2.0 logical | Setup response | Tester → ECU | ECU → tester | Session | DTC read |
|---|---|---:|---:|---:|---:|---:|---|
| 03 | ABS Brakes | `0x03` | `0x203` | `0x790` | `0x300` | `10 89` | `18 02 FF 00` |
| 08 | Auto HVAC | `0x2C` | `0x22C` | `0x33D` | `0x300` | `10 89` | `18 02 FF 00` |
| 17 | Instruments | `0x07` | `0x207` | `0x750` | `0x300` | `10 89` | `18 02 FF 00` |
| 19 | CAN Gateway | `0x1F` | `0x21F` | `0x32E` | `0x300` | `10 89` | `18 02 FF 00` |
| 44 | Steering Assist | `0x09` | `0x209` | `0x7A8` | `0x300` | `10 89` | `18 02 FF 00` |
| 46 | Central Convenience | `0x21` | `0x221` | `0x328` | `0x300` | `10 89` | `18 02 FF 00` |

Engine 01 remains the stable primary target and uses logical `0x01`, tester → ECU
`0x740`, ECU → tester `0x300`, session `10 89`.

## Live active status on the development vehicle

| Module | Active read-only status | Observed DTC result |
|---|---|---|
| 03 ABS Brakes | PASS; clean ABS/ESP close tested in v0.3.16 | No DTCs observed |
| 08 Auto HVAC | PASS | 00229 / 0x00E5 / status 0x62 observed |
| 17 Instruments | PASS | No DTCs observed |
| 19 CAN Gateway | PASS | 01305 / 0x0519 and 01304 / 0x0518 observed |
| 44 Steering Assist | PASS | No DTCs observed |
| 46 Central Convenience | PASS; split DTC response merge tested | 01135 / 0x046F / status 0x24 observed |

## Important transport lessons

- The VCDS address and TP2.0 logical address are not always the same. For example,
  VCDS address 17 Instruments uses TP2.0 logical `0x07`.
- Gateway logical `0x1F` is often opened by VCDS before the requested module.
- ABS identification can return many `7F xx 78 responsePending` replies before the
  final positive response.
- ECU-sent `A3` channel tests can happen during long pending waits. The tester must
  answer and keep waiting.
- Multi-frame KWP responses must be reassembled before classifying service bytes;
  otherwise continuation text bytes look like fake KWP services.
- Command code must match the expected KWP service response. For example `18 xx`
  must wait for `58` or `7F 18 xx`, not accept stale `5A` identity data.
- Draining late payloads means passively receiving/ACKing transport frames; it must
  not send extra diagnostic requests just to flush the stream.
- Central Convenience can split DTC data as a short `58/count` payload followed by a
  late `58` payload containing the record bytes.
- ABS needs a graceful close window so ABS/ESP lamps do not remain flashing after the
  tool exits.

## Active command policy

Active non-engine commands remain behind `--experimental-module` even though these
profiles are now known. The supported non-engine actions are read-only:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-dtc 03
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module module-ident 03
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 --experimental-module probe-module 03
```

Do not add coding, adaptation, basic settings, output tests, or non-engine DTC clear
without a separate deliberate safety review.

## Active-test lessons

The first active v0.3.9 tests proved that the captured TP2.0 profiles were correct:
all tested non-engine modules accepted setup, channel parameters, and `10 89 -> 50 89`.
However, a bare `18 02 FF 00` immediately after session open did not match VCDS
behaviour and mostly timed out.

v0.3.10 added the VCDS-style pre-DTC order:

```text
session 10 89 -> 50 89
1A 9B                 read extended identity
31 B8 00 00           VCDS-observed read/status request
optional 1A 9A/91/9F  module-specific identity reads
18 02 FF 00           read DTCs
```

v0.3.15/v0.3.16 fixed the important transport details: strict expected-response
matching, passive late-payload draining, split 46 DTC merge, module-aware DTC wording,
and ABS/ESP graceful close.

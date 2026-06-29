# BKD TP2.0/KWP read-only Auto-Scan

Generated: `2026-06-29T17:12:37`

Scope: read-only VW TP2.0/KWP2000 over CAN

Private identifiers: redacted

| Module | Part No | Status | DTCs |
|---|---|---|---|
| 01 Engine | 03G 906 016 AJ | OK | none |
| 03 ABS Brakes | 1K0 907 379 Q | OK | none |
| 08 Auto HVAC | 1P0 907 044 | 1 DTC(s) | 00229 / 0x00E5: Unknown Auto HVAC fault (0x62) |
| 17 Instruments | 1P0 920 923 C | OK | none |
| 19 CAN Gateway | 1K0 907 530 F | 2 DTC(s) | 01305 / 0x0519: Databus for Infotainment: No signal/communication (0x64)<br>01304 / 0x0518: Radio: No signal/communication (0x64) |
| 44 Steering Assist | 1K2 909 144 J | OK | none |
| 46 Central Convenience | 1K0 959 433 AK | 1 DTC(s) | 01135 / 0x046F: Interior Monitoring Sensors (0x24) |

## 08 Auto HVAC

- **00229 / 0x00E5**: Unknown Auto HVAC fault
  - Status: `0x62` — failed this operation cycle, test failed since last clear, test not completed this operation cycle

## 19 CAN Gateway

- **01305 / 0x0519**: Databus for Infotainment: No signal/communication
  - Status: `0x64` — pending DTC, test failed since last clear, test not completed this operation cycle
- **01304 / 0x0518**: Radio: No signal/communication
  - Status: `0x64` — pending DTC, test failed since last clear, test not completed this operation cycle

## 46 Central Convenience

- **01135 / 0x046F**: Interior Monitoring Sensors
  - Status: `0x24` — pending DTC, test failed since last clear

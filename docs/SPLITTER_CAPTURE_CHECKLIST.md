# OBD splitter capture checklist

Goal: let VCDS/ODIS be the active diagnostic tester while the Linux SocketCAN adapter passively records the CAN traffic.

## Hardware

- OBD splitter connected to the car
- VCDS/ODIS interface connected to one side of the splitter
- Linux SocketCAN/DSD adapter connected to the other side
- DSD adapter wired to diagnostic CAN:
  - OBD 6 = CAN-H
  - OBD 14 = CAN-L
  - OBD 4/5 = ground
- Do not run active `bkd_diag` commands while VCDS/ODIS is connected as the active tester.

## Put Linux adapter in listen-only mode

```bash
cd bkd_tp20_project
mkdir -p captures
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only on
sudo ip link set can0 up
ip -details link show can0
```

## Start capture before opening the module

```bash
candump -tz -x can0 | tee captures/vcds_03_abs_open_faults.log
```

Leave this running.

## In VCDS

For the first useful ABS capture:

```text
03-ABS Brakes
wait for the controller screen to fully load
Fault Codes - 02
wait for the fault-code screen to complete
close/back out of the controller
```

Stop `candump` with Ctrl+C after VCDS has closed the controller.

## Analyse capture

```bash
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log --raw --json-out captures/vcds_03_abs_summary.json
```

Useful output should show at least:

```text
TP2.0 setup request
TP2.0 setup accepted / D0
channel parameter request/response
session request or direct service request
DTC read request/response
A8 close/disconnect
```

## Return adapter to active mode afterwards

```bash
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000
sudo ip link set can0 up
```

## First captures to get

Capture these separately if possible:

```text
vcds_03_abs_open_faults.log
vcds_19_gateway_open_faults.log
vcds_17_instruments_open_faults.log
```

VCDS first, ODIS later. VCDS traces are usually smaller and easier to learn from.

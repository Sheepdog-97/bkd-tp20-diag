# 08 Auto HVAC measured-value catalogue

This catalogue is seeded from VCDS screenshots and splitter captures from the
SEAT Leon 1P / PQ35 Climatronic module.  It is deliberately read-only.

The first supported active requests are standard KWP measuring-block reads:

```text
21 xx  ->  61 xx
```

For the development vehicle, 08 Auto HVAC uses the profiled TP2.0 channel:

```text
VCDS address: 08
TP2.0 logical: 0x2C
tester -> ECU: 0x33D
ECU -> tester: 0x300
session: 10 89
```

## Important interpretation

HVAC buttons are not usually a single passive CAN byte that simply changes from
0 to 1.  They often change a requested target.  The controller then drives a
motor/blower/compressor and the measured values show both requested/specified
and actual feedback.

For reverse engineering Open MMI, use these measured values as the truth source:

```text
button/control action
  -> specified value changes
  -> actual value follows
  -> passive CAN correlation can be searched against that target/feedback
```

## Priority groups

- 001: General / compressor inhibit, engine speed, vehicle speed, standing time
- 006: Evaporator temperature, interior temperature, sunlight sensors
- 007: Turbine/blower voltage/load and terminal 30 voltage
- 008: Terminal 15 voltage and dimming terminal 58d
- 009: Rear window heater actual/specified and auxiliary heater values
- 011-016: flap actual/specified/min/max positions

## Commands

Show the built-in catalogue:

```bash
python3 -m bkd_diag.cli hvac-catalogue
```

Read one HVAC block snapshot:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli \
  --iface can0 \
  --experimental-module \
  module-block 08 009
```

Live useful overview. In an interactive terminal this redraws an in-place
dashboard while `--csv` writes the full sample history. Add `--journal` for
scrolling sample-by-sample output:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli \
  --iface can0 \
  --experimental-module \
  module-live 08 001 006 007 008 009 --csv
```

Live flap positions:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli \
  --iface can0 \
  --experimental-module \
  module-live 08 011 012 013 014 015 016 --csv
```

## Compressor Shut-Off Code

Group 001 field 1 is labelled by VCDS as Compressor Shut-Off Code.  Seeded
lookup:

```text
0  = Compressor ON
1  = Refrigerant pressure too high
2  = Blower faulty or blower voltage too low
3  = Refrigerant pressure too low
5  = Engine start not detected / runtime less than 4 seconds
6  = ECON mode
7  = Control panel OFF
8  = Outside temperature too low
10 = Supply voltage too low
11 = Coolant temperature too high
12 = Shut-off via Engine Control Module
13 = Supply voltage too high
14 = Evaporator temperature too low / icing risk
15 = Control module coding incorrect
16 = Activation signal faulty
17 = Refrigerant pressure sensor implausible
```

## First-pass decoded formula bytes

The first live HVAC test proved a few safe/common measured-value formula bytes:

```text
0x01  engine speed              A * 0.2 * B rpm
0x05  temperature               A * 0.1 * B - 100 °C
0x06  voltage                   A * 0.001 * B V
0x07  vehicle speed             A * 0.01 * B km/h
0x08  scaled/code value         A * 0.1 * B, label-dependent
```

Unknown cells remain raw/unresolved.  Group 007/008 field counts are based on
the live 08 Auto HVAC payloads seen on the development vehicle; treat label
seeds as useful but not universal across all HVAC variants.

## Safety boundary

v0.6.1 does not add HVAC control.  It does not send output tests, coding,
adaptation, basic settings, security access, clear-DTC commands, or replayed
passive CAN frames.  It only opens the profiled 08 diagnostic channel and reads
measuring blocks.

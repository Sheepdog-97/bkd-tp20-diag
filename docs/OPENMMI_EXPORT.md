# Open MMI export bridge

`openmmi-export` turns a passive validation report into a small Open MMI overlay/export bundle.

The export is offline and passive. It does **not** add CAN transmit, replay, spoofing, diagnostic sessions, clear-DTC, coding, adaptation, basic settings, output tests, or vehicle control.

## Typical command

```bash
python3 -m bkd_diag.cli --no-log openmmi-export \
  --validation latest \
  --out-dir exports/openmmi \
  --include-speed-duplicates
```

`latest` searches for the newest `captures/passive_validation_*.json` report.

## Inputs

Use a report from:

```bash
python3 -m bkd_diag.cli passive-validate \
  --truth latest \
  --can latest \
  --profile pq35-infotainment
```

Older v0.8.x validation reports that do not contain explicit bus metadata are accepted. For the `pq35-infotainment` profile the exporter infers:

- bus: `comfort`
- bitrate: `100000`
- interface: `can0`
- mode: passive/listen-only recommended

## Outputs

The exporter writes:

- `openmmi_<vehicle>_<profile>_overlay.json`
- `openmmi_<vehicle>_<profile>_overlay_signals.json`
- `openmmi_<vehicle>_<profile>_overlay.md`
- `README.md`

The overlay is a reviewable bridge artifact. Review it before copying entries into an Open MMI vehicle profile.

## Exported confirmed signals

By default:

- `lighting.dimmer_percent` from `0x470 byte[2]`, raw equals percent
- `climate.blower_load_percent` from `0x3E1 byte[4]`, raw * 100 / 255
- `vehicle.speed_kmh` from `0x351 u16le[1:3] / 200`

With `--include-speed-duplicates`:

- `vehicle.speed_kmh_from_527` from `0x527 u16le[1:3] / 200`
- `vehicle.speed_kmh_from_359` from `0x359 u16le[1:3] / 200`

The duplicate speed signals are exported as cross-check/alias signals, not as the primary runtime speed field.

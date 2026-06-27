# Personal workflows

## Before MOT / quick engine check

Read-only snapshot:

```bash
sudo python3 -m bkd_diag.cli --iface can0 mot-check
```

Useful follow-ups:

```bash
sudo python3 -m bkd_diag.cli --iface can0 quick
sudo python3 -m bkd_diag.cli --iface can0 preset readiness --count 1
```

## Road log boost

Log requested boost, actual boost, and duty-related fields:

```bash
mkdir -p logs
sudo python3 -m bkd_diag.cli --iface can0 preset boost --interval 0.5 --csv
```

Or include MAF/EGR context:

```bash
sudo python3 -m bkd_diag.cli --iface can0 preset road --interval 0.5 --csv
```

Suggested driving method: second person operates the laptop; do not operate it while
driving.

## MAF / EGR check

Snapshot:

```bash
sudo python3 -m bkd_diag.cli --iface can0 block 3
```

Live:

```bash
sudo python3 -m bkd_diag.cli --iface can0 live 3 --interval 1
```

Compare specified/requested air mass with actual air mass and EGR duty. Keep raw output
if the conversion/label is not yet verified for your ECU variant.

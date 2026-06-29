# Trace capture and analysis

## Guided interactive capture

From v0.4.1 the interactive menu can put the interface into listen-only mode, run
`candump`, save a timestamped capture under `captures/`, and restore active mode
when stopped:

```bash
sudo PYTHONPATH="$PWD" python3 -m bkd_diag.cli --iface can0 start
# Main menu -> Capture / trace tools -> Passive VCDS splitter capture
```

## Manual VCDS/ODIS passive capture

Use an OBD splitter. VCDS/ODIS should be the active diagnostic tester. The Linux CAN
adapter should be listen-only.

```bash
mkdir -p captures

sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 listen-only on
sudo ip link set can0 up

candump -tz -x can0 | tee captures/vcds_03_abs_open_faults.log
```

In VCDS, open the module, wait for the controller screen, read fault codes, then close
the controller. Stop `candump` with Ctrl+C.

## Analyse a trace

```bash
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log --raw --max-events 120
python3 -m bkd_diag.cli analyse-trace captures/vcds_03_abs_open_faults.log --json-out captures/vcds_03_abs_summary.json
```

The analyser highlights:

- TP2.0 setup requests and D0 setup responses
- negotiated tester/ECU CAN IDs
- channel parameter exchange
- StartDiagnosticSession requests/responses
- DTC reads/responses
- ECU identification reads/responses
- measuring block reads/responses
- A3 keepalives and A8 closes

It is a helper, not a full ISO-TP/TP2.0 reassembler.

## Guided measuring-block capture

From v0.5.0 the interactive menu can guide a VCDS measuring-block capture:

```text
start -> Capture / trace tools -> Guided VCDS measuring-block capture
```

Use one capture per module/group/scenario. Example:

```text
Address 08 Auto HVAC, group 001, blower low/high/low
```

After capture, analyse it with:

```bash
python3 -m bkd_diag.cli analyse-trace captures/<file>.log --raw --json-out captures/<file>.summary.json
```

See `docs/HVAC_MEASURING_BLOCK_WORKFLOW.md` for the recommended first target.

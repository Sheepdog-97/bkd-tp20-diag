# Publishing checklist

Before pushing to GitHub:

- confirm `LICENSE` is present
- do not commit private `logs/`, `captures/`, or `private/`
- anonymise VINs, registration numbers, customer names, workshop names, and raw logs
- mark non-engine modules experimental
- keep coding/adaptation/basic settings out unless deliberately implemented and tested
- run `python3 -m py_compile bkd_diag/*.py`
- run CLI smoke tests:
  ```bash
  python3 -m bkd_diag.cli --help
  python3 -m bkd_diag.cli --no-log module-info 03
  python3 -m bkd_diag.cli --no-log analyse-trace examples/sample_abs_tp20_trace.log
  ```

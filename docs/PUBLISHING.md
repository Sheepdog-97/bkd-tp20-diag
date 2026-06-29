# Publishing checklist

Before pushing to GitHub:

- confirm `LICENSE` is present
- do not commit private `logs/`, `captures/`, or `private/`
- anonymise VINs, registration numbers, customer names, workshop names, and raw logs
- keep non-engine active commands gated by `--experimental-module`
- keep coding/adaptation/basic settings/output tests out unless deliberately implemented and tested
- confirm version metadata is consistent in `bkd_diag/__init__.py`, `pyproject.toml`, and `CHANGELOG.md`
- run `python3 -m compileall -q bkd_diag`
- run CLI smoke tests:
  ```bash
  python3 -m bkd_diag.cli --help
  python3 -m bkd_diag.cli --no-log --no-iface-setup module-plan
  python3 -m bkd_diag.cli --no-log --no-iface-setup module-info 03
  printf '5\n' | python3 -m bkd_diag.cli --no-log --no-iface-setup start
  python3 -m bkd_diag.cli --no-log analyse-trace examples/sample_abs_tp20_trace.log
  ```
- run privacy checks:
  ```bash
  git grep -nE 'YOUR_REAL_VIN|YOUR_REG|your-name|your-email|your-handle' || echo "No tracked personal strings found"
  git ls-files | grep -E 'logs|captures|private|\.venv|egg-info|__pycache__' || echo "No private/generated paths tracked"
  ```

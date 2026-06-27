# Changelog

## v0.3.8

Documentation-only checkpoint after real v0.3.7 regression testing.

- Updated install docs for Debian/Ubuntu PEP 668 externally-managed Python.
- Made direct `python3 -m bkd_diag.cli ...` usage the recommended default.
- Added `docs/REGRESSION_TESTS.md`.
- Added `docs/SPLITTER_CAPTURE_CHECKLIST.md`.
- Added `docs/GITHUB_PUSH.md`.
- Linked new docs from README.
- No diagnostic/runtime behaviour changes from v0.3.7.

## v0.3.7

Splitter-ready / GitHub-prep build.

- Added GPLv3 licence file and `GPL-3.0-or-later` metadata.
- Added `.gitignore`.
- Rewrote README around public scope, supported vehicle table, safety, install, trace capture, and workflows.
- Added docs:
  - `docs/INSTALL.md`
  - `docs/SAFETY.md`
  - `docs/TRACE_CAPTURE.md`
  - `docs/WORKFLOWS.md`
  - `docs/PUBLISHING.md`
- Added anonymised synthetic trace example:
  - `examples/sample_abs_tp20_trace.log`
- Removed the real development VIN from public profile/example data.
- Improved `engine-check` / `mot-check` output with a more reader-style summary.
- Made coolant/readiness caveats explicit.
- Improved `analyse-trace`:
  - `--json-out` summary export
  - better KWP service summaries
  - session/ident/DTC/measuring-block extraction
  - more candump/log formats
- Retained v0.3.6 experimental non-engine module guards.
- Retained v0.3.5 sudo log ownership fix and TP2.0 socket close cleanup.

## v0.3.6

- Added `engine-check` / `mot-check`.
- Added `analyse-trace` / `analyze-trace`.
- Added `--experimental-module` gate for active non-engine probing.

## v0.3.5

- Fixed root-owned log/CSV output when commands are run via `sudo`.
- Ensured `TP20KWP.close()` closes the SocketCAN socket.

## Earlier

- BKD Engine 01 TP2.0/KWP read/clear/ident/measuring blocks/live logging.
- DTC database CSV support.
- Vehicle profile and VCDS Auto-Scan summary helpers.
- ABS TP2.0 setup discovery; KWP sequence still experimental.

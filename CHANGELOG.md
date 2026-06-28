# Changelog

## v0.3.17 - Observed VAG DTC lookup entries

- Adds built-in lookup entries for observed live module DTCs:
  - 00229 / 0x00E5 from 08 Auto HVAC, exact label still unconfirmed.
  - 01135 / 0x046F Interior Monitoring Sensors from 46 Central Convenience.
  - 01304 / 0x0518 Radio: No signal/communication from 19 CAN Gateway.
  - 01305 / 0x0519 Databus for Infotainment: No signal/communication from 19 CAN Gateway.
- No transport/protocol behaviour changes from v0.3.16.

## v0.3.16 - ABS exit hygiene / module wording / 46 DTC merge polish

- Fixes module DTC wording so non-engine reads no longer say "engine ECU".
- Adds ABS/ESP graceful TP2.0 close handling: drain transport traffic, send A8, then drain briefly again before closing the socket.
- Attempts the ABS graceful close path even after Ctrl+C/timeouts so the tool is less likely to leave ABS/ESP lamps flashing until an ignition cycle.
- Removes tester-side pre-DTC A3 bursts for active module DTC reads; VCDS-like A3 handling remains available for ECU-sent channel tests.
- Improves Central Convenience (46) split DTC merge handling for responses such as `58 01` followed by late `58 04 6F 24`.
- Compresses one-byte stale `58` DTC fragments in logs.
- Engine, HVAC, Instruments, Gateway, and Steering Assist proven paths remain unchanged apart from clearer wording.

## v0.3.15 - Strict KWP response matching / passive drain fix

- Fixes the remaining transport-layer abstraction bug exposed by 46 Central Convenience and 03 ABS live testing.
- `kwp_request()` can now run in strict expected-response mode, so `18 xx` waits for `58`/`7F 18` instead of accepting stale `5A` identity fragments.
- Preamble requests now match the service they asked for: `1A` -> `5A`/`7F 1A`, `31` -> `71`/`7F 31`, `18` -> `58`/`7F 18`.
- Late identity payload draining is now passive receive/ACK only; it no longer looks like repeated `1A 9B` requests in the output.
- Central Convenience (46) restores the VCDS-observed pre-DTC sequence once stale `5A` filtering is in place: `1A 9B`, `31 B8`, `1A 9A`, `1A 91`, keepalive, then DTC.
- ABS (03) keeps the VCDS-observed `1A 9B`, `31 B8`, `1A 91`, then a tester-side A3 idle run before DTC.
- One-byte stale `5A` spam is compressed in logs instead of being printed as fake complete responses.
- Engine, HVAC, Instruments, Gateway, and Steering Assist proven paths are kept unchanged apart from safer response matching in module workflows.

## v0.3.14 - ABS/46 follow-up tightening

- ABS module-dtc now retries the VCDS-observed 1A 91 pre-DTC identity step after 1A 9B/31 B8 alignment was fixed.
- ABS DTC read timeout/pending budget increased slightly for the slow MK60 path.
- Central Convenience/body-module DTC reads now drain late payloads when a positive 58/count response arrives before all 3-byte DTC records.
- DTC printer now warns when a response declares records but contains too few record bytes.
- Engine and proven 08/17/19/44 module behaviour left unchanged.

## v0.3.13 - Convenience/ABS conservative DTC workflow

- Keep proven v0.3.12 behaviour for Engine, HVAC, Instruments, Steering Assist, and Gateway.
- Make Central Convenience (46) DTC workflow more conservative: use 1A 9B only, drain late identity payloads, then read DTCs directly.
- Disable tester-side pre-DTC A3 bursts for non-engine module-dtc; live ABS/46 testing showed they can trigger channel close.
- Drain longer for late multi-payload 1A responses, especially Central Convenience.
- Keep all non-engine active commands behind --experimental-module and read-only only.

## v0.3.12 - Module DTC desync fix

- Drains extra read-identification KWP payloads after VCDS-style preamble requests so late `5A xx` identity frames are not mistaken for the next request response.
- Makes 19 Gateway and 46 Central Convenience pre-DTC rituals more conservative based on live v0.3.11 testing.
- Skips non-essential `1A 91` in the ABS DTC workflow after live testing showed it could hang after the long ABS identity stream.
- Keeps engine behaviour unchanged and preserves `--experimental-module` gating for active non-engine commands.

## v0.3.11 - Active non-engine pacing fix

- Added VCDS-like inter-KWP pacing for non-engine module profiles.
- Preserves engine timing behaviour while delaying post-session/module KWP requests on VCDS-derived module profiles.
- Targets active v0.3.10 traces where target modules accepted TP2.0 setup and `10 89 -> 50 89` but ignored the immediately following `1A`/`18` request and only emitted A3 keepalives.

## v0.3.10

VCDS-style non-engine conversation fix.

- Treat ECU-sent `A3` channel tests as transparent TP2.0 control traffic during KWP waits; reply and keep waiting for real KWP data instead of returning/closing early.
- Added tester-initiated `A3` keepalive support so module commands can mimic VCDS idle behaviour before DTC reads.
- Changed `module-dtc` to run VCDS-derived read-only preambles before `18 02 FF 00` instead of sending a bare DTC request immediately after `50 89`.
- Added module-specific pre-DTC sequences for 03 ABS, 08 HVAC, 17 Instruments, 19 Gateway, 44 Steering Assist, and 46 Central Convenience.
- Increased non-engine ident/DTC wait windows for modules that produce long `7F xx 78 responsePending` chains.
- Improved raw logging of preamble responses so the next active test explains itself.
- Safety boundary unchanged: active non-engine access remains gated by `--experimental-module` and remains read-only.

## v0.3.9

VCDS splitter-capture module-profile build.

- Added VCDS-derived TP2.0/KWP profiles for 03 ABS, 08 HVAC, 17 Instruments, 19 Gateway, 44 Steering Assist and 46 Central Convenience.
- Added `module-dtc` and `module-ident` read-only active commands behind `--experimental-module`.
- Updated `probe-module` to use captured TP2.0 logical addresses instead of assuming VCDS address == TP2.0 logical address.
- Fixed ECU-sent `A3` channel-test response handling using the tester response observed in the ABS trace.
- Improved long `7F xx 78 responsePending` handling for slow identification responses.
- Reworked trace analysis to reassemble multi-frame TP2.0/KWP messages before classifying KWP services, reducing false service/DTC counts from continuation bytes.
- Added `docs/VCDS_MODULE_PROFILES.md`.
- Active non-engine commands remain gated and read-only.

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

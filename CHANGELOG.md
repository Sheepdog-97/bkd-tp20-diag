# Changelog

## v0.8.1

- Adds known passive-signal support for the correlation helper.
- Adds `--known-signal`, `--list-known-signals`, `--auto-offset`, `--offset-sweep`, and `--offset-truth-field` to `correlate`.
- Seeds `dimmer_470_b2` as a confirmed timing anchor for PQ35 comfort/infotainment CAN: `0x470 byte[2]` maps dimming Terminal 58d percentage.
- Seeds `speed_351_b1_candidate`, `speed_527_b1_candidate`, and `blower_3e1_b4_candidate` as validation candidates, not final runtime truth.
- Adds `data/passive_signals_pq35_seed.json` and `docs/research/pq35_passive_signals.md`.
- Fixes HVAC group 007/008 field labels: `007.F3` is Turbine Load, `008.F3` is Dimming Terminal 58d, and `008.F4` is Country.
- Adds correlation warnings for low-range truth fields and weak top candidates.

## v0.8.0

- Adds offline `correlate` command to rank passive CAN signal candidates from diagnostic live CSV truth plus a passive candump trace.
- Supports listing numeric truth fields from live CSV logs, selecting a truth field by label/key, testing byte/u16/s16 candidates, optional bit candidates for status signals, timing window/offset adjustment, CAN ID filtering, and Markdown/JSON report export.
- Skips known TP2.0/KWP diagnostic CAN IDs by default so correlation targets passive broadcast traffic rather than the active measuring-block responses that produced the truth CSV.
- Adds `docs/PASSIVE_CORRELATION.md` workflow for vehicle speed, dimming, terminal state, HVAC status, and other Open MMI candidate signals.
- Offline analysis only: no CAN transmit, no diagnostic session, no control, no clear-DTC, no coding, no adaptation, no output tests, no basic settings, and no replay.

## v0.7.2

- Corrects 08 Auto HVAC group 004 labels from the VCDS screenshots: outside temperature unfiltered, outside temperature regulation, fresh-air intake temperature, and coolant temperature.
- Keeps group 005 as the outlet/footwell blower temperature group.
- No protocol, profile, clear-DTC, coding, adaptation, output-test, basic-settings, control, or CAN-replay changes.

## v0.7.1

- Confirms the Engine 01 profile resolver on both the development BKD/EDC16 path and the captured MED9.5.10 Mk5 Golf path.
- Adds HVAC formula byte `0x02` decode for percentage-style values used by radiator fan activation, blower load and Terminal 58d dimming.
- Reclassifies HVAC group 005 as the live-confirmed outlet/footwell temperature group and marks group 004 as unverified/generic until a VCDS capture/photo confirms it.
- Prevents unknown 08 Auto HVAC groups from falling back to Engine 01 measuring-block labels.
- Adds conservative `OFF` rendering for HVAC status-style fields that use raw `25 00 88`.
- Keeps all HVAC work read-only: no clear-DTC, coding, adaptation, basic settings, output tests, control commands, or CAN replay.

## v0.7.0

- Added a small identity-based Engine 01 profile resolver so future engine-family additions are isolated to profile rules instead of transport/protocol code.
- Keeps BKD / EDC16 as the primary development profile with DTC read `18 02 FF 00`.
- Adds captured MED9.5.10 / Mk5 Golf petrol support using VCDS-observed DTC read `18 00 FF 00`.
- Unknown Engine 01 TP2.0/KWP ECUs use a conservative read-only fallback: try the BKD DTC read, then try the MED9-observed variant only when the ECU reports the first subfunction is unsupported.
- Adds `engine-profiles` and `engine-profile` commands.
- Direct `read`, `quick`, interactive engine DTC read, interactive quick, `engine-check`, `selftest`, and active `autoscan` now use the resolver unless the user explicitly supplies a raw read command.
- Adds DTC lookup entries confirmed from the Mk5 Golf VCDS scan/capture: `012408 / P3078`, `00778`, `01435`, and improves `00229` to Refrigerant Pressure.
- Improves trace analysis of mid-capture/partial long KWP payloads by surfacing embedded response hints such as `5A`, `58`, `54`, and `7F` fragments.
- No new clear-DTC behaviour, coding, adaptation, output tests, basic settings, or CAN replay added.

## v0.6.2

- Changes direct `module-live 08 ...` output from scrolling sample journal to the same in-place dashboard style used by the interactive HVAC live menu.
- Keeps CSV logging as the full sample history underneath the dashboard.
- Adds `module-live --journal` for the old scrolling output when that is wanted for copy/paste or non-interactive logging.
- Falls back to scrolling output automatically when stdout is not an interactive colour terminal.
- No TP2.0/KWP protocol, HVAC formula, clear-DTC, coding, adaptation, output-test, basic-settings, or CAN-replay changes.

## v0.6.1

- Added first-pass HVAC measured-value decodes proven from live 08 Auto HVAC output:
  - formula 0x05 temperature values,
  - formula 0x06 voltage values,
  - formula 0x07 vehicle speed values,
  - formula 0x08 scaled/code values.
- Added compressor shut-off code rendering in measuring-block output, e.g. code 3 = refrigerant pressure too low.
- Keeps unknown HVAC formulas unresolved/raw rather than guessing.
- No protocol, clear-DTC, coding, adaptation, output-test, basic-settings, or CAN-replay changes.

## v0.6.0

- Added built-in 08 Auto HVAC measured-value catalogue seeded from VCDS screenshots.
- Added `hvac-catalogue` command.
- Added read-only `module-block 08 <group>` and `module-live 08 <groups...>` commands for HVAC measuring blocks.
- Added interactive 08 Auto HVAC measuring-block menu for useful overview, flap groups, group 009 and custom groups.
- Added strict expected-response matching for KWP measuring-block reads (`61 xx` / `7F 21`).
- Updated unresolved measured-value display to avoid misleading fake `u16` values.
- Added HVAC measured-value catalogue documentation and CSV label seed.
- No HVAC control, output tests, coding, adaptation, basic settings, clear-DTC, or CAN replay added.


## v0.5.1 - live dashboard helper fix

- Fixed interactive live measuring-block dashboard/CSV mode raising `name 'short_field_label' is not defined`.
- No protocol, DTC, report export, capture workflow, or measuring-value formula changes.

## v0.5.0 - active Auto-Scan reports and live-data workflow

- Added direct `autoscan` command for live read-only TP2.0 module scanning.
- Added Auto-Scan report export as plain text, JSON, and Markdown.
- Added min/max/delta tracking to the interactive live measuring-block dashboard.
- Added CSV live logging from the interactive engine measuring-block menu.
- Added guided VCDS measuring-block capture workflow in Capture / trace tools.
- Added HVAC measuring-block discovery workflow documentation.
- Kept clear/coding/adaptation scope unchanged; non-engine measuring blocks remain disabled until captured/proven.

## v0.4.6 - Correct measured-value scaling

- Fixes CLI parsing so measuring block numbers like `001`, `003`, `010`, and `011` are accepted as decimal groups.
- Corrects the first-pass measuring value formulas for known BKD cells after an ignition-on/engine-off capture proved `01 69 00` must decode as 0 rpm, not ~840 rpm.
- Updates RPM, pressure, duty/percentage, and air-mass scaling used by engine measuring-block snapshots and live dashboard.
- Leaves unknown formula bytes unresolved instead of pretending they are meaningful.

## v0.4.5 - In-place live measuring block dashboard

- Changes interactive live Engine 01 measuring blocks from scrolling sample output to an in-place terminal dashboard.
- The dashboard redraws the latest field values, sample count, time and recent warnings instead of creating a terminal journal.
- Falls back to the previous scrolling output when stdout is not an interactive colour terminal.
- Direct CLI `live`/`preset` behaviour remains compatible; no TP2.0/KWP protocol, clear-DTC or non-engine measuring-block scope changes.

## v0.4.4 - Live measuring block menu session fix

- Fixed interactive engine live measuring blocks opening the TP2.0 session before user prompts.
- Live/snapshot engine measuring block menu entries now open a fresh short engine session only when the read actually starts.
- This avoids the ECU closing an idle menu-held session with A8 before the first live block request.
- No protocol scope, DTC clear scope or non-engine measuring-block support changed.

## v0.4.3 - Live measuring blocks in interactive menu

- Adds live Engine 01 measuring-block polling to the interactive `start` menu.
- Adds live core preset `001 003 004 011`, live air/boost preset `003 010 011`, and custom live block entry.
- Keeps non-engine measuring blocks disabled until VCDS-captured module block requests are added.
- No TP2.0/KWP protocol changes and no clear-DTC scope changes.

## v0.4.2 - Semantic colour polish

- Adds more semantic colour to the interactive menu and concise Auto-Scan summary.
- Colours clean/no-DTC states green, DTC/warning states yellow, errors/disabled actions red, and headings/module names cyan/bold.
- Keeps existing `--no-colour` / `--no-color` and `--force-colour` / `--force-color` controls.
- Logging remains plain text because ANSI escape sequences are stripped before writing log files.
- No protocol, DTC, clear, capture or measuring-block behaviour changes.

## v0.4.1 - Redaction, concise Auto-Scan and capture menu

- Adds global `--redact-private` to redact VIN/email-like identifiers from terminal output and logs.
- Changes interactive Auto-Scan to a concise read-only summary by default; use `--detail start` for the full TP2.0/KWP dialogue.
- Adds `Capture / trace tools` to the interactive menu:
  - passive VCDS splitter capture with listen-only CAN setup,
  - analyse an existing candump trace,
  - show capture checklist,
  - restore CAN active mode.
- Keeps non-engine clear-DTC and non-engine measuring blocks disabled.
- Documents that MK4-era KW1281/K-line cars such as early EDC15/ASZ platforms are out of scope for this TP2.0-over-CAN tool.

## v0.4.0 - Interactive start menu

- Adds `start`, an interactive workshop-style menu for common tasks.
- Keeps existing direct CLI commands for scripting/regression testing.
- Adds a module-first flow: select module, then read identification, read DTCs, clear DTCs, or measuring blocks.
- Enables interactive Engine 01 read/clear/measuring-block snapshots using the existing proven engine paths.
- Enables interactive read-only DTC/ident access for proven non-engine modules when `--experimental-module` is supplied.
- Keeps non-engine clear-DTC disabled in the menu.
- Keeps non-engine measuring blocks disabled until VCDS-captured block requests are added.
- Adds a read-only autoscan menu option over the proven module set.

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
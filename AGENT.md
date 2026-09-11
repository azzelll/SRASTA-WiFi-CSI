# SRASTA Full-Product Agent Rules

This file supplements the repository's `AGENTS.md`; it does not replace it.
Follow both, resolving conflicts in favour of direct user instructions and the
product proposal.

## Mission

Deliver a locally testable SRASTA product, not a partial proof of concept:

```text
ESP32-S3 transmitter + receiver -> CSI edge runtime -> state machine
-> local API/realtime -> caregiver dashboard/PWA -> local alarm and optional IoT alert
```

The caregiver experience is the contract. Internal models and algorithms may
change with user authorisation, but the following must not change:

- contactless monitoring for home care;
- visible states: `standby`, `normal`, `inactive`, `anomaly`, `critical`;
- fall/inactivity/breathing-indication monitoring and a clear confidence or
  unavailable result;
- anomaly-only camera validation using skeleton/keypoints, not continuous
  visual surveillance;
- local edge decisions and alarm that remain useful offline;
- realtime caregiver dashboard, event history, acknowledgement, and explicit
  emergency-call action;
- honest boundaries: the system is not a medical diagnostic tool.

## Required reading and source priority

Before making a product, architecture, firmware, model, or UI decision, read:

1. the Google Docs proposal linked in `AGENTS.md`;
2. `AGENTS.md`, then this file, then `AI_CONTEXT.md`;
3. relevant README, design docs, source code, tests, and schemas.

The proposal controls product scope and user experience. Local schemas/tests
control implementation correctness. Preserve product requirements when an
implementation gap exists; make the gap explicit instead of reducing scope.

## Data, safety, and privacy invariants

- ESP32-S3 CSI V1 is LLTF/HT20, 128 signed bytes ordered `[imaginary, real]`.
  Decode with `hypot`, use the fixed 52-feature mask (`6..31`, `33..58`), and
  never resize, pad, or shift indices.
- Reject/quarantine capture-profile drift. Preserve metadata needed for quality
  checks, but do not persist raw I/Q or raw MAC addresses in the dashboard DB.
- Keep `data/` unchanged; do not publish, upload, or commit raw recordings.
- Never commit WiFi credentials, tokens, camera imagery, identity data, or
  trained model binaries without explicit user approval.
- Never mislabel mock, replay, injected, or synthetic data as live hardware
  results. The UI must make simulator mode unmistakable.
- Never test falls by asking a vulnerable or untrained person to fall. Do not
  claim medical diagnosis or unmeasured accuracy/latency.
- Camera operation is event-only. Store keypoint summaries only when needed;
  do not implement always-on recording.

## Engineering loop and quality bar

Keep working through this cycle: audit -> checklist -> implementation -> tests
-> local end-to-end exercise -> inspect evidence -> fix -> repeat. A plan,
mocked screen, compiling firmware, or passing isolated unit test is not product
completion.

Required verification includes:

- contract/decoder and invalid-frame tests;
- replay through inference/state persistence;
- API and realtime routes;
- dashboard rendering and user actions for each of the five states;
- a local simulator marked as non-live;
- firmware builds, and flash/serial proof if board ports are known;
- a local runbook and hardware setup guide with commands that another team
  member can repeat.

If hardware is connected, inspect ports safely. Flash only when the TX/RX
mapping is unambiguous. Ask the user for the mapping when it is not. Continue
all software, replay, firmware-build, and local-dashboard work even if live
hardware validation is blocked.

## Completion reporting

Before saying work is complete, run fresh verification and report the exact
commands, outcome, artefact paths, and remaining evidence gaps. Do not hide
skipped tests, placeholders, missing credentials, unavailable hardware, or
unmeasured performance behind a green status.

## Engineering handoff - 2026-09-11

This is an implemented but unfinished product. Preserve the original rules above.
For the latest measured evidence read `ENGINEERING_EVIDENCE.md`,
`ENGINEERING_CHECKLIST.md`, `RUNBOOK_LOCAL.md`, `HARDWARE_SETUP.md`, and
`MODEL_EVALUATION.md`. Treat this handoff as historical evidence, then inspect
current files, processes, ports and health before taking action.

### Direct user decisions that remain active

- Execute `PROMPT.md` as the active engineering task; do actual implementation,
  testing and measurement instead of stopping at a plan.
- Only **one ESP32-S3 receiver**, identified as **COM9**, is connected through
  USB-C. A user-configured **phone hotspot is the WiFi transmitter**. Do not ask
  for a second board or reassign COM9 to TX. Discover the port again if needed.
- The user changed the hotspot and moved it closer. Current credentials, BSSID
  and channel are only in ignored `artifacts/hotspot.local.json`; the generated
  header is ignored `firmware/include/srasta_hotspot.local.h`. Never print or
  commit their contents. Channel was 2 at the last check; verify the local file.
- Pi, camera and buzzer/LED are not available. The user asked to continue on the
  laptop. Hardware validation of those outputs remains a final-product gap.
- Other algorithms/models and other legitimately accessible public datasets
  are explicitly permitted. This overrides the older TCN-only implementation
  preference in the context files. Privacy, capture shape, source attribution,
  test isolation and honest evaluation remain mandatory.
- The user currently cannot perform the requested controlled walking trial.
  **Do not repeatedly ask for that trial on resume.** Continue independent
  engineering and make the missing labelled evidence explicit; resume physical
  collection when the user changes availability. Never request a dangerous fall.
- The user requested this handoff and a GitHub push. This is a continuation
  checkpoint, not a declaration that the final product is ready.

### Runtime and actual device status

Work from the `SRASTA-WiFi-CSI` repository root (the surrounding workspace can
have a parent named `gemastik`). Inspect `http://127.0.0.1:8000/status` before
starting a second process. The dashboard is `http://127.0.0.1:8000/?view=live`.
A serial service was left running; do not assume it survives a different host
or session. Never open another serial reader while the service owns COM9.

```powershell
.venv/Scripts/python code/run_edge_service.py --serial-port COM9 --hotspot-config artifacts/hotspot.local.json --max-packet-gap-ms 100 --db artifacts/live.sqlite3 --port 8000
```

Current policy: inactivity 120 s, confirmation 10 s, motion threshold 0.02,
sudden-motion threshold 0.08. No learned model is active. Confidence is
unavailable; displayed rules are experimental. Do not force the state to
`normal` because a user reports normal activity or lower thresholds simply to
make the dashboard appear successful.

The latest handoff check showed live/fresh serial and inference ready, but
historical counters included long gaps, reconnects and two rejected frames.
This does not establish continuous uptime. `health.fresh`, `inference_ready`,
frame rejection, insufficient-window rejection and queue loss are separate.
Gap/reconnect must invalidate temporal confirmation evidence; persisted critical
alerts and acknowledgements must not be erased as a recovery shortcut.

### Firmware and USB findings

- Environments: `tx`, `rx`, `rx_hotspot`; ESP-IDF 5.4.0 / espressif32 6.10.0.
  All three build. Only receiver COM9 has physical flash/serial evidence.
- Current revision is `srasta-jsonl-v1-paced-idf5.4.0`. LLTF/HT20/128 signed I/Q,
  imaginary-real order and fixed 52-index mask remain unchanged.
- ESP-IDF rejects a protocol bitmap containing only 11N. B/G/N is enabled while
  accepted CSI remains HT20. Serial output buffer is bounded/static to avoid
  main-task stack overflow. WiFi callbacks only copy into the bounded queue.
- Hotspot traffic is ping to its own gateway, target 100 Hz. ESP-IDF waits for
  a reply before the next request; timeout was reduced from 100 ms to one
  interval (10 ms), with numeric sent/reply/timeout diagnostics.
- A 30.47 s test after that fix observed 2,917 additional frames, 97.45 Hz,
  117 inferences and 100% fresh/ready polling without large gaps or queue loss.
  This interval is measured, not an uptime or accuracy guarantee. Later gaps
  still occurred; keep investigating their causes.
- COM9 once remained visible but emitted no bytes and ignored esptool resets.
  User USB power-cycling restored it. The source now propagates idle DTR/RTS,
  reopens a port silent for 5 s with backoff up to 8 s, and preserves critical.
  Software retry did not prove recovery from every physical USB failure.
- Use the short toolchain/temp paths below on Windows. The earlier long
  OneDrive toolchain path and compiler under Windows Temp failed.

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path $env:LOCALAPPDATA 'srasta-pio'
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
.venv/Scripts/python -m platformio run -d firmware -e tx -e rx -e rx_hotspot
```

Do not reflash a healthy receiver merely to resume a session. If a firmware
change needs a flash, stop its reader first and use only `-e rx_hotspot -t upload
--upload-port COM9` after verifying the port. Read the hardware runbook.

### Calibration evidence: not yet accepted

Local summaries are ignored, contain no raw CSI and must not be overwritten:

| Artifact under `artifacts/calibration/` | Result |
| --- | --- |
| `movement-session.json` | 111 observations before the hotspot/position change; do not mix with the new setup |
| `position2-quiet.json` | Failed, zero samples during USB outage |
| `position2-quiet-recovered.json` | 119 quiet observations, 30.20 s, ready 100%, median energy 0.0009468 |
| `position2-normal-activity.json` | Failed continuity, one observation |
| `position2-normal-paced.json` | 116 normal-activity observations, 30.11 s, ready 100%, median energy 0.0011708 |
| `position2-comparison-normal.json` | `not_separated`; threshold null |

Fit p95 quiet was 0.0014473 while fit p25 normal activity was 0.0009790.
Normal activity can include pauses; it is not a movement label for every
window. The quiet and latest normal recordings share preprocessing and stated
physical position but straddle the traffic-timeout firmware change; disclose
that limitation and validate any future calibration with fresh held-out data.
Do not relabel failures, reuse old-position data, or weaken the acceptance
criterion after seeing these results and then claim independent validation.
The tool is `code/tools/calibrate_motion.py`; it uses chronological halves,
checks setup/config, rejects overlap and preserves failed attempts.

### Data/model state and locked test

A fresh clone lacks ignored datasets, credentials, environments and models.
First check whether this host still has them; do not assume a missing artifact
means the previous experiment never ran. Reproduction commands are in the
runbook; preserve existing raw data and output directories.

- CSI-Bench: 365 unmodified primary train/validation H5 files; manifest 494
  entries. Train 288 across six subjects; validation 77 U19; test U21 has 80
  index entries and has **not been downloaded/read**; excluded U22 has 49.
  Do not open the locked test to tune a model. The old 472-entry audit is stale.
- ESP-Fi HAR: 490 CC BY 4.0 ESP32-C3 source-train MAT files, with provenance and
  Git hashes. Source-test not downloaded. Different hardware domain; it was
  used only for disclosed pretraining. WiFall was reviewed but not used.
- Shared preprocessing is `causal-v2-raw-history`. It fixes Hampel freezing a
  sustained change. Old configs/models are rejected and require retraining.
- RF v2 validation fall recall 0.800, specificity 0.378. TCN v2 INT8 recall
  0.250, specificity 0.892. Eighteen alternative 250/500-frame recipes were
  evaluated with train-subject CV; none met recall >=0.88 and specificity
  >=0.80 together. These are development checks, not final event-level metrics.
- ESP-Fi transfer FP32 recall 0.925 but specificity 0.081 (34/37 false positives).
  INT8 collapsed, and train-only recalibration did not fix parity. Runtime
  rejects TFLite with missing/failed parity. Never activate that failed model.
- Do not reuse the old one-class artifact under `code/runs/`. Preserve it and
  user notebooks. U19 is development validation after repeated experiments,
  not a final performance estimate. Read `MODEL_EVALUATION.md` in full.

### Software proof and reproducibility

There are 50 passing unit/API/replay tests without skips. Browser acceptance
covers all five states, desktop/mobile widths, 200% text, offline shell, safe
acknowledgement, explicit emergency dialog without a call, no sensitive cache,
and no external requests. Live browser checks also passed on the actual serial
pipeline. These do not prove physical alarm/camera, physiology, fall accuracy,
phone installation or sustained uptime.

```powershell
.venv/Scripts/python code/tools/verify_local.py
.venv/Scripts/python code/tools/test_live_dashboard.py --out artifacts/live-ui-new-session
```

The harness owns its temporary simulator on a separate port; it does not need
to interrupt the live receiver. `httpx2` is a real dependency of the installed
Starlette TestClient, not a typo. The service is loopback-only; mobile browser
emulation is not proof of secure access from a physical phone.

Local evidence: `artifacts/verification/`, `receiver-recovered.json`,
`receiver-paced-ping.json`, `live-ui-paced-ping/`, `firmware-build-paced-ping.log`,
`firmware-flash-paced-ping.log`, `curated-product-replay.json`, and the model
experiment directories documented in the evaluation report. Raw CSI, real
MACs, passwords, images and model binaries must stay out of Git and cloud.

### Six remaining workstreams to reach a final product

These are six acceptance stages, not six commands or a time estimate. Several
require physical hardware or new ground truth; do not promise completion from
passing software tests alone.

1. Stabilize capture and room calibration: investigate USB/sleep/radio gaps,
   prove recovery and freshness behavior, and accept thresholds only from
   appropriate labelled sessions with an independent check. The walking trial
   is currently unavailable; continue independent diagnostics meanwhile.
2. Establish representative labelled evaluation data: presence/absence, normal
   activity, inactivity, fall events and breathing reference where applicable;
   separate people/sessions before windowing and keep the final test untouched.
   Follow safe collection and privacy constraints; do not ask an untrained
   person to fall or claim event labels from whole-recording labels.
3. Deliver and freeze a reliable model/decision pipeline: train/select on
   allowed data, assess recall/precision/F1/false alerts per hour, check export
   parity, profile compatibility and actual target latency. Retain unavailable
   outputs when evidence is insufficient.
4. Integrate the physical edge kit: Pi, event-only camera/keypoints, buzzer/LED,
   offline alarm behavior and restart. Optional Blynk/MQTT needs explicit
   configuration; never send messages externally without authorization.
5. Complete acceptance on the actual system: all five states end to end,
   realistic disruptions and prolonged operation, breathing/pose reference
   checks, caregiver acknowledgement, safe physical-phone access/PWA install,
   and separately measured suspected/confirmed-event latency. Preserve privacy.
6. Package the reproducible release: pinned dependencies, startup/recovery and
   calibration workflow, deployment setup, security review, usable caregiver
   onboarding, runbooks and a release evidence report. Only declare final after
   applicable gates pass or the user explicitly changes the product scope.

Start a continuation by inspecting the current checkout and health, selecting
an executable unresolved item, implementing it, testing it, and updating the
checklist/evidence. Do not repeat completed work or wait idle for absent hardware
when independent engineering is available. GitHub branch at this checkpoint:
`agent/rebuild-be-ai-milestone`; follow the existing branch unless the user
requests another one. A future branch created by Codex should use `codex/`.


### GitHub publication status at handoff

The implementation checkpoint was committed locally as `6f22d70` on
`agent/rebuild-be-ai-milestone`. The requested push to
`https://github.com/azzelll/SRASTA-WiFi-CSI.git` was rejected with HTTP 403:
the available GitHub credential lacked repository write access. A follow-up
handoff documentation commit may follow it. Publication is **not confirmed**
at this checkpoint; a new GitHub-only clone will not contain the new product
until an authorized push succeeds.

The user has already authorized pushing this work. After repository access is
resolved, inspect local/remote heads and push the reviewed commits normally;
never force-push, change repository destination or publish private artifacts
to work around missing access. The user was asked to either log in with an
account having write access or grant the existing account write access.
Do not remove credentials or change the global account silently. Verify the
remote commit before reporting a successful push.

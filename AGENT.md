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

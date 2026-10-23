# SRASTA — Full Product Engineering Loop Prompt

Copy the prompt below into the coding agent while its working directory is the
root of this repository.

---

You are the lead engineer responsible for delivering **SRASTA** end to end:
firmware for the connected ESP32-S3 devices, local edge runtime, caregiver
dashboard/PWA, and repeatable local and hardware tests. Do not stop at an
audit, plan, mock-up, or partial backend. Work autonomously in an engineering
loop until the definition of done is evidenced.

Before changing anything, read `AGENTS.md`, `AGENT.md`, `AI_CONTEXT.md`,
`README.md`, the applicable files under `docs/`, existing tests, and the
product proposal:

<https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit>

The proposal locks the user-facing product behaviour, terminology, scope, and
privacy promise. Its core product is a contactless, privacy-first safety
monitor for an older adult in home care, based on WiFi CSI and local edge
processing. Preserve the product requirements even when implementation
evidence is incomplete; report gaps instead of silently removing features.

The user explicitly permits a different internal algorithm, model, or signal
processing approach when it is more feasible or reliable. This permission does
not permit different caregiver-facing outputs, weaker privacy, fabricated
confidence, or unsupported medical claims. Mark a simulator as a simulator and
an unverified model as unverified.

## Product contract

Build this complete local-first path:

```text
ESP32-S3 TX -> ESP32-S3 RX CSI -> USB serial / LAN
-> edge validation, preprocessing, and inference/rule engine
-> state machine, SQLite event log, and local alarm adapter
-> API plus realtime stream -> responsive caregiver dashboard/PWA
-> optional Blynk/MQTT output adapter when credentials are supplied
```

The local dashboard must work without cloud, a Blynk token, or an internet
connection. Treat Blynk/MQTT as optional fail-closed notification adapters.

### CSI contract that must not drift

- LLTF-only, HT20, exactly 128 signed I/Q bytes.
- I/Q byte order is `[imaginary, real]`.
- Amplitude is `hypot(imaginary, real)`.
- Use only indices `6..31` and `33..58`: exactly 52 amplitude features.
- Never resize, pad, or shift CSI features.
- Mask `first_word_invalid` without shifting feature positions.
- Reject/quarantine incompatible capture profiles and invalid metadata.
- Keep raw CSI, raw MAC addresses, video, secrets, and personal data out of
  SQLite, the dashboard, Git, and external services.

### Caregiver-facing behaviour

The state machine has exactly these visible states:

| State | Meaning | Required response |
| --- | --- | --- |
| `standby` | no confirmed person/presence | healthy monitoring, no alert |
| `normal` | ordinary activity | green status |
| `inactive` | no motion beyond configured limit | early caregiver warning |
| `anomaly` | potential fall, breathing anomaly, or uncertain result | event-only keypoint validation and early alert |
| `critical` | anomaly is confirmed or persistent | red alert, local alarm, emergency notification |

Create a responsive desktop-and-mobile caregiver dashboard/PWA consistent with
the proposal mock-up: navy visual identity; clear green/orange/red state
cards; identity and room; last update; device health; activity/motion trend;
breathing estimate and quality; alert history; realtime notifications; and
critical-screen acknowledgement.

The dashboard must include an explicit, user-initiated “Panggil Bantuan
Darurat” action and an acknowledge action. It must never make an emergency call
without a caregiver action. The camera is event-only: when an anomaly requires
validation it may expose a keypoint/skeleton result, never a permanent camera
stream or continuous video recording. Breathing output is an indication or
estimate, never a diagnosis, and must be withheld when quality is insufficient.

## Engineering loop

Repeat this loop until all acceptance criteria pass:

1. Inspect the working tree, implementation status, test suite, firmware, API,
   and UI. Preserve existing user changes.
2. Maintain a clear checklist of completed, active, unproven, and externally
   blocked requirements.
3. Implement the smallest correct vertical slice or fix.
4. Run relevant unit, integration, API, UI, firmware-build, and local-demo
   tests. Treat failing or skipped required tests as active work.
5. Exercise the actual local product flow, inspect the result, and fix any
   placeholder, dead control, contract drift, insecure secret handling, or
   regression.
6. Repeat. Do not stop after making a plan or after one subsystem passes.

Do not ask for permission for ordinary engineering work. Ask only when a real
external blocker remains, such as an ambiguous mapping between two physical
serial ports, missing hardware, missing credentials, or a decision that would
materially alter the product.

## Firmware and live-device work

Implement and document both roles:

1. **TX** produces controlled WiFi traffic on the configured channel/profile.
2. **RX** captures CSI and emits versioned JSONL frames to the host.

Provide non-secret configuration templates, reproducible build/flash commands,
and serial diagnostics. If connected boards are unambiguously identified, build
and flash the correct roles, then prove that the RX emits valid frames and that
the edge service/dashboard consume them. If TX/RX port mapping is ambiguous,
do not guess: ask the user to identify the two ports.

Never require a person to perform a dangerous fall. Use replay, controlled
simulator inputs, fixtures, or a user-approved safe procedure for validation.

## Local test harness

Deliver one documented command or small command sequence that starts the local
service and dashboard, runs replay or a simulator, and enables a clearly marked
development-only state controller. It must exercise all five states and their
transitions without pretending that simulated events are live CSI results.

Add automated coverage for the CSI decoder/validator, state transitions,
SQLite events, API/realtime flow, dashboard state rendering, acknowledgement,
event-only camera behaviour, simulator labelling, replay-to-state integration,
and required firmware builds.

## Definition of done

Do not declare this complete until all applicable items are backed by fresh
evidence:

- TX/RX firmware builds; flash and serial evidence when physical boards and
  unambiguous ports are available.
- Replay and, when available, live serial CSI both reach the edge runtime.
- The dashboard/PWA runs locally, uses live API/realtime data rather than
  hard-coded UI values, and works on desktop and narrow mobile layouts.
- Each of `standby`, `normal`, `inactive`, `anomaly`, and `critical` is tested
  locally and visible in the UI.
- Alarm behaviour, event-only keypoint validation, SQLite history, optional
  fail-closed external adapters, and acknowledgement actions are tested.
- All required tests run without hidden skips or false pass conditions.
- `RUNBOOK_LOCAL.md` documents setup, start, tests, demo states, and recovery.
- `HARDWARE_SETUP.md` documents wiring, configuration, build, flash, serial
  verification, and the exact unresolved hardware blocker if any.
- README and a final evidence report record exact commands, test results,
  artefacts, limitations, and only claims that have been measured.

Do not commit credentials, Blynk tokens, WiFi passwords, raw CSI recordings,
trained-model binaries, or files under `data/` unless the user explicitly
authorises it. Begin the engineering loop now.

---

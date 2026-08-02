# SRASTA implementation guide for Claude Code

## Read first

Read the Google Docs proposal completely before making any product, feature,
architecture, or delivery decision:

<https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit>

The proposal is SRASTA's **sole product source of truth**. Its scope, features,
priorities, user experience, terminology, and product claims are not open to
challenge, narrowing, replacement, or reinterpretation by an implementer.
Then read `AI_CONTEXT.md` for the CSI implementation contract and current-code
audit. Local schemas, code, and tests control implementation correctness only;
they never overrule the proposal. If implementation evidence is incomplete,
preserve the product requirement and report the implementation gap rather than
removing, deferring, or recasting the requirement.

## Scope

Build the software required to realise the proposal. The current WiFi-CSI
fall-detection path is one implementation workstream:

`ESP32-S3 CSI receiver -> USB serial -> Raspberry Pi -> preprocessing -> edge model -> dashboard / Blynk`

The hardware is not connected yet. Implement parsers, tests, replay mode,
training, and backend so the system can run as soon as ESP32 frames arrive.

It is not a ceiling on the product scope. Do not remove, postpone, or label as
out of scope any proposal-defined capability, including activity-abnormality,
inactivity, breathing, or anomaly-triggered camera-validation work. Keep each
capability's evidence and implementation status explicit.

## Non-negotiable CSI contract

- ESP32-S3 payload is signed I/Q bytes, ordered `[imaginary, real]`.
- A stable LLTF-only capture produces 128 bytes = 64 complex positions.
- Convert every pair with `hypot(imaginary, real)`.
- Use the fixed usable-index mask from `AI_CONTEXT.md`, yielding exactly 52
  amplitude features per frame.
- Preserve packet metadata: sequence, timestamp, RSSI, noise floor, channel,
  bandwidth, signal mode, MCS, `len`, and `first_word_invalid`.
- Reject or quarantine a frame whose configuration differs from the active
  capture contract. Never pad, subsample, or resize raw CSI to make a tensor
  fit.
- If `first_word_invalid` is set, mask the invalid positions without shifting
  the remaining subcarrier indices.

## Data and evaluation rules

- Use `data/curated/esp32_s3_fall_v1/manifest.csv` as the training index.
- The raw CSI-Bench corpus remains in `data/csi-bench/`; do not edit it.
- `data/external/wifall/` contains 928 ESP32-S3 I/Q recordings. Its dataset
  card has no stated license, so keep it local and research-only. It may only
  be used for representation pretraining or a separately disclosed ablation;
  do not treat every window of a continuous fall recording as a labelled fall.
- `data/external/esp_fi_har/` contains 560 CC BY 4.0 ESP32-C3 amplitude
  recordings. It may be used for supervised pretraining, with attribution to
  Wen et al. (2026), but it is a different hardware/capture domain.
- External data must never enter `esp32_s3_fall_v1/splits/test.csv` or be used
  to report SRASTA final performance. Fine-tune/evaluate on held-out ESP32-S3
  source data and later a separate local ESP32-S3 capture set. Read
  `data/external/README.md` and source READMEs before using these files.
- A recording has shape `[64, time, 1]`; transpose/select it to `[time, 52]`.
- Do not mix `device_HP` 232-feature recordings with ESP32 training input.
- Split by subject/session before creating windows. Random window splits leak
  nearly identical parts of one recording into train and test.
- Treat data under `data/` as CC BY-NC-ND research material. Do not publish,
  upload, redistribute, or alter the source recordings.

## Current CSI fall-path model decision

The existing CSI fall-path implementation uses a **TCN-Lite classifier**, taking
a `[time, 52]` amplitude sequence and exported as INT8 TensorFlow Lite for
Raspberry Pi inference. Start with three residual Conv1D blocks (kernel 3, 24
channels, dilations 1/2/4), global average pooling, and a two-class head. Use a
250-frame window initially, but choose final window length only with grouped
validation. This is an implementation decision for that path; it must not be
used to countermand any broader proposal requirement.

Implement a transparent motion-trigger + Random Forest classifier as an
internal correctness/debugging baseline. It does not replace any
proposal-defined product functionality.

Do not use the current `runs/srasta_fall/model_int8.tflite`: it was generated
from an invalid one-class, shape-mismatched training run. Do not begin with an
LSTM or Transformer; the available ESP32 dataset is small and an interpretable
baseline plus compact TCN is the appropriate reliability/performance tradeoff.

## Implementation expectations

- Keep shared preprocessing in one importable module used by both offline
  training and Raspberry Pi inference. Serialize the preprocessing config next
  to the model.
- Provide a serial-independent replay mode using a recorded H5/NPZ sample.
- Build an edge service with explicit health/status/event endpoints, a
  bounded frame queue, local SQLite event logging, and a rate-limited alert
  adapter. Blynk is an output adapter, not the inference runtime.
- Keep raw CSI local. The dashboard receives state, confidence, signal-quality,
  latency, and event summaries only.
- Separate `suspected_fall` from `confirmed_fall`: confirmation requires a
  post-event inactivity interval and therefore cannot truthfully have the same
  latency target as a motion trigger.

## Validation required before claiming success

1. Unit tests for I/Q decoding, invalid-word masking, fixed 52-feature shape,
   H5 axis conversion, and configuration rejection.
2. A replay/integration test from curated data through preprocessing and model
   inference.
3. Grouped validation with no subject/session overlap between train and test.
4. Report event-level recall, precision, F1, false alerts per hour, packet
   drop rate, model inference latency, suspected-fall latency, and
   confirmed-fall latency separately.

## Existing files to replace carefully

- `../train_tcn_lite_csi.py` is outside this Git repository and contains an
  invalid axis assumption. Do not treat it as a reliable baseline.
- `code/infer_blynk.py` parses raw values but currently does not decode I/Q or
  enforce the ESP32 frame contract. Preserve any useful Blynk configuration
  behavior while replacing its CSI path.
- Leave user changes in `code/train_tcn_lite_csi.ipynb`, `code/runs/`, and
  `data/` untouched unless the task specifically targets them.

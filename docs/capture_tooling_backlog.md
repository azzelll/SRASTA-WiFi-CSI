# SRASTA capture-tooling backlog

This backlog makes the local ESP32-S3 data path ready without changing model
metrics or pretending that a hardware capture already happened. It follows
[esp32_s3_capture_protocol.md](esp32_s3_capture_protocol.md).

## Compatibility decision

`code/srasta_csi/contract.py` is the strict **runtime inference** JSONL schema.
It accepts only the fields required for low-latency inference:

```text
version, sequence, local_timestamp_us, sender_mac, rssi, noise_floor,
channel, bandwidth, sig_mode, mcs, rx_state, len, first_word_invalid, iq_bytes
```

Future protocol-v1 capture archives must retain their session/configuration and
annotation metadata in `capture_config.json`, `events.jsonl`, `qa_report.json`,
and `manifest.csv`. A host capture adapter may project a valid archived frame
onto the runtime subset for inference; it must not loosen the runtime validator
or inject archival fields into its strict payload.

## Milestone 1 — host recorder — implemented, fixture-covered

- `code/tools/record_esp32_capture.py` creates a user-selected session folder
  only outside Git and `data/`, then writes immutable `capture_config.json`
  before accepting frames.
- `code/srasta_csi/capture_archive.py` hashes the canonical configuration,
  binds it to each archival frame, appends valid raw frames only to
  `frames.jsonl`, records `capture_summary.json`, and emits bounded payload-free quarantine diagnostics.
- It counts sequence epoch, gaps, duplicates, timestamp reversals, valid, and
  quarantined frames without repairing, padding, reordering, or synthesizing.
- The archive has an explicit projection to the strict inference JSONL subset;
  it does not broaden `srasta_csi.contract.py`.

## Milestone 2 — event annotation and QA — implemented, fixture-covered

- `code/tools/qa_capture.py` and `code/srasta_csi/capture_qa.py` validate
  separate observer events on the receiver monotonic clock, session/config
  consistency, checksums, fixed capture contract, frame ordering, reconciliation,
  no-overlap provenance, and subject/session split consistency.
- QA validates fall onset, event end, and post-fall inactivity ordering, plus
  nonfall, no-person, interference, calibration, recovery, and aborted events.
- It emits `qa_report.json`, `checksums.sha256`, and one append-only root-manifest
  row with `pending`/`accepted`/`rejected`. Acceptance uses the declared
  `max_quarantine_fraction`, `max_sequence_gap_fraction`, and
  `minimum_nonfall_observation_s`, never retrospective thresholds.
- Fixture tests cover valid frames, gaps, duplicates, timestamp reversals,
  malformed/config-hash/bandwidth/length failures, no raw-IQ quarantine leakage,
  reconciliation failures, and invalid fall timing.

A passing fixture is not a completed hardware pilot. Run a no-fall serial pilot
and inspect the generated protected local archive before collection.

## Milestone 3 — firmware emitter

- Add a separate ESP-IDF ESP32-S3 project with a pinned IDF revision.
- Emit LLTF-only HT20 CSI from the controlled sender as exactly 128 signed
  bytes in `[imaginary, real]` order, with monotonic timestamp, sequence and
  documented epoch/reset, RSSI/noise/channel/sig mode/MCS/rx state,
  `first_word_invalid`, and immutable firmware revision.
- Firmware only emits data; host QA, not firmware JSON parsing, decides whether
  a session is valid.

## Milestone 4 — desktop fixture and pilot

- Provide deterministic protocol frames for valid input, gaps, duplicates,
  timestamp reversals, wrong hash/bandwidth/length, and malformed JSON.
- Run the recorder/QA self-check before a hardware pilot.
- Conduct a no-fall pilot first. Inspect configuration consistency, sequence
  coverage, timing, recorder summary, and metadata before any safety-reviewed
  fall collection.

## Milestone 5 — collection and split freeze

- Follow the safety/consent rules in the capture protocol; do not ask vulnerable
  people to enact falls.
- Collect continuous nonfall/no-person/confuser intervals and controlled falls
  with independent observer annotations.
- Split by new subject and session before window extraction. Freeze a local
  held-out cohort before model/threshold selection.
- Only accepted sessions can be transformed into `[time,52]` model windows.

Completion of these milestones prepares a credible new evaluation corpus. It
is not a final model result by itself.

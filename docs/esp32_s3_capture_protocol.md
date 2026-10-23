# ESP32-S3 continuous capture protocol

Protocol version: `srasta-esp32-s3-capture-v1`.

This is a proposed local research-capture protocol. It creates a verifiable
continuous-recording corpus for SRASTA; it does not alter current data,
training, or runtime code. It uses pseudonymous IDs and stores no Blynk token,
Wi-Fi password, or other credential in capture data.

## 1. Fixed capture contract

Every accepted frame must use the following immutable profile:

```text
receiver:       ESP32-S3
LTF:            LLTF only
bandwidth:      HT20
raw CSI length: 128 signed int8 bytes
raw layout:     [imag_0, real_0, ..., imag_63, real_63]
model feature:  amplitude = hypot(imag, real)
usable indices: 6..31 and 33..58 (exactly 52 channels)
```

The session starts by writing `capture_config.json` and calculating its SHA-256
as `capture_config_sha256`. The JSON must name the sender/receiver board model,
ESP-IDF and firmware revision, radio channel, bandwidth, LLTF configuration,
antenna arrangement, nominal sender rate, sender identity, room/site
pseudonyms, and the exact usable-index list. A configuration change ends the
session; it does not create an in-session exception.

## 2. JSONL v1 frame schema

One line in `frames.jsonl` represents one receiver frame. `timestamp_monotonic_us`
is the required packet timestamp used for alignment; it must be taken as close
to receiver capture as the firmware permits. `captured_at_utc` is for audit
only and must not replace the monotonic timestamp.

```json
{
  "schema_version": "srasta.csi.frame.v1",
  "record_type": "frame",
  "session_id": "SES_20260729_001",
  "subject_id": "SUB_014",
  "capture_config_sha256": "<64-lowercase-hex>",
  "sequence": 1842,
  "sequence_epoch": 0,
  "timestamp_monotonic_us": 823456789012,
  "captured_at_utc": "2026-07-29T10:42:11.123456Z",
  "sender_mac": "02:00:00:00:00:01",
  "rssi_dbm": -48,
  "noise_floor_dbm": -92,
  "channel": 6,
  "bandwidth": "HT20",
  "sig_mode": "HT",
  "ltf": "LLTF",
  "mcs": 0,
  "rx_state": 0,
  "len": 128,
  "first_word_invalid": false,
  "iq_order": "imag_real",
  "iq_bytes": [-3, 14, 7, 9],
  "firmware_revision": "<immutable-build-id>"
}
```

Required validation rules:

- `schema_version`, `session_id`, `subject_id`, config hash, sequence,
  timestamp, radio metadata, and `iq_bytes` are mandatory for every line.
- `sequence` is a non-negative integer. Increment it for every observed frame,
  including invalid or quarantined frames. Increment `sequence_epoch` only on
  a documented wrap/reset, never silently.
- `timestamp_monotonic_us` must be strictly increasing within a sequence epoch.
  Preserve gaps; do not manufacture rows to make sampling appear regular.
- `bandwidth == "HT20"`, `ltf == "LLTF"`, `len == 128`, and `iq_order ==
  "imag_real"` are mandatory. `iq_bytes` contains exactly 128 integers in
  `[-128, 127]`.
- Keep `first_word_invalid` as received. The decoder retains the fixed
  52-channel shape and masks affected positions; it never shifts indices.
- `sender_mac` must be the controlled capture transmitter. Retain raw MAC only
  in protected local storage; use `sender_id` in any exported derivative.

Do not place annotations into a frame row. Frame evidence and human annotation
remain separate so that event revisions do not rewrite raw CSI.

## 3. Required event annotations

Store `events.jsonl` beside the frames. All event times are on the same
monotonic clock as `timestamp_monotonic_us`.

```json
{
  "schema_version": "srasta.csi.event.v1",
  "event_id": "EVT_20260729_004",
  "session_id": "SES_20260729_001",
  "subject_id": "SUB_014",
  "event_type": "fall",
  "activity_label": "controlled_fall",
  "onset_monotonic_us": 823478000000,
  "event_end_monotonic_us": 823480300000,
  "post_event_inactivity_start_monotonic_us": 823480300000,
  "post_event_inactivity_end_monotonic_us": 823505300000,
  "annotation_method": "two_observer_button_log",
  "annotator_ids": ["ANN_02", "ANN_05"],
  "review_status": "reconciled",
  "notes": ""
}
```

For every fall record, require all four temporal fields above. `event_end` is
the end of the fall event, not the end of the following stationary period. If
the participant recovers, add a separate `recovery` event. If a planned event
is aborted, create an `aborted_event` annotation and retain its continuous CSI
as non-training evidence until reviewed.

Also annotate, with start/end timestamps:

- `nonfall_activity` with a controlled activity label;
- `no_person` intervals when the room is intentionally unoccupied;
- `interference` intervals (for example, another person enters, controlled
  sender failure, or configuration anomaly);
- `calibration` intervals; and
- `inactivity_without_fall` when a stationary period is not a post-fall state.

Use two independent observers or one observer plus an approved synchronized
reference process. Resolve disagreements before the session can enter a split.
Do not put identifying participant details in `notes`.

## 4. Safe fall collection rules

- Collect only under an approved institutional/site safety plan and informed
  consent process. Participation is voluntary; stop immediately for discomfort,
  fatigue, or an unsafe environment.
- Do not ask vulnerable people, people who are unwell, or untrained performers
  to enact falls. Do not collect unconsciousness, head-impact, stair, furniture,
  or unassisted hard-surface falls.
- Use trained adult performers, a suitable certified impact surface, clear
  landing area, and dedicated spotters. A supervisor may abort any trial
  without penalty and the aborted annotation must be preserved.
- Schedule rest, limit repetition according to the site safety plan, and do
  not use fatigue to obtain variability. Do not obscure exits or delay normal
  access to help.
- Keep raw CSI, annotations, consent references, and any optional reference
  material in access-controlled local storage. Reference material is optional;
  it must not be exported with the research corpus unless separately authorised.

## 5. Subject/session split policy

Assign a random pseudonymous `subject_id` once, before capture. Allocate each
subject to `train`, `validation`, or `test` before windowing, and freeze that
assignment in the root manifest. A subject belongs to exactly one split.

For final evaluation, additionally hold out complete sessions, capture dates,
and (where practical) a room/site from training. Never split adjacent windows,
events, or calibration intervals across partitions. Keep all frames tied to a
single `session_id` together.

The local cohort must be new: no copied, replayed, transformed, or overlap
with any recording or participant in `data/csi-bench`, `data/curated`, or
`data/external`. The current U21 test data and all other locked SRASTA test
records remain unavailable for model, preprocessing, threshold, calibration,
or protocol-selection decisions.

## 6. Suggested continuous activities

Every session should have an event plan with pre-event, event, and post-event
timestamps. Capture ordinary activity continuously rather than restarting a
file for each label.

- No-person baseline; quiet seated/standing occupancy; lying still; routine
  walking; turns; sit-to-stand and stand-to-sit; chair transfers; object pickup;
  bed/sofa approach and departure; normal paced room movement.
- Safe confusing non-fall actions: quick sit, kneel, squat, bend, stumble
  recovery, assisted descent, and an object drop. Include only actions allowed
  by the site safety plan.
- Controlled fall events with a pre-event routine, the separately annotated
  event, and a clearly annotated post-event inactivity interval. Include
  recovery as a separate event when it occurs.
- Operational negatives: routine household-like movement, door movement,
  permitted background interference, and intentional no-person intervals.

Record planned activity labels, but retain observer timestamps as the source of
truth. Activity names describe collection events; they are not a claim about a
person's health or condition.

## 7. Proposed folder structure

The following is a future local-capture layout. It is not a request to add raw
data to this repository.

```text
local_capture_v1/                         # protected local storage, not Git
├── README.md
├── manifest.csv
├── protocol/
│   ├── srasta-esp32-s3-capture-v1.md
│   └── activity_plan_v1.csv
├── sessions/
│   └── SES_20260729_001/
│       ├── capture_config.json
│       ├── frames.jsonl
│       ├── events.jsonl
│       ├── qa_report.json
│       └── checksums.sha256
└── derivatives/                          # generated only after acceptance
    └── release_<id>/
        ├── accepted_manifest.csv
        └── split_freeze.csv
```

Keep consent and contact information in the approved restricted records
system, not this tree. `manifest.csv` uses pseudonymous IDs and an
`authority_ref` that contains no personal information.

## 8. Manifest CSV schema

One row represents one session. Required columns:

```text
session_id,subject_id,split,site_id,room_id,capture_date_utc,
capture_start_monotonic_us,capture_end_monotonic_us,
capture_config_sha256,firmware_revision,sender_id,receiver_model,
ltf,bandwidth,raw_len,iq_order,usable_indices,
frame_count,valid_frame_count,quarantined_frame_count,
sequence_gap_count,duplicate_sequence_count,nonmonotonic_timestamp_count,
observed_duration_s,nonfall_observation_s,no_person_observation_s,
postfall_inactivity_s,fall_event_count,nonfall_event_count,
event_annotation_status,observer_reconciliation_status,
frames_sha256,events_sha256,qa_report_sha256,
source_corpus,overlap_check_status,authority_ref,acceptance_status,
rejection_reason
```

Definitions:

- `source_corpus` must be `local_capture_v1`; a row sourced from any existing
  corpus cannot enter the independent final set.
- `nonfall_observation_s` is the sum of valid, reviewed continuous non-fall
  intervals after removing fall, recovery, interference, calibration, and
  quarantined spans. It is the denominator candidate for false alerts per
  hour.
- `overlap_check_status` is `passed` only after both subject and recording
  provenance checks confirm no overlap with existing SRASTA partitions.
- `acceptance_status` is initially `pending`, then `accepted` or `rejected`.
  A rejected session is never silently repaired into an accepted one; preserve
  the reason and collect a new session.

## 9. Acceptance checks before training

Run these checks before a session enters any training, validation, or test
manifest:

1. **Schema and integrity:** every JSONL record validates against v1, hashes
   match, mandatory files exist, and frame/event session IDs agree.
2. **Capture contract:** every usable frame declares S3/LLTF/HT20/128/
   `imag_real`; no configuration hash mismatch is accepted. Mixed profiles are
   quarantined, never padded, resized, or relabelled.
3. **Raw decoding:** all I/Q values are signed int8; decoding pairs as
   `[imaginary, real]` produces 64 amplitudes; selecting exactly indices
   `6..31, 33..58` produces `[time, 52]`. `first_word_invalid` is masked
   without index shifting.
4. **Temporal integrity:** sequence gaps, duplicate sequences, resets, and
   timestamp reversals are enumerated. Sampling behaviour is measured from
   timestamps; nominal 100 Hz is never assumed. The project must predeclare
   allowable loss and coverage criteria before looking at test outcomes.
5. **Annotation integrity:** every fall has valid onset < event end <=
   inactivity start < inactivity end, all times fall within its frame range,
   and observer reconciliation is complete. Interference and aborted events
   are excluded according to a written rule, not retrospectively.
6. **Exposure integrity:** reviewed continuous non-fall duration is present
   and computable for every final-test session. Report the exact denominator
   used for false alerts per hour and exclusions applied to it.
7. **Split and provenance integrity:** a subject/session appears in one split
   only; no window-level split is permitted. The root manifest records passed
   no-overlap checks against all current SRASTA records. Locked U21 and other
   test records are never read for selection.
8. **Release integrity:** only accepted sessions enter a versioned derivative
   manifest. Preserve raw data separately; do not commit raw CSI, credentials,
   trained artifacts, or personal information to this repository.

Passing these checks makes a corpus *eligible for a future final-evaluation
review*; it does not itself establish model performance.

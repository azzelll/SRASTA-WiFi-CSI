# Final SRASTA validation data gap

## Decision

The datasets currently available in this workspace are insufficient for final
SRASTA validation. None supplies, in one independently held-out corpus, the
entire chain required to calculate event metrics and false alerts per hour for
the ESP32-S3 CSI contract.

This is a data-adequacy conclusion, not a model conclusion. No model change,
model comparison, threshold adjustment, or claim of final performance follows
from this document.

## What is available and why it is not enough

| Source | Useful evidence | Final-validation gap |
| --- | --- | --- |
| `data/curated/esp32_s3_fall_v1` | 472 indexed ESP32 CSI-Bench fall/non-fall H5 recordings; canonical conversion to `[500, 52]`; subject-disjoint development splits. | The indexed files are fixed 500-frame recordings, not a separately held-out local monitoring corpus. The audit cannot verify packet sequence, released onset/offset, post-fall inactivity, or enough continuous labelled non-fall time. It also overlaps the current SRASTA source partition by definition. |
| `data/csi-bench` / CSI-Bench public source | Public paper reports sessions, fall labels, subject IDs, environments, and a smaller ESP32-S3 portion. | The public documentation does not establish the full released ESP32-S3 metadata needed for the contract: LLTF-only/HT20/128-byte configuration, packet sequence, usable event boundaries, inactivity, and a valid false-alerts-per-hour denominator. The locked SRASTA test records, including U21 where applicable, cannot be used for selection or tuning. |
| `data/external/wifall` | ESP32-S3 source, per-frame timestamps, nominal 100 Hz, and raw signed I/Q values. | It has 104 bytes / 52 complex values rather than SRASTA's 128 bytes / 64 positions, no stated data licence, no documented sequence, no verified fall onset/offset or inactivity, and insufficient verified continuous non-fall duration. It is not a final set. |
| `data/external/esp_fi_har` | CC BY 4.0, fall and six other activities, amplitude `[950, 52]`, participant/trial naming. | ESP32-C3 rather than ESP32-S3; pre-cut amplitude clips; no packet timestamps/sequence, event boundaries, inactivity, or continuous non-fall duration. |

The full source-by-source evidence is in [public_dataset_audit.md](public_dataset_audit.md).

## Missing final-evaluation evidence

The required local corpus must close every gap below. If even one is unknown,
the corpus is development-only until it is corrected or re-annotated.

| Requirement | Current status | Required correction |
| --- | --- | --- |
| ESP32-S3 LLTF/HT20, 128 signed int8 bytes, `[imaginary, real]` | No independently held-out local set currently records the full configuration as a contract. | Record the immutable per-session configuration and hash it into every frame/manifest row; quarantine configuration drift. |
| Per-packet timestamp and monotonic sequence | Not established for current curated/external final candidates. | Persist receiver monotonic timestamp and a capture sequence on every raw frame; measure gaps and duplicates. |
| Fall onset and event end | Not consistently released or verified as timestamps. | Create an event ledger with onset and end on the same monotonic clock as frames. |
| Post-fall inactivity | Missing. | Annotate the beginning and end of the post-event inactivity interval separately from the fall event. |
| Subject and session identity | Available only partially and not as a local held-out evaluation cohort. | Use pseudonymous immutable subject and session IDs, and retain split provenance. |
| Continuous non-fall exposure | Existing clips do not establish an eligible denominator. | Collect labelled continuous no-fall observation across ordinary activities, quiet occupancy, and no-person intervals; calculate the denominator from timestamps after exclusion rules. |
| Independent test set | Current sources overlap the current SRASTA corpus or cannot prove independence. | Enrol and freeze new local held-out subjects and sessions. Do not copy, replay, or derive them from `data/csi-bench` or `data/external`. |
| Research-use authority | WiFall and several public leads have unclear data terms. | Store consent/collection authority outside the repository and record only its non-identifying reference in the manifest. |

## Consequences for evaluation

- Do not report final recall, precision, F1, or false alerts per hour from the
  current public/external sources as SRASTA final results.
- Do not use the current U21 test data, or any other locked SRASTA test data,
  to choose models, preprocessing parameters, thresholds, calibration, or
  capture acceptance thresholds.
- External data may be used only in the roles recorded in the audit, with
  source provenance and separation from SRASTA's main test set. It cannot
  supply the final false-alerts-per-hour denominator.
- The existing `code/runs/srasta_fall` artifact remains invalid and must never
  be cited as training or evaluation evidence.

## Required next dataset

The next dataset is a newly collected, local ESP32-S3 corpus governed by
[esp32_s3_capture_protocol.md](esp32_s3_capture_protocol.md). It must be
accepted session by session, then split by subject before window extraction.
Only its frozen held-out subjects/sessions may be used for the next final
evaluation stage.

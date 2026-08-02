# Baseline training data plan

No scraping is required for the first SRASTA baseline. The repository already
contains a local CSI-Bench corpus and a curated, subject-disjoint manifest;
using that source is more defensible than mixing unverified online downloads.
Raw CSI stays local and is never duplicated by these commands.

## Primary data: ready now

`data/curated/esp32_s3_fall_v1/manifest.csv` is the sole entry point for the
baseline. It indexes 472 ESP32 FallDetection H5 recordings. Each source
recording is `[64, 500, 1]`; the shared reader transposes it and selects fixed
indices `6..31` and `33..58` into `[500, 52]` amplitude input.

| Partition | Subjects | Fall | Nonfall | Total | Permitted purpose |
| --- | --- | ---: | ---: | ---: | --- |
| Train | U08, U09, U11, U12, U17, U18 | 170 | 118 | 288 | Fit model parameters. |
| Validation | U19 | 40 | 37 | 77 | Select/diagnose candidates only. |
| Locked test | U21 | 40 | 40 | 80 | One final frozen-model proxy report only. |
| Excluded | U22 | 27 | 0 | 27 | Never train or validate: only one class. |

The split occurs before windowing. A baseline takes one deterministic centered
250-frame window after causal preprocessing; it does not create random windows
or resize raw CSI.

## Train the transparent sanity-check baseline

From the repository root, install `code/requirements-train.txt`, then run:

```bash
PYTHONPATH=code python code/train_srasta_rf_baseline.py \
  --manifest data/curated/esp32_s3_fall_v1/manifest.csv \
  --data-root data \
  --out-dir artifacts/srasta_rf_baseline
```

This reads only train and validation recordings. It writes the inspectable
motion features, Random Forest, shared preprocessing and capture-profile
configuration, split report, and validation-only metrics under the ignored
`artifacts/` directory. It is an internal correctness baseline, not the final
TCN-Lite INT8 or deployment candidate.

After all choices are frozen, obtain the single locked test proxy report with:

```bash
PYTHONPATH=code python code/train_srasta_rf_baseline.py \
  --manifest data/curated/esp32_s3_fall_v1/manifest.csv \
  --data-root data \
  --out-dir artifacts/srasta_rf_final_report \
  --evaluate-locked-test
```

Do not rerun the test command to tune trees, features, thresholds, or
preprocessing.

## External data: separate and restricted

| Source | Local availability | Allowed role |
| --- | --- | --- |
| WiFall | 928 ESP32-S3 raw-I/Q CSV recordings | Representation pretraining or separately disclosed ablation only; data license is not documented. |
| ESP-Fi HAR | 560 ESP32-C3 `[950, 52]` amplitude MAT recordings | Supervised representation pretraining from its source-train partition only, with Wen et al. (2026), CC BY 4.0 attribution. |

Neither source enters this manifest, the locked test, or any SRASTA final
metric. Scraping a third-party dataset is deferred until its dataset license,
hardware configuration, per-file subject/session identifiers, temporal labels,
and continuous negative exposure have been verified.

## What still needs new collection

The H5 clips lack raw I/Q bytes, packet sequence/timestamps, fall onset/offset,
post-fall inactivity annotations, and continuous non-fall duration. Therefore
they cannot substantiate packet-drop rate, false alerts/hour, event-level
metrics, or real suspected/confirmed-fall latency. Collect new data only under
the protected protocol in `docs/esp32_s3_capture_protocol.md`.

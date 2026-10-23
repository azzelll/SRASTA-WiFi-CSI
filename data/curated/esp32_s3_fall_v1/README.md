# ESP32-S3 Fall Detection v1

This directory is a reproducible index over the unmodified CSI-Bench raw
recordings in `../../csi-bench/`. It intentionally does **not** duplicate the
source H5 files.

## What is included

- 472 CSI-Bench FallDetection recordings captured with `device_ESP32`.
- 277 `fall` recordings and 195 `nonfall` recordings.
- Raw H5 shape: `[64, 500, 1]` = `[subcarrier position, time, stream]`.
- Canonical model input: `[500, 52]` after transposing and selecting indices
  `6..31` and `33..58`.

`manifest.csv` is the only allowed entry point for training. It gives the raw
path, label, subject, environment, session, source shape, expected feature
count, and grouped split.

## Split policy

The split is subject-disjoint to avoid testing on windows from the same person
used for training. A subject with only one class is placed in `excluded.csv`,
not silently used to make an invalid validation result look better.

## Provenance and license

- Dataset: CSI-Bench: A Large-Scale In-the-Wild Dataset for Multi-task WiFi
  Sensing, NeurIPS 2025.
- Dataset source: <https://www.kaggle.com/datasets/guozhenjennzhu/csi-bench>
- Paper: <https://arxiv.org/abs/2505.21866>
- License declared by the supplied corpus: CC BY-NC-ND 4.0.

Use only for local, non-commercial research. Do not upload, redistribute, or
modify source recordings. The generator
`code/tools/build_esp32_fall_dataset.py` can rebuild this index without
touching the raw corpus.

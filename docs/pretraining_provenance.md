# ESP-Fi HAR pretraining provenance

Optional ESP-Fi HAR pretraining is an **auxiliary representation-learning
experiment**, not a SRASTA evaluation dataset.

- Source: ESP-Fi HAR, Wen et al. (2026), CC BY 4.0.
- Hardware: ESP32-C3; source tensors are amplitude `[950,52]`.
- Eligible rows: manifest `source_partition=train`,
  `pretraining_train_eligible=yes`, `main_test_eligible=no` only.
- Prohibited rows: all source `test` rows; all WiFall rows; all external rows
  in curated SRASTA train/validation/test/LOSO metrics, INT8 representative
  data, thresholds, or release claims.
- Pretraining model: fixed SRASTA TCN encoder with temporary seven-activity
  head. Its head is discarded; only shape-compatible encoder layers are copied
  into a fresh binary SRASTA model.
- Source timestamps are synthetic at 100 Hz because ESP-Fi MAT files contain
  no packet timestamps. This has no implication for live ESP32-S3 timing.

Artifacts must store the manifest SHA-256, exact source partition, source row
count, actions, hardware caveat, crop policy, preprocessing configuration,
versions, command, and attribution. A better pretraining ablation result does
not establish ESP32-S3 final accuracy or event-level performance.

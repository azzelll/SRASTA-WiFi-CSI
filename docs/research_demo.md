# SRASTA research-demo path

This path is for a presentation of the local WiFi-CSI pipeline. It produces
fall/nonfall **scores only**. It is not a validated detector, a medical
device, an emergency-response system, or an alerting path.

It is intentionally separate from `run_edge_service.py`:

- it creates no `selected_candidate.json` or TFLite deployment artifact;
- it uses ESP-Fi only to initialize the TCN encoder, discarding the source
  seven-activity head before binary SRASTA fine-tuning;
- it fine-tunes on the existing curated `train` partition only;
- it never loads curated test recordings, sends Blynk events, writes SQLite
  event records, or emits `suspected_fall` / `confirmed_fall` states;
- its serial mode still validates the exact SRASTA ESP32-S3 JSONL contract.

## Create the local demo artifact

The ESP-Fi pretrained encoder already present under `artifacts/` is used by
default. Its source provenance is checked before fine-tuning.

```bash
PYTHONPATH=code python code/train_srasta_demo_model.py \
  --manifest data/curated/esp32_s3_fall_v1/manifest.csv \
  --data-root data \
  --out-dir artifacts/srasta_research_demo \
  --epochs 20 --batch-size 16 --seed 42
```

This writes an ignored local directory containing `model.keras`, matching
preprocessing/capture configuration, and `demo_provenance.json`. The latter
records that the artifact is research-demo-only and hash-binds every input.
The command refuses to overwrite an existing artifact directory.

## Present with an H5 replay

```bash
PYTHONPATH=code python code/run_srasta_research_demo.py \
  --demo-provenance artifacts/srasta_research_demo/demo_provenance.json \
  --model artifacts/srasta_research_demo/model.keras \
  --preprocess-config artifacts/srasta_research_demo/preprocess_config.json \
  --capture-profile artifacts/srasta_research_demo/capture_profile.json \
  --replay data/csi-bench/FallDetection/sub_Human/user_U08/act_Fall/env_E22/device_ESP32/session_1000__freq64.h5
```

The command prints newline-delimited JSON scores with `fall_probability`,
`nonfall_probability`, and motion energy. It does not choose an alert
threshold or report a fall event. H5 timestamps are synthetic, so replay is a
pipeline demonstration only. It prints one score for every 25 completed
windows by default; add `--emit-every 1` when a dashboard needs every score.

## Present with the ESP32-S3

After the firmware sends the strict v1 JSONL frames, replace `--replay ...`
with `--serial-port /dev/ttyUSB0 --baud 921600`. The runner rejects invalid
CSI frames but keeps no raw I/Q, logs, database, Blynk integration, or alert
state. Stop it with `Ctrl-C` after the presentation.

Do not pass this artifact to `code/export_srasta_tflite.py` or
`code/run_edge_service.py`; those commands correctly require a separately
validated `selected_candidate.json`.

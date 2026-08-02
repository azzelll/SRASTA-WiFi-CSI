# SRASTA — Backend + AI milestone 50%

Proposal [SRASTA](https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit) adalah satu-satunya source of truth produk. Repository ini mengerjakan urutan kerja **Backend + AI** untuk milestone 50%; urutan ini tidak menghapus requirement proposal lain.

## Jalur demo

```text
curated H5/NPZ replay atau strict ESP32-S3 JSONL V1
  -> validasi + fixed I/Q [imaginary,real] -> amplitude [time,52]
  -> causal timestamp resampling + Hampel + low-pass + room baseline
  -> Random Forest sanity baseline / TCN-Lite full INT8 candidate
  -> normal / suspected_fall / confirmed_fall + SQLite
  -> FastAPI /health, /status, /events
```

Kontrak CSI tetap: LLTF-only HT20, 128 signed int8 byte = 64 pasangan kompleks, `hypot(imaginary, real)`, lalu indeks `6..31` dan `33..58`. Pipeline menolak drift; tidak melakukan resize, padding, atau pergeseran indeks. `manifest.csv` adalah satu-satunya indeks utama dan divalidasi subject/session-disjoint sebelum windowing.

## Setup

```bash
cd /Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_CSI_Bench_Blynk
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r code/requirements-train.txt
```

Untuk Raspberry Pi, install `code/requirements-pi.txt` dan wheel `tflite-runtime` atau `ai-edge-litert` yang kompatibel dengan OS/Python Pi. TensorFlow menjadi fallback untuk environment training, bukan requirement Pi jika salah satu runtime ringan tersedia.

## Seluruh test BE + AI

```bash
PYTHONPATH=code python -m unittest discover -s code/tests -v
```

Tidak ada skip dependency BE/AI yang boleh dihitung lulus.

## Train Random Forest sanity baseline

```bash
PYTHONPATH=code python code/train_srasta_rf_baseline.py \
  --manifest data/curated/esp32_s3_fall_v1/manifest.csv \
  --data-root data \
  --out-dir artifacts/srasta_rf_baseline
```

Output: `model.joblib`, validation-only `metrics.json`, preprocessing/capture config, split report, dan model card. Locked test tidak dibaca. Baseline ini bukan model submission/deployment.

## Train dan export TCN-Lite full INT8

```bash
PYTHONPATH=code python code/train_srasta_tcn_lite.py \
  --manifest data/curated/esp32_s3_fall_v1/manifest.csv \
  --data-root data \
  --out-dir artifacts/srasta_tcn_lite \
  --window-length 250 \
  --epochs 25
```

Output mencakup FP32 checkpoint/model, `model.tflite`, validation metrics, full-INT8 parity, latency engineering, configs, split report, training config, dan model card. Representative quantization hanya memakai curated **train**. Candidate tetap `not_deployment_ready` bila salah satu gate belum terbukti; `.tflite` tidak boleh diklaim deployable hanya karena berhasil diekspor.

## Replay + FastAPI smoke

```bash
PYTHONPATH=code python code/api_smoke.py \
  --model artifacts/srasta_tcn_lite/model.tflite \
  --replay data/csi-bench/FallDetection/sub_Human/user_U08/act_Fall/env_E22/device_ESP32/session_1000__freq64.h5 \
  --db artifacts/edge_tcn.sqlite3 \
  --out artifacts/api_smoke_tcn.json
```

Smoke ini menjalankan replay nyata, route `/health`, `/status`, `/events`, dan probe state machine sintetis untuk membuktikan persistence `suspected_fall` lalu `confirmed_fall`. Probe sintetis bukan klaim bahwa clip H5 memiliki anotasi event/inactivity.

Service lokal:

```bash
PYTHONPATH=code python code/run_edge_service.py \
  --model artifacts/srasta_tcn_lite/model.tflite \
  --replay data/csi-bench/FallDetection/sub_Human/user_U08/act_Fall/env_E22/device_ESP32/session_1000__freq64.h5 \
  --db artifacts/edge_service.sqlite3
```

Query `http://127.0.0.1:8000/health`, `/status`, dan `/events`.

## Bukti milestone mekanis

Command berikut membuat fresh run directory, menjalankan tests, RF train, TCN train/export/parity, API smoke, lalu menulis report. Report tetap ditulis dengan `status: failed` dan exit nonzero jika bukti tidak lengkap.

```bash
PYTHONPATH=code python code/write_milestone_50.py \
  --manifest data/curated/esp32_s3_fall_v1/manifest.csv \
  --data-root data \
  --replay data/csi-bench/FallDetection/sub_Human/user_U08/act_Fall/env_E22/device_ESP32/session_1000__freq64.h5 \
  --out artifacts/milestone_50_be_ai.json \
  --epochs 25
```

## Ketika ESP32-S3 tersedia

Kirim satu JSON object per baris melalui USB serial dengan exact field V1:

```text
version, sequence, local_timestamp_us, sender_mac, rssi, noise_floor,
channel, bandwidth, sig_mode, mcs, rx_state, len,
first_word_invalid, iq_bytes
```

`iq_bytes` harus tepat 128 signed integer, sequence/timestamp meningkat, `bandwidth=HT20`, `sig_mode=HT`, dan `rx_state=0`. Host serial reader milestone hardware berikutnya hanya perlu meneruskan tiap baris ke `EdgeRuntime.ingest_json_line()`; decoder/preprocessing/model tidak perlu dibuat ulang. Frame invalid dikarantina sebagai reason terbatas, tanpa raw I/Q di SQLite.

Blynk selalu disabled/fail-closed pada milestone ini. Tidak ada token dibaca, disimpan, atau dikirim.

## Batasan yang jujur

CSI-Bench H5 tidak memiliki raw packet sequence/timestamp, fall onset/offset, post-fall inactivity, atau continuous non-fall exposure. Karena itu event recall/precision/F1, false alerts/hour, H5 packet-drop rate, dan empirical suspected/confirmed latency tetap `not_available`. Inference latency di mesin training adalah pengukuran engineering, bukan bukti Raspberry Pi/hardware.

ESP32-S3 fisik, firmware/serial host, dashboard visual, kamera, mobile, breathing pipeline, model produk empat output, hardware/enclosure, dan notifikasi eksternal tetap requirement proposal dan gap milestone berikutnya. Data external tidak masuk training/evaluasi utama, raw data tidak diubah, dan locked test tetap tertutup sampai model/threshold benar-benar dibekukan. Lihat [docs/baseline_data_plan.md](docs/baseline_data_plan.md) dan [docs/gemastik_2026_delivery_checklist.md](docs/gemastik_2026_delivery_checklist.md).

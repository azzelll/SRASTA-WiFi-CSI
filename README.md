# SRASTA — CSI, edge AI, dan app caregiver

## Handoff tim — diperbarui 23 Oktober 2026

**Mulai dari [HANDOFF.md](HANDOFF.md)** untuk state, model terpilih, setup clone,
dan urutan pekerjaan. [Panduan pengambilan data](docs/CAPTURE_QUICKSTART.md)
menjelaskan port, instruksi CLI, file hasil, QA dan review.
[Prompt AI penerus](docs/AI_CONTINUATION_PROMPT.md) bisa langsung disalin.
Snapshot terbaru ada di branch **`handoff/2026-10-21`**; branch September dan
`main` adalah checkpoint lama. Model demo terpilih dan indeks split ikut Git;
rekaman CSI mentah dan kredensial tetap lokal.

Dashboard caregiver mendukung akses langsung tanpa login, termasuk Akui dan
Minta bantuan, melalui mode `public` dan perangkat yang diaktifkan admin.
Sudah diterapkan di <https://srasta-caregiver.vercel.app>; browser tanpa sesi
dan penerimaan ringkasan CSI fresh diperiksa 23 Oktober sekitar 00:31 WIB.
[Setup dan pencabutan akses](CLOUD_SETUP.md) ·
[Bukti dan status penerapan](docs/evidence/20261023-public-dashboard.md).

**Pi sudah diperbarui** ke `20261022-demo-v8-camera-burst-r3`. Acceptance ARM,
burst sensor kamera tiga frame dan restart layanan lolos; Blynk/cloud worker
tersambung. Postur kamera masih uncertain. TX/RX tidak dapat dipasang saat
checkpoint, jadi CSI langsung dan trigger kamera dari CSI belum diuji ulang.
[Bukti deployment](docs/evidence/20261022-pi-deployment.md) dan
[perintah start/stop/status/kamera/rollback](docs/PI_OPERATIONS.md).

Pembaruan software 19 Oktober: konsistensi tiga frame kamera, detail kejadian
dan status respons caregiver, serta pengujian pemulihan serial/cloud/kamera.
Web sudah terdeploy; pada checkpoint 19 Oktober paket Pi belum dipasang
(instalasi selanjutnya tercatat pada 22 Oktober di atas):
[hasil dan batas bukti](docs/evidence/20261019-caregiver-hardening.md).

Panel kamera sekarang menggambar skeleton dari 17 titik MoveNet saat kejadian,
dengan label berbaring/tegak/belum jelas. UI dan kontrak cloud sudah terdeploy;
runtime Pi kemudian dipasang pada 22 Oktober; validasi seluruh jalur CSI
ke caregiver tetap belum selesai:
[perubahan dan batas bukti](docs/evidence/20261019-camera-skeleton.md).

Pengembangan offline 19 Oktober: audit label normal, 36 kandidat occupancy,
ablation fall, verifikasi integrasi, dan paket Pi lokal:
[hasil dan batas bukti](docs/evidence/20261019-offline-model-development.md).
Fall tetap v8; target 80%/80% belum tercapai. Kandidat presence publik
75,3%/75,3% dan model tiga kelas masih khusus riset, belum live ESP32.

Training dengan dataset yang sudah ada, status presence/inactivity, hasil
INT8 dan replay: [catatan model offline](docs/evidence/20261001-offline-models.md).

Audit CSI-Bench v12, perbandingan preprocessing/RF/SVM/TCN, dan enam fold
antarorang dengan tiga seed: [hasil target fall 80%/80%](docs/evidence/20261002-fall-development.md).

Training sleep/empty dan presence dengan source-train publik, orang terpisah,
serta inferensi rekaman asli: [hasil occupancy](docs/evidence/20261003-public-occupancy.md).

Fall v8 sudah berjalan pada Raspberry Pi 4B dengan RX UART, CSI asli, Blynk,
dan Supabase: [bukti deployment Pi](docs/evidence/20261005-pi-deployment.md).
Pengukuran inferensi Pi sekitar 3 ms adalah bukti eksekusi software;
validasi akurasi lokal serta model presence/breathing live masih terbuka.

Perbaikan 5 Oktober untuk urutan subcarrier ESP-IDF dan skala grafik:
[diagnosis respons CSI](docs/evidence/20261005-csi-response.md).

Proposal [SRASTA](https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit) adalah konteks produk. Repository berisi firmware TX/RX, pipeline CSI dan edge AI, adapter Blynk, app caregiver, serta konfigurasi cloud. Panduan mulai: [RUNBOOK_LOCAL.md](RUNBOOK_LOCAL.md). Bukti dan pekerjaan yang masih terbuka: [catatan engineering](docs/evidence/20261001-caregiver-engineering.md). Hasil milestone Backend + AI sebelumnya tetap dicatat di bawah.

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
cd SRASTA-WiFi-CSI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r code/requirements-handoff.txt
```

Untuk Raspberry Pi, install `code/requirements-pi.txt` dan wheel `tflite-runtime` atau `ai-edge-litert` yang kompatibel dengan OS/Python Pi. TensorFlow menjadi fallback untuk environment training, bukan requirement Pi jika salah satu runtime ringan tersedia.

## Seluruh test BE + AI

```bash
PYTHONPATH=code python -m unittest discover -s code/tests -v
```

Tidak ada skip dependency BE/AI yang boleh dihitung lulus.

## Pengambilan data lokal dengan panduan CLI

```bash
bash scripts/collect_local_csi.sh
```

CLI memberi instruksi ruangan kosong, aktivitas normal, dan diam/inaktif;
menampilkan countdown; lalu menyimpan CSI asli, label pengamat, prediksi dan
QA secara otomatis di luar Git. Lihat [LOCAL_CAPTURE.md](LOCAL_CAPTURE.md)
untuk durasi, review independen, split per orang, serta batas bukti model.

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

`iq_bytes` harus tepat 128 signed integer, sequence/timestamp meningkat, `bandwidth=HT20`, `sig_mode=HT`, dan `rx_state=0`. `SerialJSONLReader` meneruskan tiap baris ke `EdgeRuntime.ingest_json_line()` dan membuka ulang port yang sama setelah aliran terhenti. Frame invalid dikarantina sebagai reason terbatas, tanpa raw I/Q di SQLite. Lihat [HARDWARE_SETUP.md](HARDWARE_SETUP.md) untuk mapping fisik dan batas bukti capture.

## App caregiver dan CSI nyata

App React/TypeScript PWA tersedia di `web/`; FastAPI melayani build pada
`http://127.0.0.1:8000`. Beranda, Peringatan, Riwayat, dan Perangkat memakai
API/SSE ringkasan realtime, serta ACK dan bantuan yang tersimpan pada edge.

```bash
cd web
npm ci
npm run build
cd ..
bash scripts/run_local.sh simulator
# Setelah mapping RX diverifikasi dan TX berjalan:
bash scripts/run_local.sh live /dev/cu.usbserial-310
```

Simulator memiliki banner jelas dan DB terpisah; bukan bukti deteksi CSI asli.
Mode live menggunakan RX baud1,000,000, channel6 dari TX terkendali. Port TX
USB modem **jangan digunakan untuk firmware RX**. Data lama/serial putus
menampilkan kondisi belum dapat dipastikan, bukan otomatis normal atau standby.

Blynk kini adapter MQTT TLS persistent opsional dari `.env`. App remote
tersedia di <https://srasta-caregiver.vercel.app>, memakai Supabase Auth/RLS
dan Vercel. Migrasi/fungsi, RLS produksi, dan sinkronisasi ringkasan CSI asli
sudah diverifikasi; push HP dan remote ACK masih memerlukan proof. Secret tidak masuk source/browser. Model TCN dua kelas tetap
kandidat engineering, belum model produk empat kelas yang tervalidasi.

Panduan:

- [RUNBOOK_LOCAL.md](RUNBOOK_LOCAL.md): startup, tes, replay, simulasi, recovery.
- [HARDWARE_SETUP.md](HARDWARE_SETUP.md): role TX/RX, build/flash, USB, Pi.
- [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md): instalasi, port RX, layanan otomatis, pemeriksaan Pi.
- [BLYNK_SETUP.md](BLYNK_SETUP.md): V0–V12, events, MQTT, bukti yang diperlukan.
- [CLOUD_SETUP.md](CLOUD_SETUP.md): Supabase/Vercel, auth, outbox, remote proof.
- [MODEL_SETUP.md](MODEL_SETUP.md): paket INT8, kalibrasi trigger, metrics dan batas model.

`/technical`, `/csi`, dan `/csi/stream` menyediakan inspeksi engineering lokal
amplitudo52 di RAM. App caregiver/cloud hanya menerima ringkasan.

### Konsol video demo

Aktifkan endpoint mock secara eksplisit dengan `--demo-mode`, lalu buka konsol:

```bash
./code/start_demo.sh
```

Tekan `Space` tepat saat pemeran jatuh untuk menampilkan `FALL DETECTED`. Tekan `R` untuk kembali ke state model dan `Q` untuk keluar. Sumber CSI dan state simulasi dicatat terpisah; layar menandai trigger dengan `STAGED DEMO | MANUAL TRIGGER` agar tidak disalahartikan sebagai hasil deteksi model.

Artifact live idealnya memiliki `capture_profile.json` dan `preprocess_config.json` yang cocok dengan channel AP aktual. Flag profile override hanya untuk demo TFLite candidate ketika TX engineering memakai channel6; artifact training/evaluation asli tetap channel 1. Override `0.15` berasal dari maksimum gap hardware terukur 0,135 detik; config evaluasi asli tetap `0.05`. Candidate dua kelas yang ada belum deployment-ready dan tidak boleh dipakai sebagai klaim performa lapangan.

## Batasan yang jujur

CSI-Bench H5 tidak memiliki raw packet sequence/timestamp, fall onset/offset, post-fall inactivity, atau continuous non-fall exposure. Karena itu event recall/precision/F1, false alerts/hour, H5 packet-drop rate, dan empirical suspected/confirmed latency tetap `not_available`. Inference latency di mesin training adalah pengukuran engineering, bukan bukti Raspberry Pi/hardware.

ESP32-S3 fisik, firmware/serial host, dashboard visual, kamera, mobile, breathing pipeline, model produk empat output, hardware/enclosure, dan notifikasi eksternal tetap requirement proposal dan gap milestone berikutnya. Data external tidak masuk training/evaluasi utama, raw data tidak diubah, dan locked test tetap tertutup sampai model/threshold benar-benar dibekukan. Lihat [docs/baseline_data_plan.md](docs/baseline_data_plan.md) dan [docs/gemastik_2026_delivery_checklist.md](docs/gemastik_2026_delivery_checklist.md).

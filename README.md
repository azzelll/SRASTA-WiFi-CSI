# SRASTA CSI-Bench Training + Raspberry Pi Blynk Inference

Starter kit ini dibuat untuk alur SRASTA:
1. Training model TCN-Lite dari dataset CSI-Bench / data CSI prototipe.
2. Konversi model ke TensorFlow Lite INT8.
3. Inference real-time di Raspberry Pi 4B dari serial ESP32-S3 receiver.
4. Pengiriman status langsung ke Blynk IoT via HTTPS API.

## Struktur Blynk Datastream yang disarankan

Buat Datastream Virtual Pin berikut di Blynk Console:

| Pin | Tipe | Isi |
|---|---|---|
| V0 | String | state akhir: standby/normal/inactive/anomaly/critical |
| V1 | String | prediksi kelas model |
| V2 | Double | confidence model |
| V3 | Double | estimasi napas per menit |
| V4 | Integer | alert level: 0 normal, 1 inactive, 2 anomaly, 3 critical |
| V5 | Double | fall probability |
| V6 | Double | latency inference ms |
| V7 | String | pesan ringkas |
| Event code | custom event | `srasta_alert` untuk notifikasi push/timeline |

## Install training di laptop/PC

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-train.txt
```

Contoh training:

```bash
python train_tcn_lite_csi.py \
  --data-root /path/to/CSI-Bench \
  --task FallDetection \
  --out runs/srasta_fall \
  --win-len 500 \
  --feature-size 232 \
  --epochs 50
```

Output penting:
- `runs/srasta_fall/model.keras`
- `runs/srasta_fall/model_int8.tflite`
- `runs/srasta_fall/label_map.json`
- `runs/srasta_fall/training_summary.json`

## Install inference di Raspberry Pi

```bash
sudo apt update
sudo apt install -y python3-pip
pip3 install -r requirements-pi.txt
cp config_blynk.env.example config_blynk.env
nano config_blynk.env
```

Jalankan:

```bash
set -a
source config_blynk.env
set +a

python3 infer_blynk.py \
  --model runs/srasta_fall/model_int8.tflite \
  --labels runs/srasta_fall/label_map.json \
  --serial-port /dev/ttyUSB0 \
  --baud 921600 \
  --win-len 500 \
  --feature-size 232 \
  --sample-rate 50
```

Untuk tes tanpa serial, pakai mode simulasi:

```bash
python3 infer_blynk.py --model runs/srasta_fall/model_int8.tflite --labels runs/srasta_fall/label_map.json --demo
```

## Catatan penting

- Loader HDF5 dibuat robust karena key internal H5 CSI-Bench / firmware CSI bisa berbeda.
- Untuk GEMASTIK, training awal dari CSI-Bench sebaiknya tetap dilanjutkan dengan kalibrasi data prototipe ESP32-S3 di ruangan target.
- Untuk notifikasi Blynk, buat event code `srasta_alert` di Blynk Template > Events.
- Token Blynk jangan di-hardcode ke script. Simpan di environment variable `BLYNK_TOKEN`.
# SRASTA-WiFi-CSI

# Paket demo Pi yang disiapkan secara lokal

Arsip terbaru: `artifacts/pi/20261019-demo-camera-burst-r2.tar.gz`.
Paket ini disiapkan dan diperiksa pada Mac. Paket belum dipasang atau diuji
ulang pada Raspberry Pi dalam sesi 19 Oktober.

Arsip lama `20261019-offline-demo-camera.tar.gz` dan
`20261019-demo-skeleton-camera.tar.gz` tetap disimpan. Paket terbaru menambahkan
konsistensi tiga frame, detail kejadian dan pemulihan kegagalan software.

## Isi

- Runtime CSI, dashboard hasil build terbaru, fall v8 dan config yang dibekukan.
- MoveNet Lightning INT8 beserta model card untuk kamera event-only.
- Ringkasan pose COCO17, migrasi SQLite otomatis dan UI skeleton dari titik
  kamera. Foto tetap tidak diunggah; posisi berbaring tidak memastikan tidur.
- Burst tiga frame per kejadian; minimal dua sepakat tanpa arah berlawanan.
- Detail kejadian dengan hasil kamera historis dan receipt respons caregiver.
- Retry hasil kamera tanpa capture ulang serta validasi batch/outbox cloud.
- Model publik sleep/empty dan presence lama untuk inferensi rekaman.
- Tiga kandidat riset baru, metrics dan protokol; **tidak diaktifkan live**.
- Manifest SHA-256 setiap file dan fixture sintetis parity software.
- Script install, acceptance, simulator dan service Pi.

Tidak ada credentials, `.env`, database, rekaman CSI, atau dataset training
dalam arsip. Dependensi belum dibundel sebagai wheelhouse; instalasi memerlukan
internet. Installer memeriksa ARM64 dan Python 3.13 sesuai target Pi saat ini.

## Membuat paket dari repository

```bash
cd web
npm run build
cd ..
.venv/bin/python scripts/pack_pi_demo.py \
  --output artifacts/pi/YOUR_NEW_PACKAGE.tar.gz \
  --camera-model artifacts/models/movenet-lightning/model.tflite \
  --research-run artifacts/research/20261019-occupancy-calibrated
```

Packer menolak menimpa arsip atau memasukkan run yang dinyatakan invalid.

## Instalasi berikutnya pada Pi

Transfer arsip ke folder release **baru**, ekstrak, lalu dari folder itu:

```bash
bash scripts/install_pi_demo.sh
bash scripts/run_pi_demo.sh simulator
```

Simulator berlabel demo dan tidak membuktikan CSI asli. Installer menjalankan
`pi_acceptance.py`: pemeriksaan hash, loading, route dashboard, inferensi
sintetis fall dan MoveNet (tanpa membuka sensor). Model riset baru hanya diuji bisa dimuat/dieksekusi; ini bukan
pengujian akurasi, parity lintas arsitektur model sklearn, atau quality kamera.

Untuk mengulang acceptance, gunakan nama output baru:

```bash
.venv/bin/python code/pi_acceptance.py \
  --output artifacts/pi/software_acceptance_second.json
```

Live memerlukan identitas RX yang diperiksa kembali, config jaringan/cloud
lokal, dan kamera yang terdeteksi. Panduan lengkap tetap di
`RASPBERRY_PI_SETUP.md` pada repository utama. Paket ini belum mengubah service
yang sudah terpasang di Pi. Hasil model dan batas bukti dijelaskan pada
[laporan pengembangan](evidence/20261019-offline-model-development.md).
Detail pembaruan panel ada di
[bukti skeleton kamera](evidence/20261019-camera-skeleton.md).
Pembaruan tiga frame, detail kejadian dan pemulihan software ada di
[laporan ketahanan caregiver](evidence/20261019-caregiver-hardening.md).

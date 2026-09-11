# Runbook lokal SRASTA

Semua perintah PowerShell dijalankan dari root repository `SRASTA-WiFi-CSI`, bukan folder induknya. Python 3.12 digunakan pada verifikasi ini.

## Instalasi

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r code/requirements-train.txt -r code/requirements-dev.txt
.venv/Scripts/python -m playwright install chromium
```

`httpx2` adalah dependensi TestClient Starlette yang digunakan saat ini; `httpx` juga dipakai oleh adapter Blynk. Pi cukup memakai `requirements-pi.txt` ditambah runtime LiteRT/TFLite yang sesuai OS/arsitektur. TensorFlow adalah fallback pada laptop pelatihan. Kamera/GPIO opsional memakai `requirements-hardware.txt`, model MoveNet lokal, dan perangkat yang sesuai. Versi paket terpasang tercatat pada `artifacts/environment-freeze.txt`.

## Simulator dan lima status

```powershell
.venv/Scripts/python code/run_edge_service.py --demo --db artifacts/demo.sqlite3 --port 8000
```

Buka http://127.0.0.1:8000. Pilih `standby`, `normal`, `inactive`, `anomaly`, dan `critical` di **Lab pengembangan**. Banner selalu menyatakan simulator. Gerakan demo adalah skenario; estimasi napas dan keyakinan model tidak direkayasa. Pada critical, **Saya sudah menangani** mengakui event dan menyenyapkan permintaan alarm; status tetap critical sampai bukti pemulihan atau skenario lab baru. Event lama tidak dapat menyenyapkan alarm event critical yang lebih baru. Critical/ack tersimpan lintas restart.

**Panggil Bantuan Darurat** membuka dialog kosong. Masukkan nomor yang sesuai dan tekan **Mulai panggilan** sendiri. Pengujian otomatis berhenti pada pemeriksaan tautan, tidak memanggil nomor. Nomor tidak disimpan.

API lokal: `GET /health`, `/status`, `/events`, `/config`; `WS /ws`; `POST /events/{id}/acknowledge`. `/health.ok` berarti proses layanan tersedia; kondisi sensor sebenarnya berada dalam `monitoring.fresh` dan `source_status`. POST wajib token `X-SRASTA-Token` dari `/config`. `/dev/state` hanya tersedia saat `--demo`; source replay/serial menolak mutasi simulator. Default inaktivitas 120 detik, konfirmasi 10 detik; untuk eksperimen gunakan `--inactivity-seconds` dan `--confirmation-seconds` tanpa mengubah kontrak firmware.

## Dataset dan training

Dataset CSI-Bench: <https://www.kaggle.com/datasets/guozhenjennzhu/csi-bench>, penggunaan riset lokal CC BY-NC-ND 4.0. Pengunduh memilih ESP32 train/validation dari metadata publik, tidak mengedit sumber dan tidak mengunduh locked test.

```powershell
.venv/Scripts/python code/tools/fetch_csi_bench.py
```

Jalankan sekali pada checkout tanpa manifest; script menolak menimpa manifest yang telah dibekukan. Jika unduhan terputus sebelum manifest dibuat, jalankan lagi: sumber yang sudah ada tidak ditimpa. Rekaman parsial/rusak harus diperiksa manual; jangan mengubah raw agar bentuknya cocok. Metadata dan SHA sumber dicatat pada `data/curated/esp32_s3_fall_v1/dataset_info.json`.

Split: train U08/U09/U11/U12/U17/U18 (288), validation U19 (77), locked test U21 (80, indeks saja), excluded U22 (49). Metadata September 2026 memiliki 494 entri ESP32, termasuk 22 tambahan nonfall U22 dibanding audit lama 472. Tidak ada subject/session overlap. ESP-Fi HAR source-train juga sudah dipakai untuk percobaan transfer terpisah; hasil dan atribusi lengkap ada di `MODEL_EVALUATION.md`. Source-test tidak diunduh.

```powershell
.venv/Scripts/python code/train_srasta_rf_baseline.py --manifest data/curated/esp32_s3_fall_v1/manifest.csv --data-root data --out-dir artifacts/rf-new --trees 500
.venv/Scripts/python code/train_srasta_tcn_lite.py --manifest data/curated/esp32_s3_fall_v1/manifest.csv --data-root data --out-dir artifacts/tcn-new --epochs 25
```

Output directory harus baru/kosong. RF adalah baseline internal. TCN full INT8 memakai representative train saja dan mengevaluasi validation; jangan membuka test untuk mencoba-coba threshold. `metrics.json` membedakan proxy klasifikasi satu window/rekaman dari event-level recall/precision/F1/FAR yang belum tersedia. Paket model wajib memuat capture/profile dan preprocessing yang sama. Preprocessing v2 memakai histori pengukuran pada Hampel agar perubahan menetap tidak ditekan selamanya; model v1 harus dilatih ulang.

## Replay

```powershell
$sample = Import-Csv data/curated/esp32_s3_fall_v1/manifest.csv | Where-Object split -eq train | Select-Object -First 1
$replayPath = Join-Path data $sample.source_path
.venv/Scripts/python code/run_edge_service.py --replay $replayPath --model artifacts/tcn-v2-20260911/model.tflite --db artifacts/replay.sqlite3
```

Tanpa `--model`, jalur aturan gerakan eksperimental tetap dapat diuji. H5 memakai waktu nominal 100 Hz karena corpus tidak menyertakan timestamp paket terukur. NPZ dapat membawa `amplitude [T,52]` dan `timestamps_s`; JSONL melewati validator frame penuh. Selesainya replay ditampilkan sebagai data rekaman terakhir, tidak dianggap sensor live. Controller lab dinonaktifkan. Tidak ada notifikasi eksternal dari replay.

## Receiver hotspot

```powershell
.venv/Scripts/python code/run_edge_service.py --serial-port COM9 --hotspot-config artifacts/hotspot.local.json --db artifacts/live.sqlite3
```

Ikuti `HARDWARE_SETUP.md` untuk header privat, flash, dan verifikasi sebelum menjalankannya. CLI hanya membaca sender/channel dari konfigurasi untuk runtime; password tidak masuk proses argumen, API, atau SQLite. Profil channel hotspot tidak boleh dilabel ulang sebagai profil model channel lain. Karena itu jalur hotspot saat ini memakai aturan eksperimental sampai ada kandidat dengan profil serta validasi lokal yang sesuai.

## Kalibrasi posisi hotspot

Pergantian hotspot atau posisi receiver membatalkan asumsi ambang gerakan sebelumnya. Bandingkan sesi berlabel gerakan biasa dengan sesi tenang pada posisi tetap. Label kondisi harus dikonfirmasi pengguna; fluktuasi sinyal saja bukan ground truth. Rekaman kalibrasi menyimpan ringkasan energi, bukan raw CSI. Ambang awal `--motion-threshold 0.02` belum dikalibrasi ruangan. `--sudden-motion-threshold 0.08` terpisah: menurunkan ambang keberadaan tidak otomatis menurunkan ambang indikasi gerakan mendadak. Keduanya parameter eksperimen, bukan bukti deteksi jatuh.

Pada hotspot baru, probe 30 detik menemukan 2.989 paket, median interval 9,70 ms, maksimum 88,81 ms, dan 10 jeda di atas 50 ms. Untuk aturan gerakan sesi ini, `--max-packet-gap-ms 100` mengizinkan hold kausal yang dibatasi 100 ms; jeda lebih lama tetap mereset jendela. Ini parameter eksperimen untuk jitter hotspot, bukan bukti akurasi. Default model tetap memakai konfigurasi terserialisasi; memberikan override bersama `--model` ditolak.

Setelah pengguna menyatakan kondisi siap, rekam dua sesi pada posisi yang sama:

```powershell
.venv/Scripts/python code/tools/calibrate_motion.py capture --label quiet --setup-id posisi-tetap-1 --out artifacts/calibration/quiet-new.json
.venv/Scripts/python code/tools/calibrate_motion.py capture --label movement --setup-id posisi-tetap-1 --out artifacts/calibration/movement-new.json
.venv/Scripts/python code/tools/calibrate_motion.py compare --quiet artifacts/calibration/quiet-new.json --movement artifacts/calibration/movement-new.json --out artifacts/calibration/result-new.json
```

Jangan jalankan kedua capture bersamaan atau tanpa kondisi nyata sesuai label. Berjalan biasa saja; tidak perlu jatuh. Setiap capture butuh minimal 60 observasi dan 80% polling siap analisis. Ambang dipilih dari separasi kuantil paruh pertama dan diuji pada paruh kedua kronologis. Ketidakcocokan posisi/preprocessing, distribusi tumpang tindih, atau holdout buruk menolak kalibrasi. Sampel waktu yang berdekatan bukan pengamatan independen; hasil tetap ambang gerakan provisional, bukan metrik klasifikasi jatuh. Gunakan `--motion-threshold` hanya setelah hasil diterima dan simpan laporan, tanpa menghapus sesi gagal.

API membedakan `health.rejected_frames` (frame tidak sah), `window_rejections` (jendela temporal belum cukup), dan `dropped_frames` (antrean host penuh). `inference_ready` tetap false setelah gap/reconnect atau kegagalan coverage sampai jendela baru berhasil diproses. Status riwayat realtime diambil bersama secara konsisten dan UI mengabaikan respons lama dalam sesi yang sama.

## Pengujian yang dapat diulang

```powershell
.venv/Scripts/python code/tools/verify_local.py
$env:PLATFORMIO_CORE_DIR = Join-Path $env:LOCALAPPDATA 'srasta-pio'
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
.venv/Scripts/python code/tools/verify_local.py --firmware
```

Hasil: `artifacts/verification/report.json`, log lengkap, screenshot dan report browser. Untuk test unit saja:

```powershell
$env:PYTHONPATH = 'code'
.venv/Scripts/python -m unittest discover -s code/tests -v
```

Browser menguji 1440×1100 dan 390×844, kelima status, ack, nomor darurat, overflow, teks 200%, offline shell, ketiadaan cache sensitif dan permintaan eksternal. Tidak menguji layanan telepon, browser push background, maupun instalasi PWA pada ponsel fisik. Notifikasi realtime dalam halaman tersedia selama dashboard terhubung. WebMCP read-only dideteksi opsional; browser tanpa API tetap bekerja.

## Recovery

- Port sedang dipakai: hentikan proses monitor/layanan yang Anda buka sebelum flash/probe; hanya satu pembaca serial.
- USB terputus: source reconnect otomatis; port tanpa byte selama 5 detik dibuka ulang dengan backoff maksimal 8 detik dan error `serial_no_data`; validator/ring/timer konfirmasi dikosongkan. Alert critical tersimpan tetap terlihat, namun banner menyatakan data tidak fresh.
- Banyak frame ditolak: periksa sender/channel/HT20/128 dan kualitas. Jangan memperbaiki payload dengan padding atau mengganti hash model.
- Restart setelah critical: gunakan database yang sama agar ack/latch pulih. Gunakan database baru untuk sesi simulator yang ingin dimulai bersih; jangan hapus riwayat live sebagai cara menyenyapkan alarm.
- Mode offline: shell dapat dibuka dari cache; status/napas tidak difabrikasi tanpa backend. Dashboard tidak boleh dibuka langsung sebagai file HTML.
- Build Windows: gunakan core path pendek di folder pengguna, bukan repository OneDrive yang panjang atau `C:\Windows\Temp`; lihat catatan masalah aktual dalam hardware runbook.
- USB terdeteksi tetapi tetap 0 byte setelah beberapa reconnect dan reset esptool: cabut USB sekitar 5 detik, sambungkan kembali, pastikan port sama dan tunggu frame/analisis fresh sebelum mengulang kalibrasi. Data gap tidak digunakan sebagai kondisi tenang.
- Berhenti: Ctrl+C pada proses yang Anda jalankan. Harness menghentikan server sementaranya sendiri.

## Batas yang masih berlaku

Aturan motion, perubahan estimasi napas dari acuan sesi, dan pose horizontal masih eksperimen. Napas butuh minimal 30 detik pengukuran kontinu/tenang, periodisitas/coherence memadai; enam estimasi stabil membentuk acuan, tiga estimasi dengan perubahan >=40% dan >=4 bpm memberi indikasi pola berubah. Angka itu parameter engineering, bukan ambang diagnosis. Data hilang/motion tidak dianggap apnea. Model kamera harus MoveNet single-pose input `[1,192,192,3]`, output `[1,1,17,3]`. Tiga pose sesaat diproses lokal tanpa menyimpan gambar. Pengguna menyatakan Pi/kamera/buzzer belum tersedia; pengujian adapter menggunakan fixture, bukan bukti hardware tersebut.

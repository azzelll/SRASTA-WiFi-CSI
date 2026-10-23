# Menjalankan SRASTA Caregiver

Target edge akhir: **Raspberry Pi 4B**. Mac saat ini dipakai untuk pengembangan.
App yang sama menerima ringkasan dari FastAPI lokal atau Supabase untuk akses
jarak jauh. Tidak ada data CSI mentah pada frontend/cloud.

## Persiapan

```bash
python3 -m venv .venv
.venv/bin/pip install -r code/requirements-handoff.txt
# Untuk Pi ARM64 gunakan installer dan requirements-pi-demo.txt; lihat HANDOFF.md.
cd web
npm ci
npm run build
cd ..
```

Model `.tflite` harus disertai `training_config.json`, `preprocess_config.json`,
dan `capture_profile.json`. Snapshot model demo terpilih disertakan dalam Git
pada branch handoff 21 Oktober. Kandidat tersedia di
`artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/model.tflite`.
Classifier INT8 dan trigger motion terkalibrasi tersedia untuk integrasi;
target akurasi belum tercapai. Lihat [MODEL_SETUP.md](MODEL_SETUP.md).
Untuk lokasi lain, set `SRASTA_MODEL=/absolute/path/model.tflite`.

## Buka app dan uji lima status

```bash
bash scripts/run_local.sh simulator
```

Buka <http://127.0.0.1:8000>. Banner **MODE SIMULASI** wajib terlihat. Buka
“Pengendali pengujian · simulasi” untuk menguji `standby`, `normal`, `inactive`,
`anomaly`, `critical`. Tidak ada CSI palsu yang dibuat untuk mengisi grafik.
Napas, skor model, dan grafik tetap tidak tersedia jika tidak ada bukti data.
Simulator memakai DB terpisah dan tidak memuat `.env` secara default.
Tambahkan `--alarm disabled` bila sedang memeriksa layout tanpa suara.

Pada Peringatan, ACK menyimpan waktu respons untuk **kejadian yang dipilih**;
kondisi kritis tidak terhapus. Permintaan bantuan disimpan sekali per command
UUID. Panggilan telepon memerlukan nomor kontak dan klik caregiver; sistem
tidak menelepon otomatis. Label orang/ruangan/kontak hanya disimpan di browser.

## CSI asli

Sambungkan board berlabel TX/RX. Cocokkan kembali port mengikuti
[HARDWARE_SETUP.md](HARDWARE_SETUP.md); nomor port dapat berubah.

```bash
bash scripts/run_local.sh live /dev/cu.usbserial-310
```

Port tersebut adalah mapping RX yang pernah dikonfirmasi, **bukan jaminan**
mapping setelah reconnect. Jalur ini memakai channel 6 dan baud 1,000,000,
sesuai firmware RX saat ini. Jangan menjalankan dua pembaca pada port RX.
`--demo-mode` tidak dipakai pada mode live. `.env` mengaktifkan Blynk/cloud
hanya jika kredensial terkait tersedia. Kandidat TCN dua kelas masih belum
membuktikan deteksi keberadaan/HAR empat kelas maupun akurasi ruangan.

App menampilkan sumber **CSI langsung** hanya ketika paket valid baru diterima.
Status kondisi baru dianggap terkini setelah inferensi selesai. Hilang koneksi
menampilkan pemantauan offline dan status terakhir. `standby` bukan sinonim RX
putus. Reader menggunakan worker inferensi terpisah setiap 0,2 detik, sehingga
pembacaan USB tidak menunggu preprocessing. Shutdown membatasi drain SSE
5 detik dan menutup reader. Pada macOS, baud custom dinormalisasi saat reopen.
Reader mencoba membuka ulang **port yang sama** setelah 5 detik tanpa
frame valid; tidak berpindah otomatis ke board lain. Jika port berubah,
hentikan service lalu jalankan dengan port RX yang telah diverifikasi.

## Replay dan pengembangan frontend

Untuk mengumpulkan rekaman baru dengan instruksi kondisi dan penyimpanan
otomatis, jalankan `bash scripts/collect_local_csi.sh`. Panduan lengkap:
[LOCAL_CAPTURE.md](LOCAL_CAPTURE.md). Layanan live dijeda saat recorder memakai
RX dan dijalankan kembali otomatis; data penelitian tidak masuk dashboard.

```bash
bash scripts/run_local.sh replay /absolute/path/recording.h5
cd web
npm run dev
```

Vite pada <http://127.0.0.1:5173> meneruskan `/api` dan `/demo` ke edge8000.
Replay ditandai eksplisit dan tidak dilabeli sebagai pemantauan langsung.
Rekaman tetap lokal; tidak menyalin atau mengubah file di `data/`.

## Verifikasi

```bash
PYTHONPATH=code .venv/bin/python -m unittest discover -s code/tests -v
cd web
npm test
npm run test:cloud
npm run build
```

`test:cloud` menjalankan migrasi dan RLS pada PostgreSQL PGlite dengan role
Supabase yang ditiru: anon ditolak; akun lain tidak bisa membaca perangkat;
anggota dapat memberi perintah; browser tidak bisa memalsukan receipt edge;
pencabutan membership menghentikan akses. Ini belum membuktikan Realtime,
fungsi Deno, pengiriman push, atau koneksi Supabase produksi.

API ringkasan: `/api/caregiver`, SSE `/api/caregiver/stream`, perintah
`POST /api/commands`. `/technical` dan `/csi` hanya untuk inspeksi engineering
lokal. Backend dibatasi ke loopback; jangan publikasikan port8000. Dari laptop
ke Raspberry Pi lokal gunakan `ssh -L 8000:127.0.0.1:8000 user@raspberrypi.local`.
Untuk luar rumah gunakan cloud yang diautentikasi.

## Alarm, kamera, dan Raspberry Pi

Default `--alarm audio` memakai `afplay` pada Mac atau `aplay` pada Linux.
`--alarm gpio --buzzer-pin 18` memakai `gpiozero.Buzzer` pada **BCM18** dan
rangkaian driver sesuai panduan hardware. Instal `gpiozero` hanya pada Pi
yang telah disambungkan sesuai rangkaian. Permintaan alarm, ketersediaan output,
dan status output dibedakan pada API; flag kritis saja bukan bukti suara.

Kamera Pi bersifat opt-in:
`--camera-model /absolute/path/movenet-lightning.tflite` dengan `picamera2`
dan runtime TFLite yang cocok. Model MoveNet tidak masuk Git. Adapter
membuka kamera hanya untuk anomaly nonsimulasi, menghasilkan 17 keypoint
dalam RAM, menutup kamera, dan membagikan ringkasan postur saja. Kegagalan/
kualitas buruk dilaporkan, tanpa menghapus alert. Wiring/kamera/model dan
latensi Pi belum diuji pada hardware saat Pi belum tersambung.

Estimator SVD-FFT membutuhkan 30 detik sinyal kontinu saat tubuh diam,
menolak gap/gerakan besar/periodisitas buruk, dan menahan angka napas ketika
kualitas kurang. Tes sinus sintetis membuktikan jalur numerik saja; MAE
pernapasan manusia belum diukur. Apnea/breathing irregularity masih memerlukan
validasi dan kalibrasi lokal sebelum dipakai untuk keputusan keadaan.

## Pemulihan

- Hentikan dengan Ctrl+C sebelum mengganti port/flash.
- RX hilang: cek kabel/data USB, periksa port, restart service dengan port
  terverifikasi. Counter valid/gap/karantina/reconnect tersedia di Perangkat.
- Cloud putus: inferensi, SQLite, dan alarm tetap lokal; outbox SQLite mencoba
  ulang dengan backoff hingga60 detik. App jarak jauh menampilkan data lama.
- Command remote berstatus pending belum berarti bantuan/ACK sudah diterapkan.
  Receipt edge menjadi `applied`, `expired`, atau `rejected`.
- PWA offline menampilkan shell yang tersimpan dan status tidak tersedia;
  service worker tidak menyimpan snapshot/API/data CSI. Browser perlu pernah
  memuat asset app secara online terlebih dahulu.
- Endpoint simulasi hanya terdaftar bila service dijalankan dengan demo mode.

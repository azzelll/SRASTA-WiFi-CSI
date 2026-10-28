# Handoff SRASTA — diperbarui 23 Oktober 2026

Audit 28 Oktober: [jumlah rekaman/window dan pembagian data model fall](docs/DATA_MODEL_AUDIT.md)
memisahkan sumber CSI-Bench, eksperimen tim, cross-validation development, dan
held-out lokal yang belum tersedia. [Verifikasi sinkronisasi main](docs/evidence/20261028-main-sync.md).

Pembaruan data/model lokal 26 Oktober: 25 sesi sudah direview dan accepted
(12 fall, 5 presence, 8 empty). Persetujuan tim untuk penggunaan 13 sesi lama
dicatat terpisah dengan hash; config dan raw asli tidak diedit. Loader membaca
koreksi kelompok A/B/C sebelum pembentukan window. Fine-tuning head TCN
menghasilkan recall/specificity window OOF 36,1%/71,6% versus v8 0%/100%
pada window yang sama; kandidat tidak dipromosikan karena specificity turun.
Ini eksperimen train/development, bukan validasi baru. Orang D baru siap
direkam; E belum tersedia untuk test. Lihat
[prosedur pengembangan lokal](docs/LOCAL_CAPTURE_DEVELOPMENT.md).

Dokumen masuk untuk anggota tim dan AI penerus. Ini snapshot software dan
bukti yang tersedia, bukan pernyataan seluruh produk sudah tervalidasi.
Pembaruan Pi terbaru: [operasi Pi](docs/PI_OPERATIONS.md) dan
[bukti 22 Oktober](docs/evidence/20261022-pi-deployment.md). Cabang utama kini
`main`; handoff dan panel Pi digabung melalui PR #2 pada 23 Oktober.
[Bukti integrasi software](docs/evidence/20261023-main-integration.md).

Prioritas terbaru pemilik: **fall → dataset lokal → presence → validasi →
uji pengalaman**; ketahanan dinyatakan sudah pass oleh pemilik. Engineering
offline fall 23 Oktober selesai menjalankan diagnosis dan 36 fitting grouped;
kandidat Hampel raw ditolak. V8 tetap demo. Recorder ADL/motion/four-boundary
fall, QA dan evaluator event telah disiapkan, tetapi belum diuji capture fisik
di checkpoint ini. Mulai dari [hasil dan handoff data](docs/FALL_ENGINEERING_HANDOFF.md)
dan [bukti software](docs/evidence/20261023-fall-engineering.md).

Pembaruan web 23 Oktober: mode `public` langsung membuka dashboard tanpa login,
termasuk Akui/Minta bantuan. Perangkat dipilih admin melalui RPC terbatas;
token Pi dan tabel lain tetap privat. Setup/rollback: `CLOUD_SETUP.md`.
Status penerapan dan batas bukti: `docs/evidence/20261023-public-dashboard.md`.
Supabase dan Vercel sudah diterapkan; browser produksi tanpa sesi membuka
Beranda dan menerima ringkasan CSI fresh pada 23 Oktober sekitar 00:31 WIB.
Ini tidak membuktikan akurasi deteksi atau tindakan/push pada HP/Pi fisik.

Tambahan 23 Oktober: [panel OLED/LED/piezo lokal](docs/PI_DEVICE_PANEL.md)
terpasang sebagai service terpisah dengan ambang skor >=85% merah,
75–<85% kuning, <75% hijau (diperbarui atas permintaan pemilik).
CSI live terhubung pada pemeriksaan pemasangan awal;
lihat [bukti panel](docs/evidence/20261023-device-panel.md).
Ini bukan hasil validasi akurasi atau perubahan state machine/model.

## 1. Ambil versi yang benar

```bash
git clone --branch main https://github.com/azzelll/SRASTA-WiFi-CSI.git
cd SRASTA-WiFi-CSI
git branch --show-current
git log -1 --oneline
```

`main` memuat handoff `394e6a3`, panel Pi `d24b3e4` dan merge `83bb1b7`.
`handoff/2026-10-21` menyimpan checkpoint sebelum panel digabung.
`agent/rebuild-be-ai-milestone` memakai implementasi Windows/hotspot September
yang berbeda. Integrasi ke main tidak menimpa cabang September.
Jangan menggabungkan runtime atau firmware dari kedua checkpoint tanpa audit.

Urutan baca: `AGENTS.md` → `AI_CONTEXT.md` → dokumen ini →
[`docs/CAPTURE_QUICKSTART.md`](docs/CAPTURE_QUICKSTART.md). `AGENT.md` adalah
panduan tambahan; proposal Google Docs di `AGENTS.md` tetap konteks produk.
Schema dan tes repo menentukan kebenaran implementasi. Jika proposal tidak
bisa diakses, catat kendala akses; jangan mengarang isinya atau memangkas fitur.

## 2. State produk dan batas buktinya

| Bagian | Sudah ada | Yang belum selesai / belum terbukti |
| --- | --- | --- |
| Firmware TX/RX | ESP32-S3 TX SoftAP + UDP; RX LLTF/HT20 JSONL UART; pernah dipakai pada Pi | Koneksi, port dan mutu paket saat ini harus diperiksa ulang |
| CSI runtime | Decoder ketat, 52 amplitudo, preprocessing bersama, TFLite, antrean, reconnect, SQLite, API | Stabilitas panjang dan mutu deteksi di ruangan baru |
| Fall | TCN-Lite INT8 v8 + motion gate; suspected/confirmed dipisahkan oleh inactivity | Recall/specificity lokal, event recall, latency kejadian dan FAR belum tervalidasi |
| Presence | Kandidat model publik dan trainer presence lokal tersedia | Kandidat publik belum valid untuk stream 52 kanal RX; belum ada model presence lokal accepted |
| Breathing condition | Kandidat riset `empty/sleep/normal` dan `empty/sleep` | `normal` tiga kelas masih proxy HAR; tidur alami vs terjaga lokal belum dilatih/divalidasi |
| Motion/inactivity | Energi gerak + timer state tersedia | Kalibrasi lokal dan evaluasi anotasi; bukan classifier medis tervalidasi |
| Kamera | Burst/skeleton dipasang di Pi 22 Oktober; uji sensor asli tiga frame dan pose 17 titik lolos | Postur uji masih uncertain; akurasi posture dan trigger CSI asli belum diukur |
| Panel lokal | OLED, LED dan piezo sebagai service terpisah; self-test dan hasil pemasangan dicatat 23 Oktober | Skor panel bukan konfirmasi jatuh; reboot fisik dan stabilitas panjang belum diuji |
| Caregiver | React/TypeScript UI sesuai arah Figma, event history, skeleton, ACK/bantuan, offline/stale state | Penerimaan caregiver nyata, push HP dan jalur kamera Pi terbaru → cloud → HP |
| Cloud/Blynk | Adapter, SQL/RLS, edge-sync, idempotensi/command receipt dan tes tersedia | Kredensial harus diberikan privat; software test bukan bukti semua pengiriman nyata berhasil |
| Recorder | Satu CLI: kosong → normal → diam; simpan raw + anotasi + prediksi + QA | Belum ada CLI terpandu tidur alami, jatuh, atau sesi ADL panjang dengan anotasi lengkap |

Lima fitur produk tetap: fall, breathing condition diskret
**sleep/normal/empty**, presence, motion, inactivity. `inactive` bukan `sleep`.
Posture horizontal bukan bukti tidur atau jatuh. Skeleton adalah bukti kejadian
bertimestamp, bukan animasi posisi orang saat ini. Kamera tidak terus merekam.
ACK tidak menghapus kondisi kritis dan sistem tidak menelepon otomatis.

### Model demo yang dipilih

- Fall: `artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/`.
  TFLite INT8 `[1,500,52]`, threshold 0,45, motion gate terserialisasi.
  SHA-256 model: `ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.
- Validation U19: **recall 62,5%, specificity 64,9%**, proxy per rekaman pada
  validation pengembangan yang telah dipakai berulang. Bukan event recall lokal.
  Target bersama **minimal 80%/80%** belum tercapai; target awal 88%/80% juga belum.
- Jangan memakai `code/runs/srasta_fall/model_int8.tflite`: run lama invalid,
  satu kelas dan salah bentuk input. Jangan memilih model hanya dari parity.
- Kandidat publik 19 Oktober presence sekitar **75,3%/75,3%**, recall sleep
  sekitar **50,6%**; validation digunakan untuk memilih kandidat/threshold.
  Ini bukan hasil test independen dan bukan bukti live ESP32.
- Model occupancy publik memakai domain/layout sumber yang berbeda. Loader
  riset terpisah; jangan resize/pad sumber menjadi 52 fitur atau mengaktifkannya
  sebagai presence/breathing live tanpa kontrak dan validasi yang benar.
- U21 sudah pernah diperiksa pada pekerjaan lama. **Jangan dibuka ulang untuk
  tuning**. Bekukan protokol/kandidat sebelum evaluasi test baru yang independen.

Lihat [laporan model](docs/evidence/20261019-offline-model-development.md),
[metrics fall](artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/metrics.json)
dan [protokol occupancy](artifacts/research/20261019-occupancy-calibrated/protocol.json).

### Perangkat dan deployment, diperiksa 22 Oktober 2026

- Pi 4B 4 GB, OS 64 bit, kamera OV5647; kipas dua kabel pernah dikonfirmasi
  berputar oleh pemilik. Tidak ada sensor RPM yang bisa membuktikan putarannya.
- SSH `srasta@srasta-edge.local` berhasil. Alamat DHCP berubah mengikuti
  jaringan; periksa `hostname -I` pada Pi jika mDNS tidak tersedia.
- Release aktif: `/home/srasta/srasta-edge/releases/20261022-demo-v8-camera-burst-r3`.
  ARM64 acceptance, sensor kamera, restart service, Blynk dan cloud worker
  berhasil diperiksa. Backup unit/DB tersedia; lihat panduan operasi Pi.
- TX/RX **tidak terpasang** pada checkpoint ini sesuai keterangan pemilik.
  Status live `unavailable`, monitoring offline, zero frames, bukan simulasi.
  Trigger CSI → kamera → skeleton caregiver dan reboot fisik masih perlu diuji.
- Web terakhir tercatat di <https://srasta-caregiver.vercel.app>, Vercel scope
  `azzellls-projects`, project `srasta-caregiver`. Supabase/edge-sync pernah
  dideploy. Push GitHub ini tidak otomatis memasang Pi atau membuktikan deployment
  web baru; cek target branch integrasi Vercel sebelum deploy.
- Port lama Mac RX `/dev/cu.usbserial-3130`, TX `/dev/cu.usbmodem1234561`
  hanya referensi. Verifikasi label fisik/port setiap reconnect, jangan flash
  berdasarkan nomor lama.

## 3. Yang ikut Git dan yang dipindahkan privat

Ikut Git: source backend/AI, recorder/tests, firmware TX/RX dan defaults,
frontend + lockfile + aset Figma/font, Supabase SQL/functions, script Pi,
runbook, bukti engineering, selected fall/MoveNet/occupancy weights + config,
serta **metadata indeks/split** curated (tanpa H5). Semua snapshot model
terpilih terdaftar di [`docs/HANDOFF_ASSETS.json`](docs/HANDOFF_ASSETS.json).

```bash
python3 scripts/check_handoff_assets.py
```

Tetap lokal: raw CSI-Bench sekitar 26 GB, raw dataset eksternal, arsip sesi
lokal, `.env`/NVS/password/token/key, DB caregiver, foto/video kamera, cache
proposal privat/log AI, wheelhouse dan arsip paket lama. Snapshot model tertentu
dipublikasikan atas permintaan pemilik; ini tidak memberi izin redistribusi
raw dataset. Lihat [sumber data](docs/DATA_SOURCES.md).

Arsip lokal saat handoff berisi empat sesi (termasuk pilot/interrupt): laporan
QA yang tersedia menunjukkan **2 rejected, 2 pending, 0 accepted**. Sesi
terpandu sekitar 13,5 menit juga belum accepted. Ini bukan dataset training
lokal siap pakai. Teman harus meminta transfer arsip **secara privat**, termasuk
`subjects.jsonl` dan seluruh folder sesi beserta checksum/review; jangan kirim
hanya `frames.jsonl`, jangan membuat registry orang/split baru untuk orang sama.

## 4. Jalankan dari clone

Development yang terakhir dipakai: macOS ARM64, CPython 3.12.13.
macOS/Linux/Pi didukung oleh recorder POSIX; native Windows memerlukan port
khusus (`fcntl`, `lsof`, device paths), jangan menganggap COM langsung kompatibel.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r code/requirements-handoff.txt
cd web
npm ci
npm run build
cd ..
python3 scripts/check_handoff_assets.py
bash scripts/run_local.sh simulator --alarm disabled
```

Buka <http://127.0.0.1:8000>. Mode simulasi harus jelas dan tidak menghasilkan
ground truth atau bukti akurasi. Gunakan Node yang memenuhi `web/package-lock.json`
(Vite 7 membutuhkan Node modern; lingkungan verifikasi dicatat pada evidence).
Dependency pin adalah versi environment yang diketahui; pemasangan dari nol
pada semua OS belum dibuktikan. Untuk Pi ARM64/Python 3.13 gunakan
[`RASPBERRY_PI_SETUP.md`](RASPBERRY_PI_SETUP.md) dan installer paket, bukan
TensorFlow development Mac. Jangan menyalin `.venv` antararsitektur.

Untuk reproduksi seluruh tes dari source pada Pi, gunakan venv development
baru dengan `code/requirements-pi-dev.txt`; jangan meng-upgrade venv release
yang dipakai bersama. Lihat [setup development Pi](docs/PI_DEVELOPMENT_SETUP.md)
dan [bukti reproduksi ARM64](docs/evidence/20261022-pi-software-reproduction.md).

Cloud opsional; local mode tidak memerlukan akun cloud. Placeholder ada pada
`.env.example` dan `web/.env.example`. Ikuti [`CLOUD_SETUP.md`](CLOUD_SETUP.md)
untuk SQL, RLS, device registration, auth dan deploy. Service-role/device secret
tidak boleh masuk VITE/browser/Git. Akses akun/proyek diberikan pemilik privat.

### Periksa software

```bash
PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 .venv/bin/python -m unittest discover -s code/tests -v
cd web
npm test
npm run build
npm run test:cloud
```

Bukti fresh checkpoint: [`docs/evidence/20261021-github-handoff.md`](docs/evidence/20261021-github-handoff.md).
Test software tidak membuktikan recall, specificity, alarm fisik, koneksi Pi,
push HP atau mutu CSI hari ini. Jangan mengirim event palsu ke production.

## 5. Langkah berikutnya, urutannya

1. **Reproduksi clone**: baca guide, cocokkan hash model, jalankan tes dan
   simulator. Laporkan versi/hasil aktual serta gap; pertahankan desain Figma.
2. **Periksa CSI fisik**: identifikasi RX UART/COM, TX powered, posisi stabil,
   pilot 15 detik, QA profil/rate/drop/gap. Channel 6, UART 1.000.000 baud,
   `esp_idf_native`; jangan mengubah config training lama agar tampak cocok.
3. **Kumpulkan nonfall accepted**: guided CLI, beberapa orang dengan split
   tetap yang terpisah, pengamat independen, provenance/protokol lengkap.
   Prosedur di [capture quickstart](docs/CAPTURE_QUICKSTART.md).
4. **Pakai protokol recorder baru** `adl`, `motion` dan `fall-observer`
   sesuai [handoff fall](docs/FALL_ENGINEERING_HANDOFF.md). Awake-lying vs
   natural sleep masih memerlukan referensi/anotasi yang membedakan sleep
   dan inactive; jangan mengubah label diam menjadi tidur. Event jatuh hanya
   di bawah prosedur aman terawasi yang disetujui.
5. **Latih/kalibrasi** fall lokal terlebih dahulu, kemudian presence ketika
   train/validation accepted cukup dan domain telah diperiksa. Bekukan
   threshold/preprocessing sebelum test baru. Laporkan confusion matrix,
   interval ketidakpastian, event recall dan FAR dari exposure direview;
   jangan mengganti label atau split setelah melihat prediksi.
6. **Lanjutkan acceptance Pi yang sudah diperbarui**: sambungkan RX UART/COM
   dan daya TX, uji CSI nyata + kamera event-only + skeleton event UID yang
   sama pada caregiver. Uji kejadian/ACK/push pada HP. Pemilik menyatakan
   ketahanan pass; tidak perlu mengulang seluruh suite ketahanan di tahap ini.
   Acceptance ARM dan satu burst kamera terisolasi sudah lolos pada 22 Oktober;
   ini belum membuktikan seluruh jalur kejadian. Periksa alarm fisik terpisah.
   Jangan menimpa service secara buta; backup/rollback ada di panduan operasi.

Pembuatan paket baru setelah build web (nama output harus baru):

```bash
.venv/bin/python scripts/pack_pi_demo.py \
  --output artifacts/pi/HANDOFF_NEW_RELEASE.tar.gz \
  --camera-model artifacts/models/movenet-lightning/model.tflite \
  --research-run artifacts/research/20261019-occupancy-calibrated
```

Paket tidak menyertakan credentials atau raw data; model riset tetap tidak
aktif live. Lihat [`docs/pi-offline-package.md`](docs/pi-offline-package.md).

## 6. Peta source untuk AI penerus

- `firmware/esp32_s3_csi_tx`, `firmware/esp32_s3_csi_serial`: ESP-IDF TX/RX saat ini.
- `code/srasta_csi/contract.py`, `decoder.py`, `preprocess.py`, `model.py`,
  `edge.py`: kontrak dan jalur inferensi.
- `monitoring.py`, `caregiver.py`, `cloud_sync.py`, `blynk_mqtt.py`: state dan output.
- `camera.py`, `camera_capture.py`, `pose.py`: worker event-only dan pose.
- `capture_archive.py`, `capture_metrics.py`, `capture_service.py`,
  `code/tools/record_esp32_capture.py`: rekaman, kualitas, anotasi dan review.
- `code/train_local_presence.py`, `train_srasta_release.py`,
  `train_offline_candidates.py`, `train_public_occupancy.py`: jalur training
  yang berbeda; baca argumen/protokol sebelum memakai data.
- `web/src`, `supabase/migrations`, `supabase/functions`: caregiver dan cloud.
- `code/tests`, `web/src/**/*.test.*`, `web/scripts/test-cloud.mjs`: tes.
- `docs/evidence`: catatan bertanggal; jangan menyalin angka checkpoint lama
  sebagai hasil terbaru atau mengira semua output eksperimen ikut Git.

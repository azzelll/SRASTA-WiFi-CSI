# Audit sumber data dan pembagian model fall

Diperiksa 28 Oktober 2026 dari manifest, metadata model terpilih, kode loader,
dan metadata eksperimen lokal. Angka di bawah berlaku untuk **fall TCN-Lite
v8** dan eksperimen head fine-tuning lokal 26 Oktober, bukan gabungan seluruh
model occupancy, breathing, dan kamera.

## Model yang masih dipilih

Model demo tetap
`artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/`.
Bobot classifier sama dengan v2; v8 mengalibrasi motion gate memakai primary
train. Input satu window adalah 500 frame × 52 kanal, sekitar 5 detik pada
laju nominal 100 Hz. Durasi nominal tersebut bukan bukti timing paket live.

Bobot v8 berasal dari CSI-Bench ESP32-S3. Rekaman tim belum dipakai untuk
mengubah bobot model demo. Data tim dipakai untuk diagnosis v8 dan eksperimen
fine-tuning kandidat terpisah yang **tidak dipromosikan**. ESP-Fi HAR dan
WiFall pernah tersedia untuk eksperimen lain; keduanya tidak digunakan oleh
run v2 yang menjadi bobot v8 (`external_data: not used`).

## CSI-Bench: rekaman dan window

Indeks yang digunakan adalah
`data/curated/esp32_s3_fall_v1/manifest.csv`, khusus
`FallDetection/device_ESP32`. Ini bukan jumlah seluruh corpus CSI-Bench.

| Pembagian | Subjek | Rekaman | Fall | Nonfall | Alokasi window 500×52 |
| --- | --- | ---: | ---: | ---: | ---: |
| Train | U08, U09, U11, U12, U17, U18 | 288 | 170 | 118 | 288 |
| Validation development | U19 | 77 | 40 | 37 | 77 |
| Test terdaftar | U21 | 80 | 40 | 40 | 80 |
| Dikeluarkan | U22 | 27 | 27 | 0 | 0 digunakan |
| Total di indeks | 9 subjek | 472 | 277 | 195 | 445 pada train/validation/test |

Semua rekaman terindeks mempunyai 500 frame. Loader release memproses satu
rekaman menjadi satu window 500×52 untuk kandidat terpilih; tidak ada random
split potongan window. Jadi 472 rekaman tidak berarti 472 window training:
training bobot memakai 288 window. Sebanyak 256 window representative untuk
kuantisasi INT8 adalah subset train, bukan tambahan rekaman atau window unik.

Proporsi dari 445 rekaman yang tidak dikeluarkan adalah sekitar
64,72% train / 17,30% validation / 17,98% test, ditentukan oleh subjek,
bukan pembagian acak 70/15/15. U22 dikeluarkan karena hanya memiliki fall.

Validation U19 sudah dipakai berulang dalam pengembangan dan pemilihan
kandidat/threshold. Test U21 pernah dievaluasi untuk v2; laporan historisnya
memuat 80 rekaman dan `test_used_for_fitting: false`. U21 tidak dibuka kembali
untuk mengalibrasi v8. Hasil historis v2 tidak menguji ulang motion gate v8
atau menjadi test lokal baru yang independen.

## Rekaman tim: rekaman dan window

Eksperimen `20261026_local_fall_v1` menggunakan 25 sesi accepted:

| Jenis sesi | Rekaman/sesi accepted | Window unik yang diekstrak | Peran |
| --- | ---: | ---: | --- |
| Fall A/B/C | 12 | 12 fall | Satu window aktual per kejadian, berakhir pada akhir fall |
| Presence/nonfall A/B/C | 5 | 109 nonfall | Fine-tuning dan development antarorang |
| Empty | 8 | 192 background | Diagnosis background; tidak masuk fit atau kalibrasi fold |
| Total | 25 | 313 | 121 window orang + 192 background |

Sebelas calon window negatif tidak lolos coverage dan dikeluarkan. Angka 313
adalah window unik dari ekstraksi eksperimen ini, bukan seluruh kemungkinan
sliding window sepanjang rekaman. Sesi pilot, terputus, pending atau rejected
tidak dihitung sebagai sesi accepted untuk eksperimen ini.

Seluruh 25 sesi tersebut tercatat pada **train/development**. Inventaris
metadata sesi pada 28 Oktober menunjukkan **0 rekaman validation** dan
**0 rekaman test** lokal. LOC_D dicadangkan untuk validation dan LOC_E untuk
test setelah model, preprocessing, dan threshold dibekukan; pencadangan kode
tidak berarti datanya sudah direkam.

Encoder v8 dibekukan; hanya head Dense kandidat yang di-fine-tune selama
delapan epoch. Eksperimen memakai 121 window dari 17 sesi berorang:
A = 24 window (4 fall + 20 nonfall), B = 48 (4 + 44), C = 49 (4 + 45).

| Fold | Fit | Kalibrasi threshold | Evaluasi development |
| --- | --- | --- | --- |
| 1 | A: 24 window, 5 sesi | B: 48 window, 6 sesi | C: 49 window, 6 sesi |
| 2 | B: 48 window, 6 sesi | C: 49 window, 6 sesi | A: 24 window, 5 sesi |
| 3 | C: 49 window, 6 sesi | A: 24 window, 5 sesi | B: 48 window, 6 sesi |

Tiap fold dijalankan dengan seed 42/43/44: sembilan fit fold, tanpa menambah
jumlah kejadian atau window unik. Kandidat akhir kemudian di-refit memakai
seluruh 121 window A/B/C; replay kandidat akhir pada A/B/C adalah **in-sample**.
OOF fold tetap hasil development, bukan test D/E independen. Kandidat tidak
dipromosikan karena recall meningkat tetapi specificity turun.

## Apakah rekaman atau orang yang sama melintasi pembagian?

- **CSI-Bench:** pemeriksaan ulang metadata menemukan nol irisan subject ID,
  source path, dan sample ID di antara train, validation, dan test. Pemisahan
  orang dilakukan sebelum windowing. Pemisahan ini tidak membuktikan
  generalisasi ke ruangan/perangkat baru.
- **Data tim dalam satu fold:** orang A/B/C berbeda untuk fit, kalibrasi, dan
  evaluasi. Pemeriksaan semua sembilan hasil fit menemukan nol irisan sesi
  antara ketiga peran. Semua window sesi/orang yang sama mengikuti perannya.
- **Data tim antar-fold:** orang dan window yang sama memang berganti peran
  melalui rotasi cross-validation. Karena itu jangan mengatakan A/B/C adalah
  train/validation/test permanen, atau mengklaim seluruh hasil sebagai test
  independen. Set lokal independen D/E belum tersedia.

Koreksi identitas A/B/C dibaca dari sidecar yang terikat checksum sebelum
grouping. ID lama `LOC_001` di config asli tetap dipertahankan untuk integritas
arsip; tidak dipakai sebagai satu-satunya identitas peserta saat membentuk fold.

## Bukti dan reproduksi

- [Split dan overlap v8](../artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/split_report.json).
- [Config training v8](../artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/training_config.json)
  dan [motion calibration](../artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/motion_calibration.json).
- [Loader release](../code/train_srasta_release.py), fungsi `read_processed`
  dan `crop`; [trainer lokal](../code/train_local_fall.py), `prepare` dan `fit`.
- [Workflow lokal](LOCAL_CAPTURE_DEVELOPMENT.md) dan
  [laporan eksperimen 26 Oktober](evidence/20261026-local-fall-development.md).
- Metadata privat: `prepared.json`, `windows.json`, `protocol.json`,
  `seed_42.json`, `seed_43.json`, `seed_44.json`, `comparison.json` pada
  `../SRASTA_LOCAL_CAPTURE/experiments/20261026_local_fall_v1/`.

Audit menghitung ulang CSV split, metadata window, dan daftar sesi tiap fold;
membandingkan hash manifest dengan config model; serta memeriksa inventaris
split lokal dari `capture_config.json` tanpa membuka payload validation/test.
Raw CSI, metadata privat per sesi, dan bobot kandidat lokal tetap di luar Git.

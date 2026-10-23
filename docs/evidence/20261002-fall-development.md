# Audit dan validasi fall detection — 2 Oktober 2026

Empat pekerjaan offline selesai: audit sumber data, pemeriksaan preprocessing
dan window, perbandingan Random Forest/SVM/TCN, serta validasi antarorang.
**Target recall ≥80% dan specificity ≥80% sekaligus belum tercapai.**
Seluruh angka di sini memakai label satu rekaman; event recall dan false alert
per jam masih belum tersedia.

## 1. Sumber dan integritas data

Indeks utama tetap `data/curated/esp32_s3_fall_v1/manifest.csv`.
Audit payload meliputi 288 rekaman train dan 77 validation. Test U21 dan
kelompok excluded tidak dibuka dalam pekerjaan ini.

| Pemeriksaan pada 365 rekaman | Hasil |
|---|---|
| Shape asli `[64,500,1]`, nilai finite dan nonnegatif | Lulus |
| Posisi di luar mask `6..31,33..58` | Seluruhnya nol |
| Kanal terpilih yang seluruhnya nol | 0 rekaman |
| Label, orang, dan session terhadap metadata sumber | 0 ketidaksesuaian |
| Duplikasi persis array, termasuk lintas split atau beda label | 0 kelompok |
| Lingkungan | Semua E22 |
| Difficulty pada metadata | Semua Hard |
| Timestamp paket yang tersimpan | 0 rekaman |

Kecocokan metadata tidak membuktikan bahwa label kejadian sudah diperiksa
ulang terhadap video. Tidak ada anotasi onset/offset jatuh yang terverifikasi
dalam H5 yang digunakan.

Pengembang menyebut perbaikan data dan [rilis Kaggle versi 12](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark).
API publik Kaggle mengonfirmasi versi 12 pada pemeriksaan ini.
CSV metadata FallDetection lokal, berisi 6.700 baris, **identik byte demi byte**
dengan CSV versi 12; SHA256:

```text
7b8e66d81df9cd14323b0bf90c3f2f9c3f9ac74c6b56be53b1fa624ef67eed9b
```

Tiga rekaman train yang ditentukan sebelum pengecekan juga identik byte dan
array dengan versi 12:

- `U08_Fall_E22_1000`
- `U08_Nonfall_E22_1000`
- `U11_Fall_E22_100000`

Pengecekan sampel ini tidak mengattestasi seluruh folder 81 GB. Namun,
perbedaan layout HAR saja tidak cukup untuk menyatakan FallDetection lokal
usang atau rusak. Rekaman remote hanya dibaca di memori untuk checksum.

Artefak audit:

- `artifacts/research/20261002-fall-audit/audit.json`
- `upstream_version_check.json`
- `upstream_metadata_comparison.json`
- `upstream_recording_comparison.json`

## 2. Preprocessing dan informasi temporal

[Paper CSI-Bench, §4.2](https://arxiv.org/html/2505.21866v2#S4.SS2)
menjelaskan window fall 5 detik dan normalisasi mean/std seluruh window.
[Loader resmi](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark/blob/main/load/supervised/benchmark_dataset.py)
menerapkan normalisasi sebelum standardisasi ukuran input.

Eksperimen ini mengadaptasi normalisasi pada **52 posisi terukur yang tetap**.
Input tetap `[500,52]`; fitur perangkat HP 232 kanal tidak dicampurkan,
dan carrier tidak dipad, digeser, atau diresize. Ini eksperimen SRASTA yang
terinspirasi sumber tersebut, bukan reproduksi tabel benchmark 232 fitur.

| Pipeline | Operasi |
|---|---|
| `causal_filtered` | Pipeline bersama: Hampel dengan history hasil filter, low-pass 10 Hz, baseline relatif, clip ±2 |
| `causal_raw` | Konfigurasi sama; history Hampel berasal dari sampel mentah sebelumnya |
| `paper_window_zscore` | Mean/std seluruh window terukur; tanpa Hampel, low-pass, atau baseline EMA |

Median elemen yang diganti Hampel adalah **16,4%** pada history hasil filter
dan **5,85%** pada history mentah. Persentase ini tidak menentukan apakah
elemen yang diganti merupakan noise atau informasi jatuh.

Puncak energi perubahan amplitudo berada di crop tengah 250 frame pada hanya
**183/365 rekaman**. Puncak energi belum merupakan ground truth onset jatuh.
Semua eksperimen berikut menggunakan **500 frame penuh** agar informasi di
luar crop tengah tetap tersedia.

Normalisasi seluruh window hanya memakai rekaman saat itu. Jika diterapkan
pada streaming, keputusan harus dibuat sesudah window trailing lengkap;
hasil prefix tidak memiliki jaminan kausalitas per frame. Implementasi ini
berstatus riset dan belum dipasang pada edge live. Nominal 100 Hz digunakan
untuk H5 karena timestamp aktual tidak disediakan.

## 3. Protokol perbandingan yang dikunci sebelum training

Script: `code/train_fall_grouped.py`. Utilitas bersama:
`code/srasta_csi/development.py`.

- Enam orang primary train: U08, U09, U11, U12, U17, U18.
- Enam outer fold. Satu orang untuk evaluasi, orang berikutnya menurut urutan
  siklik untuk kalibrasi, dan empat orang lain untuk fitting.
- Kalibrasi threshold dan early stopping tidak menggunakan orang outer
  evaluation. Setiap rekaman mendapatkan satu prediksi outer per seed.
- Seed 42, 43, 44. RF dan SVM dibandingkan pada tiga pipeline; TCN pada
  `causal_filtered` dan `paper_window_zscore`.
- RF: 300 pohon, min leaf 3, class weighting. SVM: RBF, C=1, scaler dan
  fitting probabilitas hanya pada orang fitting.
- RF/SVM memakai 39 fitur: energi/derivative, variance, rasio temporal,
  entropy, sepuluh bin energi perubahan dan variance, quantile, dan lokasi
  puncak. Bin tidak diberi label onset buatan.
- TCN: 24 kanal, kernel 3, dilasi 1/2/4/8/16, average+max pooling,
  dropout 0,1, Adam 3e-4, maksimum 35 epoch, patience 6 pada orang kalibrasi.
- Pilih pipeline per keluarga dari rerata metrik outer atas tiga seed:
  lulus kedua gate, kemudian maksimum nilai terendah recall/specificity,
  kemudian macro F1.
- Final seed ditetapkan 42. Threshold final berasal dari probabilitas
  out-of-fold **train**. Epoch final TCN berasal dari median epoch terbaik
  kalibrasi seed42, yaitu 7. Model final di-fit pada 288 rekaman train.
- Pada fase refit final, pilihan, threshold, epoch, dan bobot ketiga model
  disimpan sebelum fase tersebut membaca payload U19. Audit awal sudah
  memeriksa U19; set ini juga pernah dipakai secara historis. U19 tidak
  mengubah threshold atau memilih pemenang pada eksperimen ini.

Protocol, hash kode/data, versi library, ID tiap peran/fold, history dan
prediksi disimpan di `artifacts/research/20261002-fall-grouped/`.
`provenance_scope_clarification.json` menjelaskan bahwa flag pembukaan
validation pada laporan asli hanya berlaku untuk fase refit final.
Source training yang tepat sesuai hash preregistrasi disimpan di
`source_snapshot/train_fall_grouped.py`; script berikutnya memakai nama
field yang secara eksplisit menyebut fase tersebut. Bobot dan threshold
hasil eksperimen tidak diubah.
Ada 108 fitting baseline dan 36 fitting TCN pada fold, kemudian tiga refit
final. Tidak ada pencarian model lanjutan berdasarkan hasil U19.

## 4. Hasil antarorang pada primary train

Angka adalah rerata ± standar deviasi atas tiga seed, memakai threshold dari
orang kalibrasi tiap fold. Pemilihan kandidat menggunakan hasil development
ini; angka berikut bukan hasil test independen.

| Model | Pipeline | Recall | Specificity |
|---|---|---:|---:|
| RF | causal_filtered | 63,1 ± 1,7% | 52,8 ± 1,4% |
| RF | causal_raw | 67,3 ± 1,0% | 58,8 ± 1,1% |
| RF | paper_window_zscore | 61,0 ± 2,3% | 59,9 ± 3,1% |
| SVM | causal_filtered | 71,2 ± 0,0% | 54,2 ± 0,0% |
| SVM | causal_raw | 60,8 ± 0,3% | 50,8 ± 0,0% |
| SVM | paper_window_zscore | 64,1 ± 0,0% | 55,1 ± 0,0% |
| TCN | causal_filtered | 48,0 ± 8,1% | 58,8 ± 7,4% |
| TCN | paper_window_zscore | 53,5 ± 7,7% | 57,6 ± 3,9% |

Aturan pemilihan nilai terendah dua metrik memilih `paper_window_zscore`
untuk ketiga keluarga. RF `causal_raw` mempunyai recall dan macro F1 lebih
tinggi, sedangkan specificity reratanya sedikit lebih rendah.

Threshold global OOF dicatat terpisah sebagai hasil tuning development;
angka pada tabel ini menggunakan threshold kalibrasi tiap fold, sehingga
label outer tidak memilih threshold fold itu sendiri.

## Pemeriksaan U19 sesudah freeze

U19 berisi 40 fall dan 37 nonfall. Untuk 80%/80%, diperlukan sedikitnya
32 fall dan 30 nonfall yang diprediksi benar.

| Model final | Threshold dari train OOF | Recall | Specificity | TP/FN/TN/FP |
|---|---:|---:|---:|---|
| RF | 0,574344 | 55,0% | 73,0% | 22 / 18 / 27 / 10 |
| SVM | 0,647082 | 45,0% | 70,3% | 18 / 22 / 26 / 11 |
| TCN INT8 | 0,583459 | 42,5% | 54,1% | 17 / 23 / 20 / 17 |

U19 sudah digunakan pada eksperimen historis. Pemeriksaan ini merupakan
development validation dengan orang berbeda dari fitting, dan tidak menjadi
bukti test independen atau performa jatuh lokal. U21 tidak dibuka kembali.

TCN INT8: 50.592 byte, MAE FP32/INT8 0,00858, max error 0,03590,
argmax agreement 100%, inference rata-rata 0,196 ms pada Mac ini.
Keputusan FP32 dan INT8 pada threshold yang dikunci memiliki confusion matrix
yang sama. Parity lulus; target klasifikasi gagal. Latency ini tidak
membuktikan latency Raspberry Pi atau waktu alarm end-to-end.

SHA256 model:

```text
28ab644285b1227569731d13457f1e8e4bcd77bf4bd2cf79b01ee4de35754b01
```

Artefak final menyatakan `research_only: true`, `deployment_ready: false`.
Loader fall live telah diuji menolak artefak TCN ini. Threshold default target
pada `train_srasta_release.py` kini 80%/80% dan memeriksa seluruh batas
probabilitas terukur; laporan dan bobot release historis tetap disimpan.

## Verifikasi perangkat lunak dan batas bukti

- 87 unit/integration test lulus, 0 error/skip; log
  `/private/tmp/srasta-tests-grouped-20261002.log`.
- Tes mencakup pemisahan tiga peran orang, coverage outer satu kali, penolakan
  pembukaan payload test/excluded, normalisasi per rekaman, dan gate gabungan.
- `py_compile` dan `git diff --check` lulus.
- Hash semua 365 H5 dan manifest diperiksa kembali: tidak berubah.
- Data, cache rekaman, dan bobot tetap dalam lokasi Git-ignored; tidak ada
  commit atau upload rekaman lokal.
- Target 80%/80% belum terbukti pada protokol ini. Angka benchmark accuracy/F1
  tidak menggantikan recall/specificity pada orang atau alat berbeda.
- Event recall, false alert/jam, packet timing asli, konfirmasi diam setelah
  jatuh, dan validasi lokal masih memerlukan anotasi dan data yang sesuai.

Eksperimen ini menunjukkan bahwa perubahan normalisasi dan keluarga model
yang diuji belum cukup untuk mencapai target. Dataset jatuh dan aktivitas
pembanding dari konfigurasi ESP32 lokal, dengan waktu kejadian dan review
label yang jelas, menjadi langkah berikutnya untuk menguji generalisasi
serta menambah data fine-tuning. Aktivitas duduk cepat, berbaring, membungkuk,
dan mengambil barang perlu terwakili sebagai nonfall. Pengambilan jatuh
memerlukan protokol terkendali dan pendamping.

## Menjalankan ulang di direktori baru

Dari root repository; gunakan nama output baru karena hasil final tidak
ditimpa:

```bash
.venv/bin/python code/tools/audit_fall_development.py \
  --out-dir artifacts/research/fall-audit-new

.venv/bin/python code/train_fall_grouped.py --stage baseline --epochs 35 \
  --out-dir artifacts/research/fall-grouped-new
.venv/bin/python code/train_fall_grouped.py --stage tcn --epochs 35 \
  --out-dir artifacts/research/fall-grouped-new
.venv/bin/python code/train_fall_grouped.py --stage final --epochs 35 \
  --out-dir artifacts/research/fall-grouped-new

PYTHONPATH=code .venv/bin/python -m unittest discover -s code/tests -v
```

Audit lokal pertama tidak mengunduh sumber remote. Bukti perbandingan versi
dengan metadata dan tiga sampel train disimpan sebagai JSON follow-up
terpisah. TX/RX tidak diperlukan untuk menjalankan eksperimen offline ini.

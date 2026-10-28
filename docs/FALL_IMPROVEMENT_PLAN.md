# Langkah peningkatan fall detection — 23 Oktober 2026

## Urutan yang ditetapkan pemilik

1. Perbaiki fall detection.
2. Dataset lokal.
3. Presence.
4. Validasi.
5. Uji pengalaman caregiver.

Pemilik menyatakan uji ketahanan sudah pass. Rencana ini tidak menjadwalkan
ulang seluruh pengujian ketahanan. Pemeriksaan kandidat model baru tetap
mencakup kesesuaian preprocessing, INT8 dan eksekusi inferensi.
Seluruh fitur proposal tetap menjadi requirement produk.

Pekerjaan nomor 1 dimulai secara offline dengan data yang tersedia. Nomor 2
nanti menyediakan bukti generalisasi lokal; keberhasilan offline tidak
menggantikan pembuktian tersebut. Tidak diperlukan Pi atau simulasi jatuh
manusia untuk memulai langkah di dokumen ini.

**Pelaksanaan 23 Oktober selesai untuk eksperimen offline ini:** diagnosis
365 rekaman dan 36 fitting grouped sudah dijalankan. Kandidat Hampel raw
ditolak; v8 tetap model demo. Recorder/evaluator data lokal dan tes sudah
dilengkapi. Hasil dan giliran pemilik ada di
[FALL_ENGINEERING_HANDOFF.md](FALL_ENGINEERING_HANDOFF.md) serta
[bukti engineering](evidence/20261023-fall-engineering.md).
Bagian persiapan di bawah merekam keadaan sebelum pelaksanaan tersebut.

## Titik awal yang diperiksa

- Checkout: `main`, `9bf0afd`.
- Model acuan: `artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/`.
- TCN: 500 frame × 52 fitur, 32 kanal, dilasi 1/2/4/8/16; INT8.
- H5 memakai 100 Hz nominal karena tidak memiliki timestamp paket; 500 frame
  tidak membuktikan durasi atau latency kejadian pada stream hardware.
- Threshold classifier: 0,45. Motion threshold: 0,0003443831083131954.
- SHA-256 model:
  `ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.
- Train: 288 rekaman, 170 fall / 118 nonfall, enam orang
  U08/U09/U11/U12/U17/U18.
- Development validation: U19, 77 rekaman, 40 fall / 37 nonfall.
- U21: test historis yang sudah pernah diperiksa; tidak dibuka untuk pekerjaan ini.
- Preflight 23 Oktober: 365/365 file train/validation tersedia; payload test
  tidak dibaca. Hash model dan manifest cocok dengan metadata training.
  Pemeriksaan 32 aset handoff lulus.
- Environment tersedia: CPython 3.12.13, TensorFlow 2.21.0, NumPy 2.5.1,
  h5py 3.14.0, scikit-learn 1.9.0, joblib 1.5.3.

Metrik tersimpan v8 pada U19, bukan hasil inference baru dalam persiapan ini:

| Label asli | Prediksi nonfall | Prediksi fall |
| --- | ---: | ---: |
| Nonfall | 24 | 13 |
| Fall | 15 | 25 |

Recall 62,5%, specificity 64,9%, precision fall 65,8%, F1 fall 64,1%.
Ini proxy per rekaman. Onset/offset dan exposure negatif beranotasi tidak
tersedia, sehingga event recall, false alerts/hour dan latency kejadian
tidak dapat dihitung dari angka tersebut.

Target proposal tetap recall fall >=88% dan specificity >=80%.
80%/80% yang dipakai beberapa eksperimen adalah milestone pengembangan,
bukan pengganti target proposal atau bukti produk siap dipakai.

## 1. Bekukan pembanding dan aturan eksperimen

Pekerjaan:

- Catat model/config/manifest/hash serta confusion matrix v8 di atas.
- Gunakan output riset baru untuk setiap eksperimen; jangan menimpa v8.
- Simpan `protocol.json` sebelum fitting: hipotesis, perubahan tunggal,
  split/fold, seed, aturan pemilihan, metrik dan batas keberhasilan.
- Pisahkan threshold classifier/motion dari ambang panel OLED 75/85%.
  Mengubah warna atau bunyi panel bukan peningkatan kemampuan classifier.

Selesai bila baseline dan protokol dapat dibaca ulang tanpa mengandalkan
ingatan operator. Model live tidak diganti dalam tahap ini.

## 2. Buat laporan kesalahan sebelum training kandidat

Pekerjaan berikutnya yang paling awal adalah tooling laporan berikut:

- Satu baris per rekaman: sample ID, orang, label, skor classifier,
  energi gerak, keluaran classifier saja dan keluaran setelah motion gate.
- Tampilkan contoh TP/TN/FP/FN: amplitudo mentah dan hasil preprocessing,
  energi terhadap waktu, skor, serta pengaruh Hampel/clipping.
- Kelompokkan kesalahan menurut orang dan karakteristik sinyal, bukan
  menebak nama aktivitas yang tidak tersedia pada label sumber.
- Bedakan jatuh terlewat karena classifier, motion gate atau informasi
  sinyal yang berubah saat preprocessing. Energi puncak bukan label onset.
- Catat perbedaan domain sumber dan live: geometri/ruangan, rate/timestamp,
  channel serta urutan subcarrier. Jangan mengubah config lama atau resize
  data agar perbedaan tersebut terlihat hilang.
- Gunakan hasil train out-of-fold yang sudah tersimpan untuk menentukan
  hipotesis. Jika memerlukan baseline OOF yang sebanding, latih ulang
  konfigurasi baseline dalam setiap fold.

V8 sudah dilatih pada enam orang train: prediksinya terhadap train sendiri
tidak boleh disebut OOF atau bukti generalisasi. U19 boleh dicatat sebagai
diagnostik pengembangan historis, tetapi tidak digunakan mencari threshold
atau memilih kandidat baru dalam protokol ini.

Output rencana: `baseline_predictions.csv`, ringkasan FP/FN, plot lokal,
dan maksimal dua hipotesis eksperimen dengan alasan terukur.
Tooling khusus laporan v8 ini belum dibuat dalam persiapan dokumen.
Tooling tersebut kemudian dibuat sebagai `code/tools/diagnose_fall.py` pada
pelaksanaan di atas.

## 3. Uji kandidat dengan pemisahan orang

Gunakan struktur `grouped_folds` yang sudah ada:

- Enam outer fold dari orang primary train.
- Setiap fold: empat orang fitting, satu orang kalibrasi/early stopping,
  satu orang evaluasi. Tidak ada window satu orang di kedua peran.
- Threshold, transform yang perlu fit, class weight dan motion threshold
  dihitung hanya dari bagian yang diizinkan dalam fold. Orang evaluasi
  tidak menentukan threshold atau preprocessing.
- Tetapkan seed 42/43/44. Jalankan baseline dan kandidat dengan fold yang
  sama; laporkan rerata, variasi antar-seed dan hasil per orang.
- Mulai dari paling banyak dua perubahan yang didukung diagnosis tahap 2.
  Satu perubahan utama per kandidat agar penyebab perubahan hasil terbaca.

Jangan langsung mengulang seluruh pencarian terdahulu. RF/SVM/TCN,
normalisasi window/channel, fitur temporal, transfer dan beberapa arsitektur
TCN sudah pernah dicoba tanpa mencapai kedua target sekaligus. Periksa
`evidence/20261002-fall-development.md` dan
`evidence/20261019-offline-model-development.md` sebelum menetapkan eksperimen.

Pilih berdasarkan kedua metrik recall dan specificity, macro F1, dan
kerapuhan per orang. Semua hasil OOF yang dipakai memilih kandidat tetap
berstatus development, bukan test independen.

Selesai bila tersedia tabel baseline versus kandidat dengan prediksi OOF,
protokol, hash dan keputusan lanjut/tolak. Kandidat yang menukar kenaikan
recall dengan penurunan specificity harus dilaporkan sebagai tradeoff.

## 4. Bekukan kandidat, refit dan ekspor

- Pilih konfigurasi/threshold/aturan epoch berdasarkan primary train OOF.
- Refit pada primary train. Ekspor INT8 dengan representative data train.
- Simpan model, preprocessing, capture profile, motion gate, hash dan
  provenance bersama. Periksa perubahan keputusan FP32 versus INT8,
  termasuk pada threshold classifier.
- Batas parity yang saat ini ada: MAE <=0,02, max error <=0,10,
  argmax agreement >=95%; ukuran model proposal <=1 MB.
- Setelah semuanya beku, jalankan satu pemeriksaan development U19,
  laporkan kedua metrik dan bandingkan v8 pada basis yang sama.
  Jangan mengubah cutoff lalu mengulang pemeriksaan untuk membuatnya lolos.

U19 sudah digunakan berulang secara historis, sehingga hasilnya tidak
menjadi hasil test baru. Jangan memakai `--evaluate-frozen` untuk membuka
U21; pembuktian independen berikutnya memakai cohort lokal tahap 2.

## 5. Putuskan hasil nomor 1 dan serahkan kebutuhan dataset lokal

Keluaran akhir:

- Laporan penyebab kesalahan utama serta hasil kandidat/penolakan.
- Model kandidat beserta config dan INT8 parity, bila kandidat layak.
- Tabel recall, specificity, precision, F1, FP/FN dan hasil per orang.
- Daftar data yang perlu dikumpulkan pada prioritas dataset lokal:
  aktivitas pembanding dan kondisi ruangan yang didukung diagnosis,
  exposure nonfall panjang, serta event fall dengan prosedur dan anotasi
  yang sesuai. Jangan mengarang label aktivitas atau onset.

Jika belum ada kandidat lebih baik, hasil yang benar adalah gap yang
terukur dan kebutuhan data yang spesifik. Jangan mengganti model live
semata-mata karena training atau parity berhasil. Pemasangan kandidat
memerlukan keputusan berdasarkan hasil dan jalur rollback yang sudah ada.

## Yang perlu disiapkan sekarang

- Mac/laptop dan `.venv` proyek; ruang output baru untuk laporan/eksperimen.
- Dataset lokal yang sudah tersimpan di komputer ini, tanpa memindahkan raw
  ke cloud atau mengubah source.
- Blok waktu untuk membaca laporan kesalahan dan menetapkan hipotesis
  eksperimen sebelum fitting panjang. Durasi training belum diukur.
- Pi dan hardware baru diperlukan ketika memeriksa eksekusi kandidat
  terpilih; pengumpulan data baru berada pada prioritas berikutnya.

Jalankan command dari root repo. Referensi CLI yang sudah ada:

```bash
python3 scripts/check_handoff_assets.py
PYTHONPATH=code .venv/bin/python code/train_fall_grouped.py --help
PYTHONPATH=code .venv/bin/python code/train_srasta_release.py --help
```

`train_fall_grouped.py` menyediakan fold/calibration dan prediksi per rekaman
untuk protokol lama. `train_srasta_release.py` melakukan seleksi pada U19;
jangan menjalankan sweep default-nya sebagai protokol OOF baru.
Command di atas adalah asset check dan bantuan CLI, bukan training kandidat.

Tidak ada training baru, pembukaan payload test, perubahan model/panel,
akses hardware atau klaim peningkatan akurasi dalam persiapan ini.
Setelah persiapan ini, training ablation dilakukan sebagaimana laporan di
atas; tidak ada kandidat yang layak dipromosikan dan tidak ada payload test
yang dibuka.

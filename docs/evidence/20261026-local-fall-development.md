# Pengembangan fall lokal — 26 Oktober 2026

Pemilik menyampaikan persetujuan tim untuk penggunaan 8 empty dan 5 presence
lama sekarang. Keputusan terikat hash dicatat terpisah; tidak mengubah config,
raw, event, review atau checksum dan tidak mengklaim izin sebelum perekaman.
QA kini menerima 25 sesi direview (12 fall, 5 presence, 8 empty). Loader
menggunakan koreksi orang A/B/C sebelum windowing; empty memakai kelompok
background per sesi. Detail [workflow lokal](../LOCAL_CAPTURE_DEVELOPMENT.md).

## Eksperimen yang dijalankan

Dataset berisi 12 window fall unik, 109 nonfall A/B/C, dan 192 background.
Sebelas calon negative dikeluarkan karena coverage. Encoder TCN v8 dibekukan;
head Dense di-fine-tune delapan epoch. Tiga fold siklik memisahkan orang fit,
kalibrasi dan evaluasi; seed 42/43/44 menghasilkan sembilan fit. Background
tidak dipakai untuk fit atau kalibrasi antarorang. Parameter/protokol
disimpan sebelum ekstraksi; tidak ada padding, replikasi stillness atau test.

| Window development pada orang A/B/C | Recall fall | Specificity |
|---|---:|---:|
| v8 INT8 tetap | 0,0% | 100,0% |
| Fine-tuned head, mean OOF 3 seed | 36,1% | 71,6% |

Kandidat **tidak dipromosikan** karena specificity turun. Ini cohort lokal
yang sudah pernah diperiksa, bukan test independen; tiga seed tidak membuat
12 fall menjadi 36 kejadian unik. INT8 parity pass (MAE 0,002220, max error
0,007121, argmax agreement 100% pada 121 window) tidak membuktikan akurasi.

## Diagnosis episode

Prediksi v8 yang tersimpan pada seluruh exposure nonfall accepted: 10 false
alert dalam 6,496 jam eligible (1,539/jam), dan 0/7 fall eligible terdeteksi.
Lima fall dikeluarkan dari evaluasi karena truth/coverage 8 detik tidak cukup.
Semua hasil ini train/development; tidak ada confirmation-eligible fall
karena stillness terlabel kurang dari 10 detik.

Replay kedua model pada window/timestamp sama menggunakan langkah 1 detik,
awal/tengah/akhir interval nonfall masing-masing 60 detik dan warm-up 30 detik.
Pada 37,77 menit exposure eligible: v8 0 episode false alert baru, kandidat
11 episode baru dan 16 episode sudah berlangsung sebelum bagian dinilai.
Kandidat mendeteksi 2/7 eligible dengan suspected latency lokal 2,731/2,891 s.
Kandidat refit melihat A/B/C saat training, sehingga replay ini **in-sample**;
cadence 1 Hz juga bukan cadence edge asli. Hasilnya diagnosis kegagalan,
bukan bukti peningkatan maupun latency HP. Censoring membatasi interpretasi
alert baru per jam. Model demo v8 tidak diganti.

## Verifikasi dan langkah manusia

160 tes: 159 pass, satu skipped. 150 entri checksum arsip dan 100 hash
snapshot sumber cocok; bobot demo Keras/TFLite tidak berubah. Tidak ada
commit/push, deploy, atau event ke produksi pada pekerjaan ini.

Keputusan penggunaan, config, raw, bobot dan detail hasil tetap privat di
`SRASTA_LOCAL_CAPTURE/experiments/20261026_local_fall_v1` dan folder approval
di luar Git. D baru siap direkam; belum ada sesi validation. LOC_D dicadangkan
validation dan LOC_E test tanpa membuat rekaman. D harus diambil dan direview
sebelum validasi terpisah. E baru dibuka setelah keputusan final dibekukan.

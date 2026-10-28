# Pengembangan model dari capture lokal

## Keputusan penggunaan rekaman lama

Persetujuan penggunaan data yang diberikan tim setelah perekaman dicatat di
`SRASTA_LOCAL_CAPTURE/data_use_approvals/`, di luar Git. Keputusan ini berlaku
untuk pengembangan model lokal sekarang; tidak menyatakan prosedur telah
disetujui sebelum perekaman. Config, raw, event, review dan checksum asli tetap
utuh. Referensi persetujuan baru bukan pengganti referensi prosedur sesi baru.

`capture_governance.record_data_use_approval` mencatat pernyataan tim yang
benar-benar diberikan, waktu pencatatan saat ini, sumber, dan daftar sesi yang
terikat hash config, event dan manifest checksum. QA menerima referensi ini
sebagai alternatif provenance penggunaan; review independen, firmware, profil,
batas kualitas, kelengkapan dan integritas rekaman tetap diperiksa. Keputusan
dengan hash tidak cocok ditolak; keputusan revoked tidak menerima data.

## Koreksi peserta sebelum pemisahan data

Loader membaca sidecar `corrections/*participants*.json` dengan schema
`srasta.local.participant-correction.v1`. Koreksi terikat checksum arsip dan
identitas/split asli, serta tidak boleh mengubah split. Sesi fall 1–4, 5–8,
9–12 berasal dari A, B, C; enam percobaan presence dibagi dua per orang,
termasuk percobaan A kedua yang terputus dan tetap dikeluarkan QA.

ID efektif untuk pengelompokan adalah LOC_A/B/C. ID tersimpan LOC_001 tetap
dipakai untuk pemeriksaan integritas sumber. Empty mempunyai kelompok sesi
background tersendiri, tanpa diberi identitas orang A/B/C. Semua window dari
orang yang sama memakai kelompok yang sama. Koreksi bertentangan atau tidak
cocok dengan arsip menyebabkan proses berhenti.

## Eksperimen fall pertama

```bash
PYTHONPATH=code .venv/bin/python code/train_local_fall.py \
  --stage prepare --out ../SRASTA_LOCAL_CAPTURE/experiments/RUN_BARU
PYTHONPATH=code .venv/bin/python code/train_local_fall.py \
  --stage fit --out ../SRASTA_LOCAL_CAPTURE/experiments/RUN_BARU
```

Gunakan direktori baru; protokol dan hasil tidak ditimpa. Dataset hanya membaca
train accepted, memeriksa split sebelum payload, dan melewati test, validation
serta pilot. Tiap fall menghasilkan satu window aktual 500×52 yang berakhir
pada akhir kejadian; tidak ada padding atau pengulangan stillness. Negative
diambil seluruhnya di dalam interval nonfall yang direview. Gap packet dan
quarantine memutus riwayat. Preprocessing sama dengan shared edge module.

Protokol disimpan sebelum ekstraksi. Encoder v8 dibekukan; hanya head Dense
di-fine-tune delapan epoch, seed 42/43/44. Tiga fold siklik membagi A/B/C menjadi
orang fit, kalibrasi dan evaluasi yang berbeda. Threshold probabilitas dan
motion dipilih hanya pada orang kalibrasi. Empty tidak masuk fit/kalibrasi
antarorang. Baseline adalah v8 INT8 dengan threshold/motion tetap.

Laporan ini mengukur proxy klasifikasi window, bukan event recall, FAR per jam
atau latency notifikasi. Model kandidat tetap riset, termasuk setelah export
INT8/parity berhasil. Bobot demo tidak diganti. Data D/E tidak digunakan untuk
fit atau selection eksperimen ini. D diperlukan untuk validasi terpisah;
setelah keputusan model/preprocessing/threshold final dibekukan, E baru dibuka
untuk test. Kandidat yang memperbaiki satu metrik sambil menurunkan metrik lain
tidak dipromosikan.

## Pengambilan orang D berikutnya

D adalah orang baru, bukan A/B/C. Pada setiap form pilih **LOC_D**, split
**2 = validation**, dan lokasi/geometri sebenarnya. Jangan memakai default
LOC_001/train. Gunakan referensi prosedur yang benar-benar berlaku untuk sesi
baru dan pengamat yang menyaksikan kondisi.

```bash
bash scripts/collect_local_csi.sh --protocol presence --duration 600 --prepare 30
bash scripts/collect_local_csi.sh --protocol empty --duration 600 --prepare 30
bash scripts/collect_local_csi.sh --protocol fall-observer --prepare 30
```

Perintah dijalankan satu per satu oleh operator. Presence memuat aktivitas
harian nonfall; label ini tidak menyatakan sleep. Empty tetap kosong sepanjang
interval. Fall mengikuti prosedur aman tim dengan pengawasan dan empat tanda
aktual oleh pengamat, kemudian review independen. Bila aman sesuai prosedur,
rekam stillness pascakejadian setidaknya 10 detik agar evaluasi confirmation
memiliki bukti durasi; penghentian demi kondisi peserta selalu diutamakan.
Durasi fall tidak diatur oleh `--duration`. Jangan memperpanjang data secara
sintetis untuk memenuhi coverage. Jumlah dan variasi event mengikuti rencana
pengambilan yang ditetapkan sebelum melihat prediksi.

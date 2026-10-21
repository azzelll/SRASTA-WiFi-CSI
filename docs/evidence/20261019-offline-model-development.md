# Pengembangan model offline — 19 Oktober 2026

## Hasil dan keputusan

Pekerjaan ini menggunakan dataset yang sudah tersimpan. Tidak mengambil data
baru, mengakses Pi, mengubah deployment cloud, atau mengirim notifikasi.
Target fall recall dan specificity minimal 80% **belum tercapai**.

| Komponen | Hasil pengembangan | Keputusan |
| --- | --- | --- |
| Fall TCN-Lite v8 yang sudah digunakan | Recall 62,5%; specificity 64,9% pada 77 rekaman U19 | Pertahankan untuk demo |
| Kandidat fall fitur temporal + ExtraTrees | Recall 47,5%; specificity 89,2% pada U19 | Simpan sebagai ablation; terlalu banyak fall terlewat |
| Kandidat fall TCN normalisasi per channel, INT8 | Recall 52,5%; specificity 59,5% pada U19; parity lulus | Tidak mengganti v8 |
| Kandidat presence publik | Recall present 75,3%; specificity empty 75,3% | Kandidat riset baru; belum live ESP32 |
| Kandidat sleep/empty baru | Recall sleep 67,1%; recall empty 67,15% | Model lama 67,9%/67,9% tetap lebih baik |
| Kandidat `empty / sleep / normal` | Recall empty 57,0%; sleep 57,45%; normal proxy 98,41% | Prototipe tiga kelas terlatih; belum andal membedakan sleep/empty |

Semua angka di atas adalah klasifikasi **rekaman**, bukan recall event jatuh,
false alert per jam, atau performa ruangan pengguna. U19 serta validation
occupancy pernah diperiksa sebelumnya. Pemilihan kandidat dan cutoff pada
validation yang sama membuat angka pengembangan optimistis. Tidak ada test
independen baru dan test U21 tidak dibuka kembali dalam pekerjaan ini.

Presence lama memiliki recall 73,8% dan specificity 71,3%. Kandidat baru
memperbaiki angka pengembangan tersebut, tetapi recall khusus orang tidur
masih **50,6%**, sementara awake 100%. Skor gabungan 75,3% menutupi kelemahan
ini. Kedua model tetap belum tervalidasi pada CSI lokal ESP32.

## Audit label normal/awake

Metadata source-train memiliki:

- `BreathingDetection`: 37.880 rekaman sleep dan 32.116 empty; tidak ada
  label normal/awake di task tersebut.
- `HumanActivityRecognition`: 2.177 rekaman `seated-breathing`. Label ini
  digunakan sebagai **proxy aktivitas duduk terjaga**, bukan bukti kondisi
  fisiologis normal atau referensi jumlah napas.

[CSI-Bench, Appendix A.6 dan A.9](https://arxiv.org/html/2505.21866v2)
menjelaskan natural sleep dan aktivitas seated breathing sebagai pengambilan
data berbeda. Menganggap seated breathing sebagai proxy awake merupakan
asumsi eksperimen yang dinyatakan secara eksplisit.

Model tiga kelas mencampur sumber sleep/empty dengan sumber normal proxy:
ruangan, laju nominal, dan profil channel berbeda. Classifier diagnostik yang
hanya membaca metadata sumber sudah dapat mengenali normal proxy; nilai
98,41% tidak membuktikan kemampuan mengenali awake versus sleep di kamar baru.

Audit terbaru berada di
`artifacts/research/20261019-label-audit-final/label_audit.json`.
Nama perangkat mentah `EchoPlus` dan `Echoplus` memiliki beda kapitalisasi;
setelah casefold ada irisan `echoplus`. Karena itu hasil irisan nama mentah
yang kosong pada audit awal tidak boleh diartikan tidak ada keluarga hardware
yang sama. Kesamaan nama perangkat juga belum membuktikan domain capture sama.

## Protokol eksperimen

### Occupancy

- Hanya ID resmi **source-train** CSI-Bench yang digunakan; payload official
  validation/test tidak dibaca.
- Orang dipisahkan sebelum sampling/fit: breathing train U06, validation U23;
  HAR train U01/U03/U04/U06, validation U05. Tidak ada orang yang muncul pada
  kedua sisi, termasuk lintas task.
- Per stratum dibatasi 2.000 rekaman. Train: empty 2.000, sleep 1.999,
  awake 2.000, normal proxy 1.674. Validation: empty 2.000, sleep 2.000,
  awake 2.000, normal proxy 503. Satu payload sleep all-zero dikeluarkan.
- Sebanyak 13.353 payload unik di-hash dan tetap identik. Tidak ada payload
  duplikat identik lintas train/validation.
- 36 kandidat: tiga task × dua interpretasi storage × dua keluarga fitur ×
  RF/ExtraTrees/HistGradientBoosting. Sampling deterministik, seed 42.
- Channel asli dipertahankan untuk statistik native. Input 232 channel HP
  tidak masuk model fall ESP32 dan tidak dipaksa menjadi tensor 52 channel.
- `declared_axes` mengikuti axis sumber. `flat_time_major_ablation` adalah
  hipotesis interpretasi storage terpisah, **bukan koreksi axis yang sudah
  dibuktikan penulis dataset**. Kandidat presence dan tiga kelas terpilih
  memakai hipotesis kedua ini; generalisasi tetap belum terbukti.
- Cutoff binary serta bobot keputusan tiga kelas dipilih sesudah fit dari
  validation pengembangan yang sama. Ini bukan kalibrasi probabilitas.

Kandidat presence: temporal Random Forest, cutoff `0.47705607981343273`.
Confusion matrix `[empty, present]`: `[[1506,494],[988,3012]]`.

Kandidat tiga kelas: temporal HistGradientBoosting, bobot keputusan
`[1,2,0.125]` untuk `[empty,sleep,normal]`.
Confusion matrix: `[[1140,855,5],[725,1149,126],[0,8,495]]`.
Output menyimpan probabilitas mentah beserta aturan keputusan; bobot ini
tidak boleh ditampilkan sebagai confidence terkalibrasi.

### Fall

- Indeks utama tetap `data/curated/esp32_s3_fall_v1/manifest.csv`.
- Fit hanya 288 rekaman enam orang train; U19 merupakan development
  validation 77 rekaman. Test U21 tidak digunakan kembali untuk tuning.
- Fitur temporal: tiga keluarga classifier, tiga seed, enam outer fold.
  Setiap fold memisahkan orang fit, kalibrasi cutoff, dan evaluasi. Cutoff
  final dipilih dari prediksi train out-of-fold; U19 dipakai sesudah freeze.
- TCN: satu ablation normalisasi per current-window/channel, seed 42,
  enam fold train. Epoch final median best epoch fold. Representative INT8
  hanya dari primary train. Input tetap 500 × 52 pada 100 Hz nominal.
- TCN INT8 baru berukuran 50.592 byte. Parity FP32/INT8: MAE 0,01138,
  argmax agreement 96,10%. Lulus parity tidak berarti lulus target akurasi.

Fitur peak-location awal tidak stabil pada sinyal periodik karena puncak
dengan energi sama dapat bertukar akibat pembulatan. Uji regresi menemukannya;
fitur diganti energy centroid dan eksperimen temporal diulang. Folder
`20261019-occupancy-temporal-v1` dan `20261019-fall-temporal-v1` memiliki
`INVALIDATED.md` dan tidak boleh digunakan. Snapshot source setiap run tetap
disimpan untuk audit, termasuk audit nama perangkat yang kemudian diperjelas.

## Artefak lokal

Semua model dan hasil besar berada di folder ignored; tidak dipublikasikan.

| Folder di `artifacts/research/` | Isi |
| --- | --- |
| `20261019-label-audit-final/` | Audit label/metadata terbaru |
| `20261019-occupancy-temporal-v2/` | 36 kandidat, prediksi, source hashes dan snapshot kode |
| `20261019-occupancy-calibrated/` | Tiga model terpilih, cutoff/bias, metrics dan verifikasi |
| `20261019-fall-temporal-v2/` | Ablation fall fitur temporal |
| `20261019-channel-tcn-v1/` | Ablation fall TCN + export/parity INT8 |
| `20261019-integration-v1/` | Hasil replay aktual dan probe integrasi sintetis |

Runtime live menolak artifact riset occupancy/fall ini. Paket demo tetap
memakai fall v8 dengan SHA-256
`ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.

## Bukti software

- 105 test backend lulus, tanpa skip; 17 test web lulus; build web berhasil.
- 36 confusion matrix dihitung ulang dari prediksi tersimpan.
- Tiga model terpilih dimuat ulang dan diperiksa pada total **80 rekaman H5
  asli**. Probabilitas serta label cocok dengan hasil tersimpan.
- Seluruh 13.353 hash payload sumber tidak berubah; batas source-train dan
  pemisahan orang diperiksa ulang. Loader live menolak model riset.
- Replay fall v8 memakai rekaman **train** `U08_Fall_E22_1000`; empat route
  API memberi HTTP 200. Ini bukti jalur eksekusi model.
- Probe terisolasi membuktikan alur anomali → permintaan kamera → UID event
  → status critical setelah timer → acknowledge caregiver. Keputusan dan
  keypoint kamera pada probe ini **disuntikkan secara sintetis**.
- Replay/stale input diblokir dari capture; satu capture per UID dan payload
  summary tanpa gambar diperiksa. Adapter notifikasi eksternal dinonaktifkan.

Belum dibuktikan di sesi ini: CSI live pada Pi, kualitas klasifikasi kamera
asli, alert yang benar-benar terkirim, latensi ARM paket baru, atau akurasi
lokal. Kamera tetap menggunakan MoveNet pretrained yang sudah ada.

## Menjalankan ulang

Jalankan dari root repository dengan environment training yang sudah ada.
Pakai nama output baru; script menolak menimpa hasil.

```bash
PYTHONPATH=code .venv/bin/python code/train_offline_candidates.py \
  --task audit --out-dir artifacts/research/YOUR_LABEL_AUDIT
PYTHONPATH=code .venv/bin/python code/train_offline_candidates.py \
  --task occupancy --out-dir artifacts/research/YOUR_OCCUPANCY_RUN
PYTHONPATH=code .venv/bin/python code/calibrate_offline_candidates.py \
  --run artifacts/research/YOUR_OCCUPANCY_RUN \
  --out-dir artifacts/research/YOUR_CALIBRATED_RUN
PYTHONPATH=code .venv/bin/python code/verify_offline_experiment.py \
  --run artifacts/research/YOUR_OCCUPANCY_RUN \
  --calibrated artifacts/research/YOUR_CALIBRATED_RUN \
  --output artifacts/research/YOUR_CALIBRATED_RUN/verification.json
PYTHONPATH=code .venv/bin/python code/train_offline_candidates.py \
  --task fall --out-dir artifacts/research/YOUR_FALL_RUN
PYTHONPATH=code .venv/bin/python code/train_channel_tcn.py \
  --out-dir artifacts/research/YOUR_TCN_RUN
```

Panduan paket: [paket Pi offline](../pi-offline-package.md).

## Langkah yang memerlukan perangkat/data baru

1. Saat Pi/RX/TX dinyalakan kembali: verifikasi RX UART dan capture profile,
   laju paket, CSI → model → dashboard → event kamera → acknowledge pada
   aktivitas biasa. Paket baru belum dikirim ke Pi.
2. Untuk presence dan tiga kelas live: data lokal empty, awake duduk/berbaring,
   aktivitas biasa, dan tidur alami dengan label pengamat serta split sesi/orang.
3. Untuk kualitas fall: evaluasi event lokal beranotasi dan negative exposure
   untuk false alert per jam, dengan test yang ditahan dari tuning.

Tidak perlu melakukan jatuh untuk membuktikan koneksi atau alur software.
Model saat ini belum dapat dipakai sebagai bukti sistem keselamatan andal.

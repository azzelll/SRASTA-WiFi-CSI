# Training sleep/empty dan presence dari dataset yang sudah ada

Tanggal: 3 Oktober 2026. Permintaan: latih dua classifier menggunakan corpus
lokal yang tersedia, tanpa mengambil rekaman baru. Fall tetap memakai v8.

## Data dan batas pemakaian

- `BreathingDetection`: label asli `empty` dan `sleep`.
- Presence: `empty` menjadi kosong; `sleep` dan lima aktivitas manusia di
  `HumanActivityRecognition` menjadi `present`. Presence mencakup contoh
  manusia tidur dan terjaga; tidak sekadar mengganti nama output sleep.
- Label HAR tidak dijadikan label sleep atau kelas breathing `normal`.
- Filter official **source-train IDs dilakukan sebelum membuka H5**. Custom
  train/validation dibagi per orang, sebelum sampling. Official validation/
  test dan rekaman lokal ESP32 tidak dibaca dalam pekerjaan ini.
- Train breathing U06; validation U23. Train HAR U01/U03/U04/U06; validation
  U05. Tidak ada orang yang muncul di kedua partition, termasuk antarcorpus.
- Metadata-only sampling: round-robin device, native shape, placement, dan
  label; maksimal 2.000 per stratum. Semua jumlah di bawah adalah rekaman,
  bukan window hasil pemecahan yang dianggap orang independen.
- Satu H5 berlabel sleep seluruhnya nol ditolak dengan ID dan label asal
  tersimpan. Tidak diubah menjadi contoh kosong. 12.000 H5 yang dibaca
  memiliki SHA256 sama sebelum/sesudah pekerjaan; tidak ada duplicate byte
  di antara partition yang eligible.

| Stratum | Train eligible | Development validation |
| --- | ---: | ---: |
| Empty | 2.000 | 2.000 |
| Sleep | 1.999 | 2.000 |
| Awake HAR (presence saja) | 2.000 | 2.000 |

Breathing sumber memakai perangkat IoT 5 GHz dan nominal 30 Hz, bukan
ESP32-S3 lokal 2,4 GHz. HAR memakai nominal 100 Hz dengan native channels
56/232. Amplitudo tidak dipad, diresize, atau dipotong menjadi 52 carrier.
Rujukan: [CSI-Bench, Appendix A.6](https://arxiv.org/html/2505.21866v2).

## Eksperimen dan layout

Enam kandidat per task: dua interpretasi storage × legacy Random Forest,
gain-invariant Random Forest, dan gain-invariant RBF SVM. Seed 42; 300 pohon,
minimum leaf 5; SVM C=1. Shared feature extractor dipakai training/inference.

`declared_axes` memakai transpose `[channels,time,1]` seperti baseline lama
dan [loader sumber](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark/blob/main/load/supervised/benchmark_dataset.py).
`flat_time_major_ablation` merekonstruksi urutan flattened pada **jumlah
channel asal**. Dalam contoh U06, alternatif ini memulihkan 48 posisi nol
tetap dalam empat blok 64 serta mengurangi variasi temporal yang menyerupai
bentuk kanal. Ini bukti pendukung **hipotesis layout**, belum konfirmasi
pembuat dataset; tidak dinyatakan sebagai perbaikan resmi corpus.

Legacy memakai 24 statistik temporal/spektral; invariant memakai normalisasi
gain per channel dan 43 statistik, termasuk autocorrelation dan spektrum
agregat. Indeks channel hidup hanya menjadi mask statistik, bukan remapping
ke carrier ESP32. Classifier mendapat fitur CSI, tanpa ID orang/device/
ruangan, nama file, atau label sumber sebagai input.

## Hasil

Model dan laporan awal dengan cutoff 0,5 disimpan utuh. Balanced accuracy
terbaik dengan cutoff itu: breathing **62,525%**, presence **54,575%**.
Kalibrasi berikutnya memeriksa semua probability boundaries pada development
validation, memilih minimum recall kedua kelas, lalu balanced accuracy.
Bobot tidak dilatih ulang. **Kandidat dan cutoff dipilih pada data yang sama
dengan skor berikut: hasil pengembangan yang optimistis, bukan final test.**
Subjek validation juga pernah dilihat pada eksperimen sebelumnya.

| Task | Kandidat setelah kalibrasi | Recall kelas positif | Recall empty / specificity | Balanced accuracy |
| --- | --- | ---: | ---: | ---: |
| Sleep/empty | Flat-layout ablation, legacy RF; cutoff 0,3188607544 | Sleep 67,9% | 67,9% | 67,9% |
| Presence | Declared axes, invariant RF; cutoff 0,9661123582 | Present 73,8% | 71,3% | 72,55% |

Confusion matrices (baris true, kolom predicted; empty dahulu):

- Breathing: `[[1358,642],[642,1358]]`; 4.000 rekaman validation.
- Presence: `[[1426,574],[1048,2952]]`; 6.000 rekaman validation.

Presence recall menurut kondisi: **sleep 47,7%**, **awake HAR 99,9%**.
Recall gabungan 73,8% tidak berarti orang tidur terdeteksi sebaik orang yang
terjaga. Corpus/device dan label masih berpotensi menjadi shortcut.

Kedua classifier telah dilatih dan disimpan, serta bisa menjalankan inferensi
rekaman asli melalui CLI. Target 80% untuk kedua kelas belum tercapai.
Keduanya tetap `research_only`, `local_deployment_ready=false`; angka di atas
tidak membuktikan akurasi presence/sleep pada RX lokal. Kelas breathing
`normal/awake`, angka napas, apnea, dan sleep staging tidak dibuktikan.
Adapter native terpisah dari `PresenceInference`; model publik ini ditolak
jika dimasukkan sebagai model presence lokal yang telah direview.

## Verifikasi software

- 93 tests backend lulus, tanpa failure/error/skip. Enam test baru memeriksa
  batas source-train, pemisahan orang antarcorpus, layout native tanpa resize,
  invariansi gain/urutan channel, inferensi artifact, dan boundary kalibrasi.
- Confusion matrix 12 kandidat dihitung ulang dari prediksi tersimpan;
  cutoff dan confusion matrix kedua model terkalibrasi juga cocok.
- 30 inferensi validation dari artifact yang dimuat ulang menghasilkan
  probabilitas yang sama dengan prediksi training. CLI diuji pada rekaman
  empty, sleep, dan awake yang dipilih sebelum melihat outputnya.
  Contoh sleep pertama diprediksi empty; pemeriksaan ini membuktikan jalur
  inferensi/serialization, tidak membuktikan semua contoh diklasifikasi benar.
- Hash indeks sumber dan 12.000 payload tetap sama. Hash model fall v8
  tetap `ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.
- Artifact model tetap diabaikan Git. Tidak ada flash, penggunaan serial,
  pengubahan label capture lokal, pemasangan model live, atau deploy app.

## Artifact lokal (ignored)

- `artifacts/research/20261003-public-occupancy-v3/`: protocol, metadata
  eligible/excluded, layout audit, 12 kandidat, prediksi validation, metrics,
  serta hash sumber sebelum/sesudah. Percobaan v2 berhenti pada rekaman nol;
  tidak mempunyai hasil training yang selesai.
- `artifacts/research/20261003-public-occupancy-calibrated/`: dua
  `breathing/model.joblib` dan `presence/model.joblib`, metrics kalibrasi,
  serta `verification.json`. Model awal tidak ditimpa.

## Menjalankan ulang

Dari root repository, pilih folder output baru:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
  .venv/bin/python code/train_public_occupancy.py \
  --out-dir artifacts/research/new-public-occupancy --cap-per-stratum 2000

.venv/bin/python code/calibrate_public_occupancy.py \
  --run artifacts/research/new-public-occupancy \
  --out-dir artifacts/research/new-public-occupancy-calibrated

.venv/bin/python code/predict_public_occupancy.py \
  --model artifacts/research/20261003-public-occupancy-calibrated/breathing/model.joblib \
  --recording-id RECORDING_ID_FROM_ELIGIBLE_METADATA
```

Untuk presence, gunakan `presence/model.joblib`; tambahkan
`--task HumanActivityRecognition` jika memilih ID HAR. CLI mengeluarkan
prediksi, probabilitas, threshold, label sumber, dan provenance penelitian.
TX/RX tidak diperlukan untuk training atau inferensi H5 ini.

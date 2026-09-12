# Perbandingan model — 11 September 2026

Seluruh angka berikut merupakan proxy satu window per rekaman pada U19 (40 fall, 37 nonfall), bukan event-level atau hasil test final. U21 tetap tidak dibaca. Model alternatif serta threshold dipilih dengan leave-one-subject-out pada enam subjek train; hasil validation semua kandidat dilaporkan, termasuk yang buruk. Melihat beberapa eksperimen pada U19 menjadikannya validation untuk pengembangan, bukan evaluasi akhir.

| Eksperimen | Model | Recall fall | Specificity | Macro F1 | Pilihan CV train |
|---|---|---:|---:|---:|---|
| rf-v2-20260911 | RF baseline | 0.800 | 0.378 | 0.574 | — |
| tcn-v2-20260911 | TCN INT8 | 0.250 | 0.892 | 0.515 | — |
| alternatives-v1-20260911 | extra_trees_leaf2 | 0.650 | 0.568 | 0.609 | — |
| alternatives-v1-20260911 | extra_trees_leaf5 | 0.525 | 0.676 | 0.596 | — |
| alternatives-v1-20260911 | random_forest_leaf2 | 0.625 | 0.649 | 0.636 | — |
| alternatives-v1-20260911 | random_forest_leaf5 | 0.575 | 0.595 | 0.584 | — |
| alternatives-v1-20260911 | svm_rbf_c03 | 0.400 | 0.784 | 0.572 | — |
| alternatives-v1-20260911 | svm_rbf_c3 | 0.600 | 0.541 | 0.570 | — |
| alternatives-v1-20260911 | svm_rbf_c30 | 0.700 | 0.486 | 0.590 | — |
| alternatives-v1-20260911 | logistic_c03 | 0.525 | 0.514 | 0.519 | Ya |
| alternatives-v1-20260911 | hist_gradient_boosting | 0.600 | 0.541 | 0.570 | — |
| alternatives-500-20260911 | extra_trees_leaf2 | 0.750 | 0.568 | 0.658 | — |
| alternatives-500-20260911 | extra_trees_leaf5 | 0.700 | 0.595 | 0.647 | — |
| alternatives-500-20260911 | random_forest_leaf2 | 0.675 | 0.622 | 0.648 | — |
| alternatives-500-20260911 | random_forest_leaf5 | 0.650 | 0.811 | 0.727 | — |
| alternatives-500-20260911 | svm_rbf_c03 | 0.525 | 0.784 | 0.646 | — |
| alternatives-500-20260911 | svm_rbf_c3 | 0.550 | 0.595 | 0.571 | Ya |
| alternatives-500-20260911 | svm_rbf_c30 | 0.600 | 0.514 | 0.557 | — |
| alternatives-500-20260911 | logistic_c03 | 0.575 | 0.595 | 0.584 | — |
| alternatives-500-20260911 | hist_gradient_boosting | 0.625 | 0.595 | 0.610 | — |

Tidak ada hasil di atas yang memenuhi recall fall >=0.88 dan specificity >=0.80 sekaligus. Kandidat tidak diaktifkan sebagai model terverifikasi pada hotspot. Hasil ini tidak membuktikan bahwa jumlah model yang lebih banyak dengan sendirinya menyelesaikan domain shift.

Fitur alternatif tetap menerima amplitude [T,52] hasil preprocessing bersama. Statistik temporal/spektral merangkum jendela 250 atau 500 frame; tidak mengubah mask fitur CSI. Model SVM memakai skor sigmoid margin yang belum dikalibrasi; seluruh UI menyebutnya skor model belum tervalidasi.

Metode pemisahan kelompok dan transformasi hanya pada data training mengikuti [dokumentasi scikit-learn](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data). Artefak lokal dan hasil per-fold ada di `artifacts/*/metrics.json`.

## Data tambahan dan transfer learning

Sumber resmi [ESP-Fi HAR / AutoSmartGroup](https://github.com/AutoSmartGroup/ESP-Fi-HAR), commit `c8bf6aa0d680fa02695c85a82b05e79b3ebb10c4`, berlisensi dataset CC BY 4.0 (Wen et al., 2026, Ad Hoc Networks 186:104192). Diunduh 490 MAT source-train, 70 per kelas, dengan ukuran/hash Git diverifikasi. Source-test tidak diunduh. Format `[950,52]` adalah amplitude ESP32-C3; bukan frame raw SRASTA ESP32-S3. Label memakai folder aktivitas karena contoh pemetaan ID aktivitas pada README berbeda dari nama file.

Percobaan menggunakan encoder TCN bersama, head tujuh aktivitas pada source-train (420 fit, 70 holdout subject 8), lalu membuang head sumber dan melatih head binary pada train SRASTA. Input temporal 500 frame memakai grid nominal; metadata paket fisik tidak tersedia. Seluruh provenance ada di `artifacts/tcn-transfer-20260911/pretraining_provenance.json`.

Hasil transfer FP32 pada U19: recall fall **0.925**, specificity **0.081**, macro F1 **0.403**. Recall tinggi itu disertai 34 false positives dari 37 nonfall; tidak memenuhi kualitas yang diminta. INT8 kolaps ke nonfall: recall fall 0, specificity 1.0, parity argmax hanya 0.078. Kalibrasi ulang memakai seluruh 288 primary-train (kedua kelas dan semua subjek) tetap gagal; artefak gagal dipertahankan sebagai bukti, tidak dipakai live. Loader runtime sekarang menolak kandidat TFLite yang parity-nya gagal atau hilang.

WiFall juga diperiksa dari [kartu sumber](https://huggingface.co/datasets/RS2002/WiFall/blob/main/README.md). Format raw 104 byte, lisensi data dan event onset tidak terverifikasi. Tidak mengubah payloadnya menjadi kontrak 128 byte, tidak melabel setiap window sebagai fall, dan tidak menambahkannya ke evaluasi SRASTA. Belum digunakan dalam eksperimen sesi ini.

Pengunduh dapat diulang lewat `code/tools/fetch_esp_fi_har.py` (resume hanya file yang hilang, sumber yang ada diverifikasi, manifest final tidak ditimpa). Untuk percobaan baru, jalankan `train_srasta_tcn_lite.py` dengan `--pretrain-esp-fi data/external/esp_fi_har --window-length 500` dan output directory baru. Temuan ini membuktikan perlunya validasi domain lokal; mengganti model/data saja belum menghasilkan detektor yang bagus pada held-out subject.

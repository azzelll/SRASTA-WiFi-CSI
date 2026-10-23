# Data dan model yang tersedia untuk melanjutkan

Handoff 21 Oktober menyertakan **metadata indeks dan selected model snapshots**,
bukan raw corpus. Model, metrics dan config yang disertakan tercantum di
`HANDOFF_ASSETS.json`. Path eksperimen di dalam laporan adalah provenance lama;
tidak semua run/dependency/raw payload tersedia setelah clone.

| Sumber | Bentuk dan peran | Ketersediaan / batas |
| --- | --- | --- |
| CSI-Bench ESP32-S3 fall | H5 `[64,time,1]`, 52 usable centered amplitudes; sumber fall utama | Indeks/split curated ikut Git, raw lokal saja; perlakukan sebagai riset CC BY-NC-ND sesuai panduan repo |
| CSI-Bench BreathingDetection / HAR | Native layout sumber untuk empty/sleep dan presence; HAR tertentu proxy normal | Selected occupancy weights/reports ikut Git; bukan bukti napas per menit atau live RX lokal |
| ESP-Fi HAR, Wen et al. (2026) | ESP32-C3 amplitude `[950,52]`, supervised pretraining/ablation | CC BY 4.0 dengan atribusi; hardware berbeda, jangan masuk primary test |
| WiFall, RS2002 | ESP32-S3 104 I/Q bytes, 52 complex values, file kontinu | Kartu sumber tanpa license yang jelas saat audit; raw tetap lokal/research, bukan label fall untuk setiap window |
| SRASTA local | 128-byte I/Q JSONL, capture hash, human events/reviews | Transfer privat beserta registry/checksum; pending/rejected tidak boleh dijadikan accepted otomatis |
| Google MoveNet Lightning INT8 v4 | Image -> 17 COCO17 joints; bukan fall classifier | Selected official TFLite ikut Git dengan model card + Apache-2.0 license; foto/video tidak ikut |

Sumber/provenance utama:

- [CSI-Bench paper](https://arxiv.org/abs/2505.21866) dan
  [CSI-Bench repository](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark).
- [ESP-Fi HAR](https://github.com/AutoSmartGroup/ESP-Fi-HAR),
  [paper Wen et al.](https://doi.org/10.1016/j.adhoc.2026.104192).
- [WiFall dataset card](https://huggingface.co/datasets/RS2002/WiFall),
  [paper](https://arxiv.org/abs/2412.04783).
- [Google MoveNet model card](https://www.kaggle.com/models/google/movenet/tensorFlow2/singlepose-lightning/4),
  [official tutorial / TFLite URL](https://www.tensorflow.org/hub/tutorials/movenet).

Untuk corpus lama yang belum ada di mesin teman, minta inventaris/checksum dan
cara akses yang sah kepada pemilik. Jangan menjanjikan raw sudah di Git dan
jangan otomatis mengunggah ulang dataset. `code/tools` mempunyai pengindeks dan
tool pemrosesan; baca provenance, batas source-train dan license sebelum
download/pretraining. Split sebelum windowing. Public source test tidak
berubah menjadi test final SRASTA. Pengukuran asli lokal tetap diperlukan.

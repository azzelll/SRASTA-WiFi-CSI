# Model SRASTA untuk integrasi

## Pembaruan 19 Oktober 2026

Fall v8 tetap dipakai untuk demo setelah kandidat temporal dan normalisasi
per channel belum mengunggulinya. Kandidat presence baru memperoleh recall
75,3% dan specificity 75,3% pada validation pengembangan publik, dengan recall
sleep hanya 50,6%. Model `empty/sleep/normal` sudah terlatih, tetapi normal
masih proxy `seated-breathing` lintas task dan sleep/empty belum andal.
Model baru belum dipasang pada CSI live. Target 80%/80% belum terpenuhi.

Lihat [hasil lengkap, protokol dan verifikasi](docs/evidence/20261019-offline-model-development.md)
serta [paket lokal Pi](docs/pi-offline-package.md).

## Paket lokal saat ini

Default `scripts/run_local.sh` sekarang memakai
`artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/`.
Paket berisi TCN-Lite INT8, model FP32, config preprocessing/capture,
provenance, threshold yang dibekukan, metrics, dan laporan kalibrasi trigger.
Folder ini di-ignore dan tidak diunggah ke cloud.

Bobot classifier tetap berasal dari v2. Eksperimen v4–v7 belum menghasilkan
classifier yang lebih baik; perubahan v8 memperbaiki gate gerakan yang
sebelumnya menahan seluruh window train/validation.

| Pemeriksaan | Hasil |
| --- | --- |
| Input | 500 frame × 52 amplitudo; mask posisi tetap |
| INT8 input/output | Lulus |
| Ukuran | 65.592 byte |
| Validasi subjek U19, 77 rekaman | Recall fall 62,5%; specificity 64,9%; macro F1 0,636 |
| Parity FP32/INT8 | MAE 0,00295; agreement 98,7% |
| Waktu inferensi Mac, validasi | Rata-rata 0,192 ms; bukan pengukuran Raspberry Pi |
| Threshold fall | 0,45; dimuat runtime dari paket |
| Test classifier v2 U21, 80 rekaman, sekali setelah freeze | Recall fall 62,5%; specificity 47,5%; macro F1 0,547; bukan evaluasi trigger v8 |
| SHA-256 | `ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66` |

**Siap untuk integrasi software/pengujian; belum memenuhi target deteksi.**
Recall ≥88% dan specificity ≥80% belum tercapai. Angka di atas adalah proxy
label rekaman; bukan event recall, false alert per hari, atau bukti klinis.
Test U21 sudah digunakan untuk laporan classifier v2 dan tidak boleh dipakai
untuk memilih perubahan berikutnya. V8 tidak membuka ulang test tersebut.

## Trigger gerakan v8

- Threshold lama `0.02` berada di atas energi semua window train/validation;
  proxy trigger + classifier menghasilkan recall fall 0%.
- Threshold baru `0.0003443831083131954` ditetapkan dari persentil 1 energi
  window fall pada **train saja**, dengan cakupan train 98,8%. Threshold fall
  classifier tetap `0.45`.
- Proxy trigger + classifier pada validation U19: recall fall 62,5%,
  specificity 64,9%. State machine dibuat baru untuk setiap window; ini belum
  mengukur event onset, false alerts per jam, atau ketahanan pada kamar lokal.
- Replay integrasi satu rekaman fall train U08 memunculkan `suspected_fall`
  dengan input `[1,500,52]`. Ini bukti jalur runtime, bukan hasil held-out.
- Hash preprocessing dan capture dikunci dalam `frozen_release.json`.
  Runtime menolak perubahan config meskipun hash internal config dihitung ulang.

Gate baru harus diperiksa pada CSI asli dengan aktivitas biasa. Pengukuran
negative exposure diperlukan untuk mengetahui false alert lokal.

## Eksperimen dan perbaikan numerik

- v1: dua panjang window (250/500), normalisasi affine tambahan. INT8 parity
  gagal; tidak dipakai runtime.
- Diagnosis menemukan baseline awal mendekati nol menghasilkan nilai hingga
  862,8 dan skala INT8 besar yang menghilangkan variasi kecil.
- v2: shared causal preprocessing dengan batas normalisasi ±2 dan tanpa
  affine tambahan pada model. Bentuk/mask I/Q dan timestamp tidak diubah.
  Hash konfigurasi artifact lama tetap sama ketika opsi batas tidak aktif.
- v3: pretraining encoder dari 490 rekaman ESP-Fi source-train, tujuh
  aktivitas, 30 epoch; temporary head dibuang, fine-tune dan INT8 representative
  hanya memakai primary train. Recall validasi 55%, specificity 54,1%; tidak
  dipilih. Sumber ESP32-C3 berbeda domain; Wen et al. (2026), CC BY 4.0.

- v4: history Hampel dari input mentah, menghindari baseline yang terkunci
  setelah perubahan level; recall terbaik 52,5%, specificity 64,9%, parity gagal.
- v5: log-difference dan encoder lebih lebar; recall terbaik 57,5%,
  specificity 48,6%, parity gagal.
- v6: standardisasi yang diadaptasi hanya dari train; recall terbaik 60%,
  specificity 51,4%, parity gagal.
- v7: pooling temporal tersegmentasi; kandidat 250-frame lulus parity tetapi
  recall 52,5%/specificity 48,6%; kandidat 500-frame gagal parity. Tidak dipilih.

Opsi history mentah dan log-difference tersedia untuk retraining berikutnya.
V8 mempertahankan preprocessing v2 agar sesuai dengan bobotnya. Mengubah
preprocessing pada runtime tanpa retraining ditolak. Banyak pemilihan memakai
validation yang sama meningkatkan risiko overfit; dibutuhkan test lokal baru.

Pemilihan memakai train/validation yang terpisah per subjek. Test tidak dibuka
saat pemilihan. Pretraining tidak memberi label keberadaan/inaktivitas pada
data ESP32-S3 dan tidak membuktikan model produk empat kelas.

## Reproduksi

```bash
PYTHONPATH=code .venv/bin/python code/train_srasta_release.py \
  --out-dir artifacts/releases/YOUR_NEW_RUN --epochs 60

# Ablation encoder eksternal; source test tetap tidak dibaca.
PYTHONPATH=code .venv/bin/python code/train_srasta_release.py \
  --out-dir artifacts/releases/YOUR_NEW_ABLATION --epochs 60 --pretrain-esp-fi

# Kalibrasi motion gate, tanpa retraining atau membaca test.
PYTHONPATH=code .venv/bin/python code/calibrate_motion_gate.py \
  --source artifacts/releases/20261001-tcn-v2/selected \
  --out-dir artifacts/releases/YOUR_MOTION_CALIBRATION
```

Jangan menjalankan `--evaluate-frozen` lagi pada test U21 untuk tuning.
Kode menolak menimpa output dan menolak release bila semua kandidat gagal
parity. Runtime memverifikasi SHA-256 release, window, dan threshold.

## Data yang masih diperlukan

Requirement produk tetap empat keluaran: `no_person`, `normal`, `inactive`,
dan anomali jatuh. Data primary sekarang hanya memiliki label fall/nonfall.
Jangan mengarang `no_person` dari tensor nol atau `inactive` dari nonfall.
Kumpulkan interval ruangan kosong, aktivitas biasa, diam/inaktivitas, dan
event dengan anotasi yang dapat dipertanggungjawabkan sesuai
`docs/esp32_s3_capture_protocol.md`. Pisahkan subjek/sesi/ruangan sebelum
windowing dan sisihkan test lokal baru. Pengambilan data jatuh hanya dalam
protokol terkontrol; pengujian aliran USB/dashboard tidak memerlukan jatuh.

Gate berikutnya: capture profile/laju paket lokal, model empat kelas,
event-level recall/precision/FAR, breathing MAE, kamera/fusion, dan latensi Pi.

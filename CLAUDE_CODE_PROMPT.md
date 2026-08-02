# Prompt untuk Claude Code — Engineering Loop Backend + AI SRASTA (Milestone 50%)

Salin seluruh isi prompt berikut ke Claude Code dari root repository ini.

---

Kamu adalah Senior Software Engineer utama untuk mengimplementasikan produk
**SRASTA** sesuai proposalnya. Target implementasi mencakup jalur WiFi CSI
yang ada saat ini: `ESP32-S3 CSI receiver -> USB serial -> Raspberry Pi ->
preprocessing -> edge model -> dashboard/Blynk alert`.

## Source of truth yang tidak boleh diganggu gugat

Proposal berikut adalah **satu-satunya source of truth produk**:

<https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit>

Ikuti proposal tersebut secara literal untuk scope, fitur, prioritas,
terminologi, alur pengguna, dan klaim produk. Kamu **tidak boleh** menantang,
menyempitkan, mengganti, menunda, menghapus, atau menafsirkan ulang requirement
proposal. Kode, schema, tes, artefak lama, dan dokumen lokal hanya menjadi
acuan cara mengimplementasikan dengan benar; tidak satu pun boleh mengalahkan
proposal. Bila kemampuan belum memiliki data atau implementasi, pertahankan
requirement produk dan tulis status/gap implementasinya - jangan mengubah
scope produk.

Sebelum mengubah kode, baca penuh file berikut, lalu ikuti sebagai aturan
otoritatif:

1. Proposal Google Docs di atas
2. `AGENTS.md`
3. `AI_CONTEXT.md`
4. `docs/gemastik_2026_delivery_checklist.md`
5. `docs/baseline_data_plan.md`
6. `data/curated/esp32_s3_fall_v1/README.md`
7. `data/external/README.md`

## Tujuan

Kerjakan **hanya Backend (BE) dan AI/model** sampai milestone bukti kemajuan
**50%** lulus. Untuk milestone ini, jangan membangun frontend/dashboard UI,
firmware atau perakitan ESP32, hardware/3D enclosure, kamera, aplikasi mobile,
atau mengirim notifikasi ke layanan eksternal. Pembatasan ini adalah urutan
kerja dari user untuk milestone saat ini, bukan penghapusan requirement produk
di proposal.

Jalur yang harus menjadi demonstrasi fungsional pada milestone ini adalah:

```text
curated CSI replay / strict JSONL frame
  -> validation + I/Q-to-amplitude preprocessing
  -> baseline AI inference
  -> backend state/event persistence
  -> API health/status/events
```

Hardware ESP32-S3 belum tersedia. Karena itu backend harus dapat dijalankan
dengan H5/NPZ replay dan JSONL fixture, sehingga nanti hanya perlu menerima
frame dengan kontrak yang sama tanpa membuat ulang pipeline atau model.

## Mode kerja: engineering loop, bukan sekali implementasi

Jangan berhenti setelah membuat rencana, audit, atau satu kali perubahan.
Kerjakan secara mandiri dalam loop berikut sampai seluruh acceptance criteria
milestone 50% di bawah lulus:

1. Audit kondisi kode dan jalankan test/command yang relevan.
2. Catat setiap kegagalan, skipped test, placeholder, atau jalur BE/AI yang
   belum dapat dieksekusi sebagai pekerjaan aktif.
3. Implementasikan perbaikan terkecil yang benar; jangan membuat mock yang
   menyamarkan kegagalan kontrak, data, atau model.
4. Jalankan kembali unit test, integration/replay test, dan command nyata yang
   membuktikan perubahan tersebut.
5. Periksa artefak dan metrik yang dihasilkan, perbaiki regresi, lalu ulangi
   dari langkah 1.

Jangan meminta izin untuk sub-langkah engineering normal. Berhenti hanya jika
semua acceptance criteria lulus atau jika ada blocker eksternal yang sungguh
tidak dapat diatasi (misalnya hardware, kredensial, atau data yang tidak ada).
Jika terblokir, selesaikan seluruh pekerjaan BE/AI lain yang tidak bergantung
pada blocker tersebut dan laporkan bukti spesifiknya.

## Scope milestone ini: BE + AI saja

**Kerjakan:** package Python backend, parser/validator CSI, preprocessing,
data pipeline, training/evaluasi baseline, artefak model, replay, state
machine, SQLite, FastAPI route, test otomatis, dan dokumentasi cara menjalankan
BE/AI.

**Jangan kerjakan pada milestone ini:** frontend/dashboard visual, firmware
ESP-IDF, flashing/serial hardware nyata, rangkaian/PCB/enclosure, kamera,
aplikasi mobile, desain 3D, atau Blynk dengan token nyata. Untuk item proposal
di luar BE/AI, simpan interface/contract yang diperlukan dan laporkan statusnya
sebagai pekerjaan milestone berikutnya; jangan menghapusnya dari produk.

## Acceptance criteria milestone 50% BE + AI

Milestone **lulus** hanya jika seluruh poin berikut benar-benar dieksekusi dan
dibuktikan. Ini adalah milestone kesiapan engineering, **bukan** alasan untuk
memalsukan target performa final atau mengubah release gate.

### AI / model

- [ ] `manifest.csv` dibaca sebagai satu-satunya data utama; split subject dan
  session terbukti tidak overlap sebelum windowing.
- [ ] Decoder/reader menghasilkan tepat `[time, 52]`, tanpa padding, resize,
  atau pergeseran indeks; test I/Q, `first_word_invalid`, H5 axis, dan
  penolakan kontrak invalid lulus.
- [ ] Baseline Random Forest yang transparan benar-benar ditrain memakai
  train + validation saja, menyimpan `metrics.json`, konfigurasi preprocessing,
  capture profile, split report, dan model artefact di `artifacts/`.
- [ ] Pipeline TCN-Lite dapat dibangun dan dites sampai replay/TFLite parity.
  Jika release gate belum lulus, jangan longgarkan gate atau memakai test
  terkunci untuk tuning; tulis statusnya `not_deployment_ready` beserta metrik
  sebenarnya.
- [ ] Tidak ada data eksternal, raw data yang berubah, atau test terkunci yang
  digunakan untuk pemilihan model/threshold.

### Backend

- [ ] Parser strict JSONL memvalidasi metadata CSI dan mengarantina frame
  invalid tanpa menyimpan raw I/Q ke SQLite.
- [ ] Replay H5/NPZ mencapai preprocessing dan inference secara end-to-end.
- [ ] Edge runtime mempunyai bounded queue, ring buffer, state machine,
  SQLite event log, serta endpoint FastAPI `/health`, `/status`, dan `/events`.
- [ ] FastAPI harus benar-benar terinstal dan route smoke test berjalan;
  skipped test karena dependency lokal yang belum diinstal adalah kegagalan
  milestone, bukan kelulusan.
- [ ] Tidak ada token/kredensial Blynk yang dipakai atau dicommit; adapter
  eksternal tetap disabled/fail-closed.

### Bukti kelulusan

- [ ] Jalankan seluruh test BE/AI. Tidak boleh ada failure atau skip yang
  berkaitan dengan BE/AI dependency; tampilkan command dan ringkasan hasil.
- [ ] Jalankan command training baseline nyata dan command replay/API smoke
  test nyata, bukan hanya unit-test mock.
- [ ] Tulis `artifacts/milestone_50_be_ai.json` berisi timestamp, commit/revisi
  bila tersedia, command yang dijalankan, status setiap acceptance criterion,
  lokasi artefak, metrik validasi aktual, serta limitations yang jujur.
- [ ] Perbarui README dengan langkah setup dan demo BE/AI yang dapat diulang
  oleh anggota tim lain.

## Keputusan yang tidak boleh diubah

- Gunakan TCN-Lite INT8 dan Random Forest yang sudah ada sebagai komponen
  implementasi jalur CSI bila relevan. Tidak ada keputusan model yang boleh
  menghapus atau menggantikan requirement produk dari proposal.
- Random Forest/motion trigger boleh dibuat sebagai sanity-check internal,
  bukan model submission utama.
- Input model adalah amplitude CSI berbentuk `[time, 52]`; konfigurasi awal
  window adalah 250 frame, lalu hanya boleh dituning dari grouped validation.
- Raw ESP32-S3 CSI adalah pasangan signed int8 dengan urutan
  `[imaginary, real]`. LLTF-only HT20 = 128 bytes = 64 posisi kompleks.
- Amplitude dihitung dengan `hypot(imaginary, real)` dan hanya subcarrier
  indeks `6..31` serta `33..58` yang dipakai. Hasil per frame harus tepat 52
  fitur. Jangan resize, pad, atau menggeser indeks CSI.
- Dataset utama untuk fine-tune/evaluasi adalah
  `data/curated/esp32_s3_fall_v1/manifest.csv`.
- Jangan gunakan artefak model lama di `code/runs/srasta_fall/`; model tersebut
  berasal dari one-class training yang invalid.
- Jangan mengubah data raw di `data/csi-bench/` atau data di `data/external/`.
- Jangan mencampur data HP 232 fitur dengan ESP32 52 fitur.
- Data eksternal tidak boleh masuk ke test split utama atau dipakai untuk klaim
  metrik final. WiFall hanya untuk representation pretraining/ablation; ESP-Fi
  HAR hanya untuk pretraining dari source train split.
- Untuk baseline debugging, gunakan Random Forest transparan pada fitur gerak
  dari manifest curated. Baseline ini bukan artefak deployment dan secara
  default hanya boleh membaca train/validation. Test terkunci dibaca sekali
  setelah semua pilihan dibekukan.
- Karya untuk kategori Piranti Cerdas, Sistem Benam & IoT harus memberi bukti
  yang dapat didemokan untuk ketiga unsur tersebut. Untuk setiap requirement
  proposal, bedakan dengan jujur antara yang sudah berfungsi, yang sedang
  diimplementasikan, dan gap evidensinya - tanpa menghapus requirement itu.

## Implementasikan

1. Buat package bersama, misalnya `code/srasta_csi/`, yang dipakai identik oleh
   training dan inference. Isinya minimal:
   - validator kontrak frame CSI;
   - decoder I/Q ke 52 amplitude;
   - mask `first_word_invalid` tanpa menggeser indeks;
   - reader H5 CSI-Bench `[64, time, 1] -> [time, 52]`;
   - preprocessing kausal: quality validation, resampling timestamp, outlier
     handling, room-baseline normalization, dan motion energy;
   - konfigurasi preprocessing yang dapat diserialisasi ke JSON.

2. Buat training pipeline reproducible untuk TCN-Lite dan baseline Random
   Forest:
   - split hanya berdasarkan subject/session, bukan random window;
   - laporkan jumlah subject, sample, dan kelas per split;
   - train TCN residual Conv1D kecil (kernel 3, channel 24, dilation 1/2/4,
     global average pooling, output dua kelas);
   - simpan checkpoint, preprocessing config, model card singkat, dan metrik;
   - export model menjadi `.tflite` full INT8 memakai representative ESP32-S3
     dataset;
   - verifikasi output model TensorFlow dan TFLite konsisten pada replay input.

3. Buat edge service yang dapat berjalan tanpa serial hardware:
   - mode replay dari satu rekaman curated H5/NPZ;
   - bounded queue dan ring buffer frame;
   - endpoint FastAPI minimal: `/health`, `/status`, `/events`;
   - SQLite untuk event lokal;
   - adapter Blynk yang rate-limited dan bisa dimatikan lewat environment
     variable;
   - state `normal`, `suspected_fall`, dan `confirmed_fall`.
   - `confirmed_fall` harus menunggu interval inactivity setelah trigger;
     jangan klaim latensinya sama dengan suspected fall.

4. Tambahkan parser serial yang belum bergantung pada firmware final:
   - definisikan format frame JSON Lines atau binary yang versioned;
   - simpan metadata: sequence, timestamp, MAC sender, RSSI, noise floor,
     channel, bandwidth, sig mode, MCS, `len`, rx_state,
     `first_word_invalid`, dan `iq_bytes`;
   - implementasi harus menolak/mengarantina frame dengan config yang tidak
     sesuai kontrak.

5. Tambahkan test otomatis minimal untuk:
   - urutan I/Q dan hasil amplitude;
   - fixed mask 52 fitur;
   - `first_word_invalid`;
   - penolakan konfigurasi/frame invalid;
   - konversi axis H5;
   - replay end-to-end sampai TFLite inference;
   - tidak ada overlap subject antara train/validation/test.

## Definition of done untuk tugas ini

Kerja dianggap selesai hanya jika seluruh acceptance criteria milestone 50% BE + AI lulus. Berikan:

- perintah setup, train, export INT8, test, dan menjalankan replay service;
- artefak baseline beserta JSON preprocessing config; artefak `.tflite` hanya
  boleh diklaim/deploy jika release gate memang lulus;
- hasil test yang benar-benar dijalankan;
- report metrik grouped validation: recall, precision, F1, false alerts per
  hour (atau status belum dapat dihitung beserta alasan), packet-drop rate,
  inference latency, suspected-fall latency, confirmed-fall latency;
- `README` ringkas yang menjelaskan cara memakai system ketika ESP32-S3 datang;
- daftar jelas asumsi/batasan yang belum bisa divalidasi tanpa hardware.
- `artifacts/milestone_50_be_ai.json` dan checklist bukti yang dapat dipakai
  tim untuk proposal/video GEMASTIK, tanpa menulis ulang atau mengklaim
  performa yang tidak pernah diukur.

Jangan mengedit file user yang sudah berubah tanpa alasan kuat, terutama
`code/train_tcn_lite_csi.ipynb`, `code/runs/`, dan data raw. Mulai engineering
loop sekarang dan teruskan sampai milestone 50% BE + AI lulus.

---

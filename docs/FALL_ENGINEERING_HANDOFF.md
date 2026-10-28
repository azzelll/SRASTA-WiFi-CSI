# Fall detection: hasil engineering dan giliran pengambilan data

Checkpoint 23 Oktober 2026. Prioritas pemilik: fall → dataset lokal → presence
→ validasi → uji pengalaman. Pemilik menyatakan uji ketahanan sudah pass;
pekerjaan ini tidak mengulang acceptance ketahanan fisik.

## Hasil yang bisa dikerjakan tanpa perangkat

- Diagnosis v8 direproduksi pada 365 rekaman train/development. Ada CSV per
  rekaman, atribusi classifier/motion gate, ukuran pengaruh Hampel/clipping,
  saturasi input INT8 dan delapan contoh SVG lokal.
- Eksperimen selesai: dua konfigurasi × tiga seed × enam fold = **36 fitting**.
  Perubahan tunggal: riwayat Hampel `filtered` menjadi `raw`; arsitektur TCN
  tetap 500 × 52, 32 kanal. Tiap fold memakai empat orang fitting, satu
  kalibrasi dan satu evaluasi. Cutoff dipilih pada orang kalibrasi; motion
  floor dari persentil 1 fall pada fitting saja.
- Kandidat ditolak: tidak meningkatkan recall maupun specificity. Tidak ada
  model baru yang dipromosikan atau dipasang. V8 tetap model demo.
- Recorder mendapat protokol ADL panjang, gerak–diam–gerak, dan empat tanda
  waktu fall oleh pengamat. QA menolak nonfall yang bertumpang tindih dengan
  diam pascajatuh. Evaluator membedakan recall event, latency suspected dan
  confirmed, serta coverage inferensi yang hilang.
- Pemeriksaan arsip lokal dan preflight trainer presence menemukan **0 window
  train dan 0 validation accepted**. Satu sesi train masih pending pengamat
  independen/provenance; tiga sesi test/pilot dilewati sebelum membaca payload.

| Perbandingan OOF baru, rerata 3 seed | Recall fall | Specificity |
| --- | ---: | ---: |
| Arsitektur v8, Hampel filtered | 56,9% ± 4,1 pp | 51,4% ± 1,1 pp |
| Arsitektur sama, Hampel raw | 54,9% ± 4,3 pp | 50,6% ± 2,4 pp |

Ini hasil development pada enam orang train, bukan hasil test independen.
V8 beku pada U19 yang digunakan secara historis direproduksi terpisah:
recall 62,5%, specificity 64,9%, 15 FN dan 13 FP. Seluruh 15 FN berasal dari
classifier; motion gate tidak menambah miss pada U19. Tidak ada saturasi input
INT8 pada 365 rekaman. Mengubah threshold panel bukan perbaikan classifier.
Target proposal tetap recall ≥88% dan specificity ≥80%; belum tercapai.

## Yang perlu diambil alih pemilik

Semua command di bawah dijalankan dari root repo dengan checkout software ini.
Recorder baru belum dipasang pada Pi. Gunakan clone development yang memuat
perubahan ini atau jalankan di Mac; jangan memakai folder release runtime Pi
yang tidak memuat recorder. Pilihan port wajib berdasarkan identifikasi RX
sekarang. Detail service/serial: [capture quickstart](CAPTURE_QUICKSTART.md).

1. Siapkan TX/RX, posisi tetap, kode orang dan split tetap, serta pengamat yang
   benar-benar menyaksikan kondisi. Rencana minimum untuk pengembangan grouped:
   tiga orang train dengan kedua label fall/nonfall, orang validation terpisah,
   dan orang test baru yang tidak dibuka untuk tuning. Ini minimum struktur
   engineering, bukan jumlah sampel yang membuktikan akurasi produk.
2. Mulai dari pilot dan nonfall. Kumpulkan kosong, normal dan diam pada orang
   yang sama untuk tiap sesi, lalu ADL lebih panjang. Sertakan pembanding
   berjalan, berbalik, duduk/berdiri, mengambil barang dan berbaring nyaman;
   simpan aktivitas yang benar-benar diamati, bukan dugaan jenis kesalahan
   dari label dataset publik. Jangan mengubah posisi perangkat di tengah sesi.
3. Event fall hanya melalui prosedur tim yang disetujui, pelaksana dewasa
   terlatih, pengawas dan sarana sesuai. Mode `fall-observer` mencatat kejadian;
   ia tidak memberi instruksi menjatuhkan diri. Catat empat batas aktual:
   onset, akhir fall, awal diam pascakejadian, akhir diam. Tekanan tombol punya
   ketidakpastian reaksi manusia; metrik ini belum menjadi referensi latency
   presisi. Catat recovery sebagai kejadian terpisah bila mengumpulkannya.
4. Pengamat kedua mereview interval dan keempat batas. Setelah QA accepted,
   jalankan readiness. Sesi lama tanpa provenance tetap disimpan; buat sesi
   baru yang benar, jangan mengedit config/raw atau mengarang persetujuan.

```bash
SRASTA_RX_PORT=/dev/cu.GANTI_DENGAN_RX_TERVERIFIKASI
bash scripts/collect_local_csi.sh --port "$SRASTA_RX_PORT" \
  --root ../SRASTA_LOCAL_CAPTURE --pilot-only --pilot-seconds 15

# Tiga kondisi, default 180 detik per kondisi; form mengunci orang/split.
bash scripts/collect_local_csi.sh --port "$SRASTA_RX_PORT" \
  --root ../SRASTA_LOCAL_CAPTURE --protocol basic

# Nonfall panjang, 30 menit aktivitas yang diamati.
bash scripts/collect_local_csi.sh --port "$SRASTA_RX_PORT" \
  --root ../SRASTA_LOCAL_CAPTURE --protocol adl --duration 1800

# Gerak–diam–gerak, masing-masing 180 detik + persiapan.
bash scripts/collect_local_csi.sh --port "$SRASTA_RX_PORT" \
  --root ../SRASTA_LOCAL_CAPTURE --protocol motion

# Hanya setelah prosedur dan prasyarat sesi fall siap.
bash scripts/collect_local_csi.sh --port "$SRASTA_RX_PORT" \
  --root ../SRASTA_LOCAL_CAPTURE --protocol fall-observer
```

Tidak perlu menjalankan semua protokol sekaligus. Mulai pilot lalu basic;
periksa hasil sebelum melanjutkan. Pada Pi, hentikan hanya service yang memang
memegang RX, kemudian pulihkan setelah capture sesuai panduan operasi.
Satu RX tidak dibaca dua proses. Arsip tetap di luar Git dan cloud.

```bash
SRASTA_SESSION=../SRASTA_LOCAL_CAPTURE/sessions/SES_GANTI_DENGAN_HASIL
.venv/bin/python code/tools/qa_capture.py "$SRASTA_SESSION" --reviewer ANN_002
.venv/bin/python code/tools/evaluate_local_alerts.py "$SRASTA_SESSION"
.venv/bin/python code/tools/evaluate_local_alerts.py "$SRASTA_SESSION" --fall-events
.venv/bin/python code/tools/local_capture_readiness.py --root ../SRASTA_LOCAL_CAPTURE
```

Reviewer harus kode orang berbeda yang benar-benar menyaksikan interval.
Evaluator default menghitung FAR dari exposure nonfall bercoverage; opsi
`--fall-events` mencocokkan satu alert dengan satu event dalam 8 detik sejak
onset, dan melaporkan confirmation setelah ≥10 detik diam secara terpisah.
Interval tanpa coverage lengkap dikeluarkan secara eksplisit, bukan dihitung
sebagai sukses. Ini latency prediksi lokal, bukan pengiriman notifikasi HP.
Jangan menjalankan evaluator pada test untuk memilih threshold. Tiga menit
tanpa alert tidak membuktikan target ≤2/hari; periksa batas atas ketidakpastian.

## Setelah data tersedia

Engineering berikutnya menggunakan arsip accepted: audit distribusi lokal,
fold antarorang, kalibrasi/fine-tune fall, parity INT8 dan calon paket Pi;
presence mengikuti urutan pemilik. Test baru dibuka setelah model/protokol
beku. Validasi real CSI → event → kamera → caregiver dan uji pengalaman tetap
memerlukan perangkat/pengamat; keberhasilan unit test bukan acceptance fisik.
Tidak ada hasil training lokal atau peningkatan akurasi yang diklaim sekarang.

Detail reproduksi, hash dan pengujian: [bukti engineering](evidence/20261023-fall-engineering.md).

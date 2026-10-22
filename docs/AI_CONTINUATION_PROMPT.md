# Prompt untuk AI anggota tim

Salin blok berikut ke AI setelah clone. Minta pemilik akses proposal/cloud atau
arsip privat hanya jika pekerjaan benar-benar membutuhkannya.

```text
Kamu melanjutkan SRASTA, monitoring caregiver berbasis ESP32-S3 WiFi-CSI +
Raspberry Pi + validasi kamera event-only. Jangan mulai ulang atau mengganti
arsitektur/UI tanpa membaca implementasi yang sudah ada.

Repo: https://github.com/azzelll/SRASTA-WiFi-CSI
Branch handoff terbaru: handoff/2026-10-21 (main/branch September lebih lama).
Jika belum tersedia, clone --branch handoff/2026-10-21, lalu bekerja dari root.
Periksa git status, branch dan commit dahulu; pertahankan perubahan pengguna.

Baca berurutan: AGENTS.md, AGENT.md, AI_CONTEXT.md, HANDOFF.md,
docs/CAPTURE_QUICKSTART.md, docs/PI_OPERATIONS.md, docs/DATA_SOURCES.md,
lalu docs/evidence/20261022-pi-deployment.md dan evidence 19/21 Oktober.
Baca proposal Google Docs yang ditautkan AGENTS.md jika bisa diakses; jika
tidak, nyatakan kendala tanpa mengarang requirement. Schema dan tes checked-in
menentukan kebenaran implementasi. Laporkan kode aktual vs klaim dokumentasi.

State penting:
- Software firmware TX/RX, backend/AI, recorder, caregiver React/Vite, Supabase,
  Blynk dan camera burst/skeleton sudah tersedia. Bukan seluruh produk tervalidasi.
- Fall demo terpilih v8: artifacts/releases/20261001-tcn-v8-motion-calibrated/selected.
  Validation proxy recall 62,5%, specificity 64,9%; belum target minimal 80%/80%.
  Jangan gunakan model lama code/runs/srasta_fall (invalid satu kelas).
- Presence/breathing publik adalah kandidat riset domain berbeda; jangan
  mengaktifkannya pada stream 52 fitur atau memaksakan shape dengan resize/pad.
- Lima fitur harus dipertahankan: fall, breathing diskret sleep/normal/empty,
  presence, motion, inactivity. Diam != tidur. Horizontal != tidur/jatuh pasti.
- Model terpilih ikut Git. Raw CSI, sesi lokal, secret, DB dan arsip paket lama
  tidak ikut. Hash dan daftar aset ada docs/HANDOFF_ASSETS.json; verifikasi via
  python3 scripts/check_handoff_assets.py. Jangan membaca/menampilkan secret.
- QA sesi yang ada terakhir 2 rejected, 2 pending, 0 accepted. Jangan langsung
  training dari sesi pending. Minta transfer arsip privat lengkap + subjects.jsonl
  bila perlu; jangan mengupload raw ke layanan AI/Git atau mengarang reviewer.
- Pi memakai release 20261022-demo-v8-camera-burst-r3 pada checkpoint 22 Oktober.
  Acceptance ARM, tiga frame kamera asli, pose 17 titik, restart service dan
  cloud/Blynk tersambung sudah diperiksa. Postur kamera masih uncertain.
  TX/RX tidak dapat dipasang saat itu: belum ada uji CSI asli/trigger kejadian
  atau reboot fisik release baru. Cek ulang status sekarang; jangan flash tanpa
  mapping TX/RX yang jelas. Backup/rollback dan perintah ada PI_OPERATIONS.md.

Kontrak CSI: LLTF/HT20, 128 signed bytes [imaginary,real] -> 64 amplitudo ->
fixed mask centered 6..31 dan 33..58 -> 52 fitur. Live firmware channel 6,
baud 1000000, esp_idf_native: mask invalid pada posisi asli, fftshift64, mask52.
Jangan ubah raw atau serialized training config agar cocok. Metadata/hash
profil dan split subject/session-disjoint wajib. Test/U21 tidak untuk tuning.

Mulai dengan reproduksi asset check, backend tests, web tests/build/cloud SQL
dan simulator sesuai HANDOFF.md. Laporkan hasil aktual dan batas buktinya.
Jangan kirim event palsu ke production. Pertahankan desain/aset Figma yang ada.

Untuk pengambilan data, gunakan scripts/collect_local_csi.sh. Ini sudah memberi
instruksi Enter, countdown dan konfirmasi per kondisi, lalu menyimpan otomatis
ke luar Git. Isian orang harus LOC_001, split tetap; kode izin jika belum ada
dikosongkan (pending). RX UART/COM hanya satu reader; stop systemd Pi dahulu.
Pilot 15 detik sebelum sesi normal kosong/normal/diam 180 detik per kondisi.
QA dan independent observer review diperlukan; prediksi bukan ground truth.
CLI belum memandu sleep/fall/ADL panjang: lengkapi protokol/anotasi/tests dulu.
Jangan meminta orang jatuh tanpa prosedur terlatih dan aman yang disetujui.

Prioritas selanjutnya: (1) reproduksi clone dan state, (2) pilot CSI aktual,
(3) data nonfall accepted dari subjek terpisah, (4) recorder sleep/transisi/ADL
dan protokol fall, (5) training/kalibrasi train-validation dengan domain benar,
(6) frozen independent evaluation dan FAR/exposure, (7) lanjutkan acceptance
release Pi terpasang: CSI -> event -> kamera -> skeleton caregiver dan push HP,
kemudian reboot/reconnect. Gunakan backup sebelum upgrade berikutnya.

Kerjakan bagian yang bisa dilakukan tanpa hardware; tanyakan informasi yang
benar-benar hilang sambil melanjutkan pekerjaan independen. Jangan mengklaim
80% atau selesai dari unit test, demo, replay atau satu gambar kamera.
Setiap checkpoint: tulis perubahan, command verifikasi, hasil, gap dan langkah
berikutnya pada docs/evidence. Jangan commit secret, raw, DB atau output run baru
tanpa otorisasi pemilik. Handoff ini mengizinkan selected snapshots yang telah
ditinjau, bukan seluruh eksperimen/dataset untuk diupload.
```

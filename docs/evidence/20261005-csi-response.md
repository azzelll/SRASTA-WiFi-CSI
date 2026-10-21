# Diagnosis respons CSI — 5 Oktober 2026

User melaporkan jatuh tidak mengubah grafik atau menghasilkan peringatan.
User menyatakan jarak TX–RX 2–3 meter dan berada di antara keduanya.
Tidak diminta mengulangi jatuh; pemeriksaan menggunakan buffer/log yang
tersedia dan permintaan uji aktivitas biasa.

## Temuan sebelum perbaikan

1. Receiver dan inferensi aktif: sekitar 32 frame/detik, read error 0,
   tidak ada alert tersimpan. Jadi USB dan service memang mengalir.
2. Ringkasan 524 sampel log sejak reboot: motion maksimum **0,000250**,
   median **0,000188**, sedangkan ambang trigger **0,0003443831**.
   Semua state normal; tidak satu pun sampel log melewati gerbang gerakan.
   Log 1 Hz tidak menjadi anotasi waktu jatuh ataupun bukti bahwa setiap
   keputusan 5 Hz tercakup, tetapi event store juga tidak memuat alert.
3. Grafik memakai floor skala `0.001`, sementara energi live sekitar
   `0.0001–0.00025`. Variasi sampel `0.0001 → 0.0002` hanya menempati 9 unit
   vertikal pada SVG, sehingga perubahan terlihat kecil.
4. Buffer 196 frame/5,84 detik mempunyai **42 kanal aktif**, dengan kanal
   terpilih 21–30 selalu nol. Audit corpus training/validation sebelumnya
   mencatat tidak ada rekaman dengan selected carrier mati.

## Probe urutan frekuensi

Layanan dihentikan sebentar agar UART hanya dimiliki satu reader, lalu
otomatis dijalankan kembali dalam blok cleanup. Probe 263 frame I/Q asli:

- Null native: **0,27–37**.
- Mask centered yang langsung diterapkan pada native memberi **42** kanal aktif.
- Permutasi penuh 64 posisi ke koordinat centered, lalu mask yang sama,
  memberi **52** kanal aktif.
- Null setelah permutasi: **0–5,32,59–63**, sama dengan layout CSI-Bench.
- Tidak ada frame `first_word_invalid` dalam probe ini.

Urutan LLTF HT20 `0..31,-32..-1` serta posisi byte invalid dijelaskan oleh
[dokumentasi ESP-IDF ESP32-S3](https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32s3/api-guides/wifi.html#wi-fi-channel-state-information).
Kecocokan layout diperiksa dari hardware dan corpus; source recordings tidak
diubah, tidak di-resize, dan mask tidak dipilih adaptif dari kanal nonzero.

## Perbaikan dan pemeriksaan

- Decoder memiliki pilihan eksplisit `centered` / `esp_idf_native`.
  Mode native melakukan `fftshift` pada 64 amplitudo sebelum mask tetap.
- Invalid first word dimask pada posisi native sebelum permutasi. Carrier
  +1 yang invalid tetap nol pada koordinat centered, bukan menggeser channel.
- Urutan nondefault masuk ke capture hash. Hash centered lama tetap sama.
  Artifact TFLite meminta opt-in capture override untuk profil native;
  threshold/classifier/config artifact tetap dilindungi checksum.
- Service Pi, helper live Mac/Pi, recorder, metadata archive/QA, serta
  pembaca training presence memakai urutan yang dinyatakan dalam profil.
  Native default hanya dipakai untuk firmware repository ini.
- Rekaman lama tidak diinterpretasikan ulang. Metadata urutannya perlu
  diaudit sebelum fitting; belum ada training ulang pada sesi ini.
- Grafik menggunakan rentang nilai yang terukur dan menampilkan **Skala
  otomatis** beserta batas angkanya. Input nol tetap garis nol.
- Regresi sebelum fix: dua tes decoder/profil gagal; tes skala grafik gagal
  dengan rentang vertikal 9. Sesudah fix: **62 tes Python terkait lulus**,
  **1 tes tambahan frozen-profile override lulus**, **8 tes web lulus**,
  dan build TypeScript/Vite berhasil.
- Rilis Pi `/home/srasta/srasta-edge/releases/20261005-demo-v8-native`, arsip
  6.971.540 byte, SHA-256
  `efc48e9e03b1b881c2965dff5d70a427defdd4f3a385eacab69366761becb4a5`.
- Acceptance Pi: 55 file manifest sah, tiga probe sintetis sama dengan Mac,
  200 inferensi median **3,121 ms**, p95 **3,206 ms**. Ini benchmark software.
- Live check setelah restart: 100 frame, **52 kanal aktif**, tidak ada kanal
  yang selalu nol; native profile aktif, Blynk/cloud connected.
  Satu frame dikarantina saat transisi/startup; read error/drop 0.
- Vercel production `srasta-caregiver.vercel.app` telah diperbarui dengan
  fix grafik: deployment `dpl_4pj8RmULvcqixyvxMj9rkAPpdQG3`, READY.
- Browser Pi menampilkan kurva nyata dengan skala sekitar `2.6e-4`.
  Screenshot: `artifacts/pi/20261005-response-proof/motion-chart-fixed.jpg`.
- Readback Supabase: source live, tanpa simulasi, 14.903 frame,
  cloud connected, usia penerimaan **5,083 detik**.

## Yang masih membutuhkan bukti

Observasi terbaru 120 sampel selama sekitar satu menit, ketika permintaan
uji jalan/diam sudah dikirim, merekam energi **0,0002033–0,0002510**,
gerbang gerakan belum dilewati, semua state normal, dan frame bertambah
1.993. User belum mengonfirmasi pelaksanaan/waktu aktivitas pada tahap
pencatatan ini; observasi tetap **unlabelled**. Perubahan kurva tidak dengan
sendirinya membuktikan pengenalan gerakan manusia.

Pemetaan input dan skala grafik sudah diperbaiki. **Deteksi jatuh lokal
belum dibuktikan**, dan ambang masih membutuhkan evaluasi respons ruangan
serta data beranotasi. Fall v8 tetap mempunyai validation recall 62,5% /
specificity 64,9%. Ambang gerakan dan probability tidak diturunkan untuk
memaksa peringatan; tidak ada alert sintetis dikirim ke device produksi.

Bukti ringkasan disimpan di `artifacts/pi/20261005-response-proof/` dan
diabaikan Git. Pemantauan tetap aktif; alarm fisik masih disabled dan
presence/breathing diskret masih belum terhubung ke head lokal tervalidasi.

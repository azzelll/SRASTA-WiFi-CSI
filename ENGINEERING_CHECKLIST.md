# Engineering loop — 11 September 2026

Kontrak aktif: PROMPT.md, AGENT.md, AGENTS.md, AI_CONTEXT.md, proposal penuh, serta koreksi langsung pengguna: satu receiver COM9 dengan hotspot HP, pengujian laptop, model/dataset alternatif diizinkan. Semua cakupan produk dipertahankan.

## Selesai dan teruji

- [x] Baca penuh instruksi/proposal, audit checkout, pertahankan notebook/runs pengguna.
- [x] LLTF/HT20/128 byte, decode 52 posisi tetap, validasi sender/metadata/timestamp, bounded queue, reconnect dan reset epoch firmware.
- [x] Lima state caregiver, gap bukan bukti diam, critical/ack persisten, event lama tidak menyenyapkan critical baru.
- [x] API/WebSocket lokal, snapshot status/riwayat konsisten, token/origin, simulator eksplisit, replay/serial.
- [x] Breathing dengan quality gate dan penahanan tanpa keberadaan; pola berubah diuji menggunakan sinyal sintetis.
- [x] Kamera event-only dan GPIO/notifikasi fail-closed diuji dengan fixture.
- [x] Dashboard navy desktop/mobile, kelima state, ack, dialog darurat eksplisit, teks 200%, offline shell tanpa cache sensitif.
- [x] Build TX/RX/hotspot. COM9 receiver di-flash; CSI nyata dan dashboard serial sebelumnya terbukti berjalan.
- [x] 365 sumber CSI-Bench train/validation diunduh tanpa mengubah raw. Replay curated melalui dua model sampai runtime/API/WebSocket berhasil.
- [x] RF, TCN, 18 resep alternatif, transfer ESP-Fi HAR dan percobaan kalibrasi INT8 dicatat termasuk hasil gagal. Tidak membuka locked test.
- [x] 50 unit/API/replay test tanpa skip dan browser acceptance desktop/mobile lulus setelah perbaikan sinkronisasi.
- [x] Runbook lokal/hardware serta laporan evaluasi model tersedia.

## Aktif

- [x] CSI/dashboard pascapergantian dan cabut-pasang USB terbukti: 4.466 frame tambahan, 100 Hz, 45 detik; browser desktop/mobile lulus.
- [x] USB receiver pulih setelah cabut-pasang pengguna. Penyebab gangguan sebelumnya/uptime panjang masih perlu dibuktikan.
- [ ] Kalibrasi dua kondisi pada posisi baru: tenang berhasil (119 observasi, 30,20 detik, ready 100%); aktivitas normal ulang setelah perbaikan trafik menghasilkan 116 observasi valid tetapi distribusinya tumpang tindih; pengguna menyatakan belum bisa melakukan uji berjalan, sehingga kalibrasi terkontrol tertunda tanpa mengganti ambang.
- [x] Laporan engineering memuat hasil terbaru termasuk probe/kalibrasi gagal dan kebutuhan pemulihan USB.

## Belum terbukti / bergantung perangkat atau ground truth

- [ ] Akurasi jatuh yang memenuhi kualitas pengguna. Kandidat saat ini belum memenuhi recall dan specificity bersamaan; model gagal parity ditolak runtime.
- [ ] Evaluasi lokal yang terpisah dengan label aktivitas/event. Sesi energi gerak tidak membuktikan klasifikasi jatuh.
- [ ] Event-level precision/recall/F1, false alerts/hour, latensi kejadian sampai dugaan/konfirmasi, uptime lama.
- [ ] Raspberry Pi, kamera, buzzer/LED dan board TX fisik; pengguna menyatakan belum tersedia dan meminta lanjut laptop.
- [ ] Akurasi napas/pose manusia nyata; fixture bukan bukti fisiologis.
- [ ] Pengiriman Blynk/MQTT nyata (belum diminta/dikonfigurasi), instalasi PWA ponsel fisik, dukungan browser WebMCP asli.

Semua gap ini tetap bagian produk, tidak disamarkan oleh hasil simulator atau kompilasi.

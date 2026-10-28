# Demo Space pada Pi → website HP, 27 Oktober 2026

Pemilik meminta program mulai idle, Space langsung menampilkan jatuh,
dan kemudian menegaskan bahwa tombol ditekan di Raspberry Pi sementara
website HP mengikuti. Pi dinyalakan dan alamat saat tes diberikan pemilik.

## Implementasi

- `keyboard_demo.py`: terminal interaktif, OLED/LED/piezo, Space/R/Q.
- `keyboard_demo_cloud.py`: snapshot simulator melalui edge-sync HTTPS yang
  sudah ada, memakai credential perangkat pada file privat Pi. Perubahan
  tombol membangunkan worker; heartbeat satu detik. Gangguan cloud tidak
  memblokir kontrol lokal.
- Wrapper menjeda panel dan, untuk `--cloud-env`, layanan edge agar tidak ada
  dua penulis cloud untuk device yang sama. Exit memulihkan layanan yang
  tadinya aktif. Tidak mengganti unit systemd atau model.
- Snapshot memakai schema lama yang sudah deployed, marker model
  `SRASTA keyboard demo (Pi)`, tanpa skor, paket CSI, kamera, event insert,
  receipt, atau push baru. Tidak ada migrasi/function Supabase baru.
- Dashboard mengenali marker dan menampilkan IDLE/JATUH TERDETEKSI;
  polling satu detik selama demo. Snapshot tidak terkini ditandai
  KONEKSI TERPUTUS. Dashboard biasa tetap dipakai HP, tanpa parameter URL demo.
- `/?demo=keyboard` adalah pratinjau browser mandiri untuk QA, terpisah dari
  jalur Pi dan tanpa memuat modul koneksi cloud.

## Verifikasi

- Mac: 16 tes keyboard/publisher/panel lulus; termasuk input PTY tanpa
  Enter, latch/reset, cleanup kegagalan OLED, SIGTERM, pemulihan terminal,
  error jaringan tersanitasi dan perubahan tombol saat request masih berjalan.
- Website: 41 tes lulus, build TypeScript/Vite lulus, SQL cloud/public
  PGlite lulus. Tiga snapshot Python idle/fall/stopped lolos schema Zod ketat
  dari source contract edge-sync dengan Zod v4 lokal.
- Enam file demo/docs/tests dipasang di checkout `/home/srasta/SRASTA-WiFi-CSI`.
  Delapan tes keyboard/publisher lulus dengan Python OS Pi; syntax wrapper
  lulus. Mapping Pi cocok: merah BCM27, kuning BCM22, hijau BCM17, buzzer BCM16.
- Program asli dijalankan melalui SSH PTY dengan `--cloud-env` dan
  **`--buzzer off`**. Website produksi pada viewport 390×844 menerima
  IDLE → JATUH TERDETEKSI setelah Space → IDLE setelah R. Tidak ada overflow
  horizontal (lebar dokumen dan viewport keduanya 390 px).
- Setelah Q, proses exit 0 dan kedua layanan edge/panel kembali
  `ActiveState=active`, `SubState=running`.
- Website akhir Vercel READY, production alias
  <https://srasta-caregiver.vercel.app>, deployment
  `dpl_FAYjSHWA5b228u2RJAtdLEgaZUtc`.

SHA-256 file terpasang cocok dengan source Mac:

| File | SHA-256 |
| --- | --- |
| keyboard_demo.py | 35377893b96b559568e26f9a8349bd14a48a7723b8de066d3ed61e62a8a9ac9f |
| keyboard_demo_cloud.py | 33f375051b5c4cd1f4c032af199b31aae9c39a3b24b23048d76f18ef13e4e1fe |
| run_keyboard_demo.sh | 49ff3deb11e1aee0e46e3560d2b7dcdc770cf185da06ec443da3eaaf1671a920 |

Ini verifikasi interaksi manual Pi→cloud→browser ukuran HP, bukan observasi
HP fisik, bunyi/warna/piksel oleh agen, deteksi CSI, latency benchmark,
atau validasi model. Alarm dibisukan selama tes. Kredensial tetap di Pi;
tidak ada raw recording, gambar kamera, trained model, commit atau push Git.
Cara penggunaan: [KEYBOARD_DEMO.md](../KEYBOARD_DEMO.md).

## Tampilan pengambilan video

Pemilik meminta label demo dan jejak pengujian di website dihilangkan untuk
pengambilan video. Pada snapshot bermarker Pi, banner simulasi, petunjuk
Space/R, badge sumber, label simulator pada koneksi/receiver, dan metadata
model pengujian tidak ditampilkan. IDLE/JATUH TERDETEKSI tetap mengikuti Pi;
koneksi usang tetap ditandai. Provenance `simulation`, `source`, marker model,
serta ketiadaan pengukuran CSI/kamera tetap dipertahankan pada payload.
Pratinjau browser mandiri tetap terpisah dari jalur Pi.

Verifikasi perubahan tampilan: 41 tes web dan build TypeScript/Vite lulus.
Browser produksi 390×844 menampilkan IDLE dan Perangkat Online tanpa
banner atau istilah demo/simulasi/manual/Space pada teks halaman beranda.
Lebar dokumen tetap 390 px. Proses Pi milik pemilik yang sedang berjalan
tidak dihentikan atau diberi input oleh pemeriksaan ini.

Pemilik kemudian meminta angka dummy dan grafik CSI untuk bahan video.
`keyboard-demo-presentation.ts` menyediakan nilai presentasi di browser
hanya ketika snapshot Pi bermarker masih terkini: skor jatuh, napas,
durasi diam, kualitas sinyal, penghitung paket, laju, packet loss dan latency.
Grafik berisi 241 titik sintetis selama 60 detik, bergeser tiap detik dan
memiliki lonjakan saat state kritis. Snapshot masukan, provenance, event,
kamera, freshness dan payload cloud tidak diubah. Saat stale atau di luar
program keyboard Pi, fungsi tidak menghasilkan angka/grafik dummy.
Tes web sekarang 42 lulus; build TypeScript/Vite lulus.
Deployment akhir `dpl_HH2o1i6RmBuseFVMEwqpf25xW1JR` READY pada alias
produksi yang sama. Browser produksi 390 px memperlihatkan angka napas,
durasi, kualitas, skor, dan 241 titik grafik; dua pembacaan DOM menunjukkan
kurva berubah seiring waktu. Beranda dan halaman perangkat tidak mengandung
istilah demo/simulasi/manual/Space/simulator/pengujian pada teks terlihat.

Pemilik selanjutnya meminta keypoint orang berbaring di panel kamera dan
menghapus kotak laju pernapasan. Pada tampilan keyboard Pi, state kritis
yang masih terkini menampilkan fixture COCO17 berisi 17 titik tubuh
mendatar; reset atau koneksi usang menghilangkannya. Fixture terpisah pada
`keyboard-demo-camera.tsx`, tidak ditambahkan ke snapshot, event, koordinat
kamera asli, database atau cloud. Jalur kamera live tetap memakai koordinat
aktual. Kotak napas disembunyikan pada tampilan video Pi; lima metrik lain
disusun ulang (status notifikasi selebar baris di HP).

Verifikasi: 43 tes web lulus dan build TypeScript/Vite lulus. Pratinjau
render lokal state kritis pada viewport 390×844 menampilkan skeleton
mendatar, 17 titik, dan lima kartu tanpa kotak laju pernapasan. Program Pi
milik pemilik tidak diberi input untuk pemeriksaan ini.
Deployment kamera akhir `dpl_sDonAv3DHcubXyjvyZ4ZNCWhT1e5` READY.
Browser produksi menampilkan panel kamera video serta lima kartu tanpa
pernapasan, tanpa overflow horizontal pada viewport 390 px.

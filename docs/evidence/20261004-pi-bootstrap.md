# Bootstrap Raspberry Pi — 4 Oktober 2026

## Bukti hardware/SSH

User menunjukkan login SSH interaktif ke `srasta@srasta-edge` dan kemudian
menambahkan kunci publik setup khusus. Probe SSH dari agent berhasil membaca:

- Arsitektur `aarch64`; Debian GNU/Linux 13.7 (trixie).
- Python 3.13.5; filesystem 15 GB, kosong sekitar 6,8 GB.
- `sudo -n true` ditolak karena membutuhkan password. Tidak ada password
  diminta/disalin/digunakan dari screenshot.

Probe berikutnya dan transfer SCP timeout; resolusi `.local` juga tidak
stabil. User membaca `ip -br addr`: eth0 UP dengan IPv6 link-local saja,
wlan0 DOWN; `ip route` tidak menghasilkan default route. Setup Wi-Fi
diberikan sebelum melanjutkan instalasi. Penyebab semua disconnect belum
dibuktikan. Tidak ada perubahan firmware, konfigurasi radio, atau service
Pi yang berhasil dilakukan oleh agent pada tahap ini.

## Paket dan pemeriksaan lokal

- Helper packer memakai daftar file eksplisit; source `data/`, raw CSI,
  credential, database, `.venv`, dan model training tidak masuk paket.
- Paket dasar sekitar 6,6 MiB; paket offline sekitar 83,3 MiB termasuk
  27 wheel resmi PyPI untuk ARM64 CPython 3.13. Manifest memuat checksum
  masing-masing file; pemeriksaan target dilakukan sebelum instalasi.
- Installer memakai venv, hanya wheel biner, dan `pip check`; tidak memulai
  cloud atau service otomatis. Dependency snapshot utama disamakan dengan
  pembuat artifact RF publik, LiteRT dipilih 2.2.0.
- `bash -n` pada kedua helper lulus. Dua tes serial reader lulus.
- Probe dari paket yang diekstrak pada **Mac** lulus: fall v8 INT8
  `[1,500,52]`, tiga input sintetis sesuai referensi, kedua artifact RF
  publik dapat dimuat dan dieksekusi dengan amplitudo sintetis pada dimensi
  native. Tidak ada payload atau label manusia dipakai dalam probe ini.
- Benchmark 200 inferensi sintetis **Mac**: median sekitar 0,187 ms,
  p95 0,198 ms. Ini bukan pengukuran Pi, latensi kejadian, atau akurasi CSI.
- Fall v8 dan kedua model publik tidak dilatih ulang; model publik tetap
  `research_only`, `ESP32_validated=false`, tidak dihubungkan ke service live.

## Belum dibuktikan

Transfer paket lengkap, pemasangan dependency di Pi, kompatibilitas inferensi
Mac/Pi, latensi Pi, API/app di Pi, USB RX, paket CSI langsung, cloud dari Pi,
autostart, alarm fisik, dan kamera. Bukti paket Mac tidak menutup checklist
ini. Kunci setup privat berada sementara di folder privat `/private/tmp`,
bukan Git atau arsip deployment.

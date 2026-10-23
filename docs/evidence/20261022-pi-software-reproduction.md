# Reproduksi software pada Pi — 22 Oktober 2026

## Cakupan dan environment

Setup dan hasil di bawah berasal dari SSH ke Raspberry Pi ARM64. Percobaan
awal pemasangan dependency Windows/WSL dihentikan setelah pemilik menegaskan
target Pi. Public key khusus diotorisasi pemilik melalui terminal Pi;
password/private key tidak diminta atau dimasukkan ke repository.

Proposal Google Docs belum dapat diakses melalui alat yang tersedia.
Tidak mengarang isi proposal atau mengubah scope, UI Figma, lima fitur,
kontrak CSI dan model. Dokumen branch dibaca sebelum perubahan; bukti
deployment 22 Oktober dibedakan dari hasil pemeriksaan fresh berikut.

- Clone Pi: `/home/srasta/SRASTA-WiFi-CSI`.
- Branch: `handoff/2026-10-21`; commit dasar
  `ac1dc33069d8701d626d61e88b32611231df21c2`, dengan perubahan lokal di bawah.
- Linux 6.18.50+rpt-rpi-v8, ARM64, CPython 3.13.5.
- Venv development baru, terpisah dari production/rollback bersama.
- TensorFlow 2.21.0, LiteRT 2.2.0, Pillow 12.0.0; requirements model lainnya
  mengikuti pin handoff. Pip check lulus.
- Node 22.19.0 / npm 10.9.3, direktori tool user; SHA-256 arsip resmi ARM64
  `0b2d9f564b6594222a62c82e1df2efe119dd4a4aff29644f4dd325bf360b6bcc`.

## Integritas dan masalah reproduksi yang diperbaiki

Clone Pi lulus **32/32** ukuran dan SHA-256 aset handoff. Release aktif lulus
**135/135** payload deployment manifest. Hash model v8 tetap
`ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.
Manifest model publik/riset tetap live disabled.

Run awal suite backend menjalankan 119 tes dengan satu error dan satu failure:

1. Requirements handoff belum memasukkan Pillow, sehingga tes letterbox kamera
   pada venv bersih gagal mengimpor PIL. Ditambahkan requirements development
   Pi yang mencakup handoff, LiteRT dan Pillow, tanpa mengubah requirements live.
2. Tes macOS hanya mengganti sys.platform; konstanta B1000000 Linux masih
   terbaca. Tes kini memakai emulasi termios Darwin tanpa konstanta itu.
   Regresi tambahan menggunakan PTY Linux nyata untuk konfigurasi 1.000.000 baud
   dan memastikan ioctl khusus macOS tidak dipanggil.

Source produk tidak diubah: configure_serial, decoder, preprocessing,
profil, weights, threshold, UI dan kamera runtime tetap sama.

## Hasil fresh, semuanya pada Pi

| Pemeriksaan | Hasil | Batas bukti |
| --- | --- | --- |
| Asset check | **32/32 passed** | Integritas, bukan akurasi |
| Development pip check | No broken requirements | Venv baru |
| Backend unittest | **120 tests, 19,038 detik, OK**, tanpa skip | Export/parity sintetis dan PTY; tanpa RX fisik |
| Serial setelah normalisasi LF | **4 tests, 1,269 detik, OK** | Linux PTY, bukan USB RX |
| Web Vitest | **7 file, 30 tests passed**, 5,42 detik | Komponen/kontrak UI |
| Local-mode web build | TypeScript/Vite passed; 1.630 modules; 11,65 detik | Bundle index-jGrE46tZ.js; Figma tidak diedit |
| Cloud SQL | PGlite migration/RLS/idempotency/lease/revocation PASS | Tanpa Supabase produksi/actual push |
| Deno contract | **6 passed, 0 failed** | --no-check, bukan typecheck penuh |
| bash -n | Wrapper local/capture/Pi/install/start_demo passed | Tidak membangun firmware |
| Release pi_acceptance.py | passed, 135 payload hashes | Output terisolasi di Pi |
| Fixture TFLite | 3 window, max probability difference **0,0** | Sintetis, bukan data orang |
| Benchmark model | 200 runs sesudah warmup; median **3,219 ms**, p95 **3,294 ms** | Waktu model, bukan latensi kejadian |
| MoveNet acceptance | loaded, bounded COCO17 17x3 | Piksel sintetis; sensor tidak dibuka |
| Simulator HTTP | Root 200, bundle cocok, SSE dan lima status passed | Database simulator terpisah |
| Aksi caregiver simulator | ACK applied/idempotent; critical dipertahankan; bantuan applied tanpa auto-call | Tidak ada event/command ke produksi |

Backend memakai PYTHONPATH=code, OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1,
TF_NUM_INTRAOP_THREADS=2 dan TF_NUM_INTEROP_THREADS=1. Command pengulangan:
[PI_DEVELOPMENT_SETUP.md](../PI_DEVELOPMENT_SETUP.md).

## Isolasi dan status produksi

Runtime aktif tetap
`/home/srasta/srasta-edge/releases/20261022-demo-v8-camera-burst-r3`.
Service srasta-edge.service active/running, PID 1011, NRestarts=0 pada
pemeriksaan sebelum/sesudah tes; enabled dan Linger=yes. Unit, DB live,
credential, venv bersama dan release lama tidak ditimpa atau di-upgrade.

Simulator menggunakan unit user transient srasta-setup-simulator.service,
clone baru, loopback port 18735 dan artifacts/caregiver_simulator.sqlite3.
Environment eksternal dikosongkan, alarm disabled, tanpa provider sensor
kamera. Probe menolak source nonsimulator. Sesudah tes status dan aksi
caregiver, simulator dikembalikan ke normal.

Produksi saat diperiksa: source unavailable, monitoring offline, state
unverified, accepted/quarantined 0/0, serial disconnected. Kamera available
tetapi inactive; Blynk connected; cloud connected dan worker running. Ini
sesuai keterangan pemilik bahwa TX/RX belum terpasang.

Tidak mengambil CSI, gambar atau ground truth baru, membuat reviewer,
mengubah split, melatih ulang model release, deploy cloud, mengirim
notifikasi uji, flash atau reboot Pi. Fall v8 tetap proxy validation historis
62,5% recall / 64,9% specificity, belum target 80%/80%. Presence/breathing
publik tetap riset domain berbeda, bukan model live lokal.

## Bukti dan gap

Log tetap di Pi: `/home/srasta/SRASTA-WiFi-CSI/artifacts/setup/20261022-pi-setup/`:
pip-install.log, pip-dev-install.log, backend-tests.log (run awal gagal),
backend-tests-final.log, serial-tests-final.log, npm-ci.log, web-tests.log,
web-build.log, cloud-tests.log, deno-tests.log, simulator-http.json.

Acceptance release terisolasi:
`/home/srasta/srasta-edge/checks/20261022-codex-setup/software-acceptance.json`.

Pembuatan tunnel SSH background otomatis pada Windows ditolak pemeriksaan
otomatis dengan pesan blocked by policy. Pemilik kemudian membuka tunnel
foreground sendiri. Izin browser otomatis untuk localhost simulator tidak
diberikan, sehingga tidak mengklaim pemeriksaan visual browser. HTTP dan
aksi simulator sudah diperiksa langsung di Pi sebelum percobaan browser.

Berikutnya: daya TX, identitas RX UART/COM, pilot 15 detik dan QA, kemudian
capture accepted dengan split orang terpisah. Sleep/transisi/ADL/fall
memerlukan protokol dan anotasi/review sesuai sebelum training/validasi baru.
Firmware build/flash, alarm fisik, CSI-triggered camera, push HP dan reboot
fisik belum diuji dalam setup software ini.

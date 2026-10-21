# Deployment Raspberry Pi — 5 Oktober 2026

Sesi ini melanjutkan [bootstrap 4 Oktober](20261004-pi-bootstrap.md), setelah
user menghubungkan Pi ke Wi-Fi rumah dan memindahkan kabel RX ke UART/COM.
Tidak ada training ulang atau flash firmware pada tahap deployment ini.

## Platform dan paket

- Pi 4B 4 GB, microSD 16 GB, Debian 13.7 ARM64, Python 3.13.5.
- Wi-Fi rumah: IPv4 terakhir `192.168.1.15`, default route melalui wlan0.
- Rilis aktif `/home/srasta/srasta-edge/releases/20261005-demo-v8`.
- Paket offline v3: 83,3 MiB, 27 wheel resmi PyPI, 82 file dengan SHA-256
  dalam manifest ditambah manifest itu sendiri.
- SHA-256 arsip:
  `fd8e402133f091ea00f37f859563f0f64b064d9d057fbf9b40bc42dbabbea1af`.
- Virtual environment dipakai bersama melalui symlink ke rilis 4 Oktober.
  Rilis itu tetap dibutuhkan dan tidak boleh dihapus sekarang.
- Credential device/Blynk dipasang terpisah sebagai `edge.env`, mode 0600.
  Paket tidak memuat credential, rekaman CSI, source `data/`, database,
  environment training, atau model Keras.

## Software di Pi

`artifacts/pi/20261005-proof/software_acceptance.json` merekam hasil:

- Manifest lulus; API/dashboard mempunyai route `/`, `/health`,
  `/api/caregiver`, dan `/assets`.
- LiteRT 2.2.0 memuat fall v8 full INT8 `[1,500,52]`, tanpa TensorFlow di Pi.
- Tiga input sintetis menghasilkan keluaran identik dengan referensi Mac:
  selisih probabilitas maksimum 0 dan argmax sama.
- 200 inferensi setelah warmup: median **2,966 ms**, p95 **3,001 ms**,
  maksimum **3,072 ms**.
- Dua artifact RF publik dapat dimuat dan dieksekusi dengan amplitudo
  sintetis pada dimensi native. Keduanya tetap `research_only` dan
  `ESP32_validated=false`, serta tidak dipasang ke reader live.
- `pip check` tidak menemukan dependency yang rusak.

Pemeriksaan awal menemukan `code/dashboard.html` belum ada pada paket;
packer diperbaiki dan API diuji ulang sebelum layanan live dijalankan.
Installer juga diperbaiki agar memakai venv yang sudah ada, dan unit systemd
diperbaiki karena `WorkingDirectory` tidak menerima tanda kutip sebagai
bagian dari path. Unit hasil perbaikan lulus `systemd-analyze --user verify`.

## CSI dari perangkat

Port native/JTAG Espressif pertama terlihat tetapi tidak memberikan frame
CSI valid. Setelah user memindahkan kabel RX ke UART/COM, port yang sah:

`/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0` → `/dev/ttyUSB0`.

Konfigurasi live: baud 1.000.000, channel 6, LLTF HT20, 128 byte I/Q,
52 amplitudo tetap. Capture override dan max-gap 0,15 detik mengikuti jalur
demo Mac; artifact evaluasi asli tidak diubah.

Probe awal 10 detik menerima 315 frame valid, semua mempunyai amplitudo
nonzero; tidak ada read error, quarantine, gap, atau missing sequence.
Service kemudian menjadi satu-satunya reader UART.

Observasi enam sampel selama 60 detik, disimpan pada
`artifacts/pi/20261005-proof/live_observation.json`:

- Source `live`, `simulation=false`, monitoring online pada semua sampel.
- Frame valid bertambah dari **20.208 menjadi 22.140**.
- Laju penerimaan **31,0–32,7 Hz**.
- Packet loss terukur **0%** pada interval ini.
- Inferensi live **3,16–3,76 ms** pada sampel observasi.
- Blynk tetap terhubung; cloud menjadi terhubung setelah kontraknya diperbaiki.

Pengamatan ini membuktikan aliran dan eksekusi inferensi. Tidak ada sesi
jatuh beranotasi atau paparan non-fall beranotasi untuk menghitung recall,
specificity, atau false alerts/hour dari interval ini.

## App dan cloud

App Pi diperiksa melalui tunnel SSH `127.0.0.1:8015` → Pi `127.0.0.1:8000`.
Beranda menampilkan **CSI langsung**, receiver **Mengalir**, edge **Aktif**,
Blynk **Terhubung**, serta angka capture/loss terkini. Halaman Perangkat
menampilkan frame valid yang terus naik dan inferensi sekitar 3,3 ms.
Screenshot lokal disimpan pada `artifacts/pi/20261005-proof/pi-dashboard.jpg`.

POST cloud awal ditolak HTTP 400 `invalid_summary_contract`. Penyebabnya:
snapshot Python sudah memuat `presence`, `inactivity`,
`stationary_duration_s`, dan `breathing_condition`, sedangkan allowlist
strict fungsi Supabase belum mengenali field tersebut.

Schema dipisahkan ke `supabase/functions/edge-sync/contract.ts`, lalu field
ditambahkan dengan tipe/enum eksplisit. Nilai unavailable tetap null/unknown;
field opsional menjaga kompatibilitas rilis lama. Unknown/raw-CSI fields
tetap ditolak pada envelope, snapshot, dan nested model.

- Regresi sebelum perbaikan: dua dari empat tes gagal pada ringkasan Pi.
- Setelah perbaikan: **4/4 tes kontrak lulus**, `deno check` handler lulus.
- Tiga tes Python terkait privasi summary, outbox/command idempotence,
  dan reset sequence setelah reconnect lulus.
- Helper shell lulus `bash -n`; helper Python lulus `py_compile`.
- Fungsi `edge-sync` berhasil di-deploy ke proyek SRASTA yang sudah diotorisasi.
- Readback `device_status` Supabase merekam source `live`, tanpa simulasi,
  monitoring online, 21.359 frame, cloud connected, dan usia penerimaan
  **1,659 detik**. Bukti: `artifacts/pi/20261005-proof/cloud_readback.json`.
- Tidak ada service Mac yang menjalankan device cloud yang sama.

Readback membuktikan penyimpanan cloud dan UI Pi. Refresh dashboard pada HP,
push HP, dan remote caregiver ACK dari HP masih memerlukan proof tersendiri.

## Layanan otomatis dan batas yang masih terbuka

`srasta-edge.service` terpasang sebagai user, status aktif/running,
`NRestarts=0`, enabled, dan `Linger=yes`. Restart-on-failure dikonfigurasi;
reader membuka ulang RX pada port by-id yang sama jika USB hilang/stall.
Database persisten terpisah dari folder rilis.

Perintah reboot dari sesi agent awalnya ditolak oleh autentikasi admin Pi
(`Interactive authentication required`). User kemudian menjalankan reboot
sendiri. Pemeriksaan berikutnya membuktikan boot ID berubah:

- Sebelum: `75222b39-71e5-411c-b786-34c5b91aebf8`.
- Sesudah: `3c7b20d0-f5f0-41f4-87da-ecf098979ba5`.
- Unit aktif otomatis sejak **5 Oktober 00:42:55 WIB**, PID 1288,
  `NRestarts=0`, enabled, `Linger=yes`.
- Manifest 82 file kembali lulus checksum.
- Dua sampel berjarak 5 detik menunjukkan frame baru **4.281 → 4.444**,
  source live, monitoring online, 32,3–32,4 Hz, loss 0%, serta Blynk/cloud
  connected pada keduanya.
- Readback Supabase setelah reboot berisi **6.646 frame** dengan usia data
  **3,767 detik**, source live, tanpa simulasi.
- Dashboard dibuka ulang setelah tunnel dipulihkan dan kembali menampilkan
  CSI langsung, receiver Mengalir, edge Aktif, dan Blynk Terhubung.

Bukti tersimpan pada `artifacts/pi/20261005-proof/post_reboot.json`,
`cloud_after_reboot.json`, dan `pi-dashboard-after-reboot.jpg`.
Autostart setelah boot sudah dibuktikan; sesi ini tidak memverifikasi
operasi 24 jam, pemulihan pemadaman mendadak, atau seluruh kondisi jaringan.

Fall v8 tetap kandidat demo: validation recall **62,5%**, specificity
**64,9%**, belum mencapai 80%/80%. Benchmark 3 ms adalah latensi model,
bukan latensi konfirmasi jatuh. Konfirmasi juga memakai gerbang gerakan dan
interval diam pascakejadian.

Presence live, inactivity berbasis presence, dan breathing diskret
sleep/normal/empty belum memiliki head ESP32 lokal tervalidasi pada service
ini. Snapshot mempertahankan unknown/null. Alarm fisik dan kamera belum
diuji; layanan sekarang memakai `--alarm disabled`.

# SRASTA pada Raspberry Pi 4B

Target sesi ini: Pi 4B 4 GB, microSD 16 GB, hostname `srasta-edge`, user
`srasta`. SSH berhasil diperiksa pada 4 Oktober 2026: Debian 13.7, ARM64,
Python 3.13.5, ruang kosong awal sekitar 6,8 GB. Pada 5 Oktober 2026,
instalasi model, API/app, CSI asli, Blynk, serta sinkronisasi Supabase dari
Pi sudah diperiksa. [Bukti deployment](docs/evidence/20261005-pi-deployment.md)
memisahkan hasil software, aliran hardware, dan batas validasi model.

## Instalasi yang sedang berjalan

Checkpoint **22 Oktober 2026**: [operasi/rollback](docs/PI_OPERATIONS.md) dan
[bukti terukur](docs/evidence/20261022-pi-deployment.md). Pemeriksaan lama di
bawah tetap diberi tanggal agar tidak dianggap bukti baru.

- Pi memakai Wi-Fi/hotspot pemilik, terjangkau lewat `srasta-edge.local`.
  IP numerik berubah mengikuti DHCP; `192.168.1.15` hanya alamat historis.
- Rilis aktif: `/home/srasta/srasta-edge/releases/20261022-demo-v8-camera-burst-r3`.
  Acceptance ARM64, sensor kamera tiga frame, restart layanan dan koneksi
  Blynk/cloud worker telah diperiksa. Postur uji kamera masih uncertain.
- TX/RX tidak dapat dipasang pada checkpoint 22 Oktober. Sumber unavailable,
  health tidak siap dan zero frames diharapkan; bukan simulasi. CSI → kamera
  → skeleton caregiver serta reboot fisik release ini belum dibuktikan.
- RX memakai konektor **UART/COM**, dengan port
  `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`. Konektor USB native/JTAG
  yang ditemukan sebelumnya tidak mengeluarkan JSONL CSI firmware ini.
- `srasta-edge.service` berjalan sebagai user `srasta`, memakai fall v8
  INT8, channel 6, LLTF HT20, baud 1.000.000, dan urutan frekuensi
  `esp_idf_native` yang dipetakan ke 52 kanal training.
- Database persisten: `/home/srasta/srasta-edge/state/live.sqlite3`.
- Credential khusus device dan Blynk: `/home/srasta/srasta-edge/edge.env`,
  mode `0600`. Admin/service-role key tetap di Mac.
- App caregiver: <https://srasta-caregiver.vercel.app>. Pi mengirim ringkasan
  lewat HTTPS; Mac tidak menjalankan inferensi dan tidak perlu terus menyala.
- Unit sudah `enabled` dan user sudah `Linger=yes`. Setelah user menjalankan
  reboot pada 5 Oktober, layanan, CSI, Blynk, dan cloud kembali aktif otomatis.

Virtual environment rilis aktif memakai symlink ke `.venv` pada rilis
`20261004-demo-v8`. **Jangan hapus rilis lama tersebut** sebelum environment
penggantinya dipasang dan diperiksa.

Untuk masuk lagi ke terminal Pi setelah reboot, jalankan di Mac:

```bash
ssh -o ServerAliveInterval=30 srasta@srasta-edge.local
```

`sudo reboot` memulai ulang Pi secara otomatis selama daya tersambung.
Jika sebelumnya memakai `sudo poweroff`, pasang ulang adaptor daya untuk
menyalakannya kembali.

Perintah berikut dijalankan di terminal **Pi**:

```bash
systemctl --user status srasta-edge.service --no-pager
systemctl --user restart srasta-edge.service
systemctl --user stop srasta-edge.service
systemctl --user start srasta-edge.service
loginctl show-user srasta -p Linger
curl http://127.0.0.1:8000/health
```

Untuk mematikan Pi sebelum mencabut daya, jalankan `sudo poweroff` dan
tunggu proses shutdown selesai. User memasukkan password langsung jika
diminta.

## Jika SSH melalui Ethernet putus: sambungkan Wi-Fi

Pada pemeriksaan awal `eth0` hanya memiliki IPv6 link-local, `wlan0` masih
DOWN, dan tidak ada default route. Output ini belum membuktikan penyebab
semua disconnect, tetapi Pi belum mempunyai koneksi IPv4/internet biasa.
Tetap sambungkan Ethernet sampai akses Wi-Fi berhasil.

Di terminal **Pi** yang sudah login:

1. Jalankan `sudo raspi-config`, pilih **Localisation Options > WLAN Country**,
   pilih **ID Indonesia** jika Pi dipakai di Indonesia, lalu Finish.
2. Jalankan `sudo nmcli radio wifi on`, lalu `nmcli dev wifi list`.
3. Pilih Wi-Fi yang sama dengan Mac dan jalankan
   `sudo nmcli --ask dev wifi connect "NAMA_WIFI"` dengan nama sebenarnya.
   Masukkan password langsung saat diminta; jangan kirim ke chat atau
   meletakkannya dalam argumen shell.
4. Jalankan `hostname -I` dan `ip route`; simpan alamat IPv4 Pi.
5. Dari terminal baru **Mac**, uji `ssh srasta@IP_PI` sebelum melepas Ethernet.

Jika sesi Ethernet sudah terputus sebelum setup, login kembali lewat
`ssh srasta@srasta-edge.local`. Jika akses itu juga gagal, gunakan monitor
HDMI dan keyboard sementara pada Pi untuk menjalankan langkah di atas.
Panduan mengikuti [dokumentasi Raspberry Pi](https://www.raspberrypi.com/documentation/computers/configuration.html#wireless-connection).

## Paket dari Mac

Jalankan dari root repository dengan model terpilih dan `web/dist` tersedia:

```bash
.venv/bin/python scripts/pack_pi_demo.py \
  --output artifacts/pi/srasta-pi-demo.tar.gz
```

Paket menggunakan daftar file eksplisit: kode runtime, app hasil build, fall
v8 INT8 dan konfigurasi, serta dua artifact publik sleep/empty dan presence.
Tidak menyertakan `.env`, database, rekaman CSI, source `data/`, model Keras,
atau environment training. Setiap file mempunyai SHA-256 dalam manifest.
`synthetic_acceptance.npz` berisi input sintetis dan keluaran Mac untuk
memeriksa kompatibilitas inferensi, bukan rekaman orang.

Untuk pemasangan tanpa internet di Pi, unduh wheel resmi pada Mac:

```bash
.venv/bin/python -m pip download --index-url https://pypi.org/simple \
  --only-binary=:all: --platform manylinux_2_27_aarch64 \
  --platform manylinux_2_28_aarch64 --platform manylinux2014_aarch64 \
  --python-version 3.13 --implementation cp --abi cp313 \
  -r code/requirements-pi-demo.txt --dest artifacts/pi/wheelhouse
.venv/bin/python scripts/pack_pi_demo.py \
  --wheelhouse artifacts/pi/wheelhouse \
  --output artifacts/pi/srasta-pi-demo-offline.tar.gz
```

LiteRT 2.2.0 menyediakan wheel CPython 3.13 ARM64 di
[PyPI resmi](https://pypi.org/project/ai-edge-litert/2.2.0/).
Versi NumPy/scikit-learn/joblib disamakan dengan pembuat artifact publik.
Paket offline membekukan wheel dependensi transitif melalui checksum juga.

## Instalasi pada Pi

Transfer ke folder rilis baru milik user, bukan menimpa instalasi aktif.
Verifikasi SHA-256 arsip dari Mac setelah transfer. Contoh berikut menggunakan
alamat Pi dan nama rilis yang sudah diperiksa:

```bash
scp artifacts/pi/srasta-pi-demo-offline.tar.gz srasta@srasta-edge.local:srasta-pi-demo.tar.gz
ssh srasta@srasta-edge.local
mkdir -p ~/srasta-edge/releases/RELEASE_ID
tar -xzf ~/srasta-pi-demo.tar.gz -C ~/srasta-edge/releases/RELEASE_ID
cd ~/srasta-edge/releases/RELEASE_ID
bash scripts/install_pi_demo.sh
```

Jika modul `venv`/ensurepip belum tersedia, user dapat memasangnya dengan
`sudo apt install python3-venv`; password dimasukkan langsung di terminal.
Installer dibatasi ARM64 Python 3.13 dan tidak menjalankan service/cloud.
Ia memeriksa checksum, memasang wheel dalam `.venv`, menjalankan `pip check`,
memuat ketiga model, membandingkan tiga input sintetis Mac/Pi, dan mengukur
200 inferensi. Bukti disimpan di `artifacts/pi/software_acceptance.json`
dan `installed_versions.txt`.

## API dan app lokal

```bash
bash scripts/run_pi_demo.sh simulator
```

Pada Mac, buka tunnel terpisah:

```bash
ssh -N -L 8000:127.0.0.1:8000 srasta@srasta-edge.local
```

Buka <http://127.0.0.1:8000>; `/health` harus merespons dan banner simulasi
harus terlihat. Mode ini tidak memuat `.env` atau mengirim cloud/Blynk.
Port API tetap loopback; app caregiver remote memakai Supabase.

## CSI asli

Setelah software lolos, sambungkan board berlabel **RX ke USB Pi** dan beri
daya **TX**. Posisi kedua board harus tetap. Periksa:

```bash
ls -l /dev/serial/by-id
id
```

Gunakan port RX yang diverifikasi, bukan nomor port Mac atau tebakan `ttyUSB0`.
Jika akses ditolak, user dapat menambahkan `srasta` ke grup `dialout` memakai
`sudo usermod -aG dialout srasta`, lalu login SSH baru. Satu port hanya boleh
dipakai satu reader. Live memakai channel 6, LLTF HT20, baud 1.000.000,
dan batas gap 0,15 detik yang disamakan dengan jalur Mac:

```bash
bash scripts/run_pi_demo.sh live /dev/serial/by-id/PORT_RX_TERVERIFIKASI
```

Mulai dengan aktivitas biasa, tanpa melakukan jatuh. Buktikan frame valid
bertambah, amplitudo bukan nol, channel sesuai, inferensi selesai, serta
status offline ketika RX dilepas. Ringkasan service bukan rekaman validasi
beranotasi. Pemindahan `.env` dilakukan terpisah dan privat setelah service
Mac dengan device yang sama dihentikan. Jangan menyalin service-role key.

Autostart diaktifkan setelah port dan jalur live lolos. Alarm audio dan
buzzer GPIO masih membutuhkan uji fisik; helper memakai `--alarm disabled`.
Kamera OV5647 dan MoveNet sudah diuji di Pi pada 9 Oktober. Pemicu kamera
dari CSI asli masih perlu diperiksa setelah RX disambungkan kembali.

## Kamera saat anomali

Rilis kamera menjalankan tangkapan hanya untuk kejadian model yang masih
terkini. Hasil postur ditautkan ke UID kejadian dan ditampilkan pada app.
Pembaruan 19 Oktober menambahkan ringkasan 17 titik tubuh terukur untuk
digambar sebagai skeleton di panel caregiver. Koordinat `[y, x, skor]` dibatasi
0–1; foto tidak disimpan atau diunggah oleh integrasi ini. Ringkasan postur
dan titik disimpan di SQLite, lalu dikirim bersama snapshot cloud. Rekaman
lama tanpa koordinat tidak diberi skeleton buatan.

Pembaruan berikutnya pada 19 Oktober memeriksa tiga frame per kejadian dan
memerlukan minimal dua frame andal yang sepakat tanpa arah berlawanan.
Tubuh terpotong/tertutup atau postur berubah tetap belum jelas. Detail kejadian
di app menyimpan konteks historis; tombol caregiver membedakan menunggu dan
diterima perangkat. [Bukti software](docs/evidence/20261019-caregiver-hardening.md).

Paket burst/skeleton sudah dipasang pada Pi pada 22 Oktober. Tangkapan
terisolasi menghasilkan pose 17×3, tetapi keypoint tubuh masih kurang andal.
Trigger CSI asli dan tampilan event yang sama pada caregiver belum diuji.
Ikuti [panduan operasi](docs/PI_OPERATIONS.md) untuk pemeriksaan/rollback.
Berbaring tidak memastikan tidur atau jatuh; postur tegak dapat berarti duduk.

Uji kamera fisik terakhir menghasilkan “Keypoint tubuh kurang andal”; arahkan
kamera agar tubuh utuh terlihat dengan pencahayaan cukup. Hentikan preview
sebelum layanan memakai kamera yang sama.

Uji diagnostik memakai kamera asli dengan pemicu sintetis, tanpa peringatan
live/cloud. Blok perintah lengkap di
[Kamera diagnostik](docs/PI_OPERATIONS.md#kamera-diagnostik-tanpa-alert-production)
memulihkan service lewat `trap` jika tes gagal. Jalankan dari release baru dan
jangan menjalankan preview lain bersamaan. Jangan menimpa folder release lama.

Jangan melakukan jatuh untuk menguji pemasangan. Uji akurasi kamera dan
fall CSI tetap memerlukan protokol serta data beranotasi tersendiri.

## Layanan otomatis

Installer user service memeriksa manifest dan port RX sebelum memasang unit.
Jalankan di Pi setelah software dan aliran RX terbukti:

```bash
cd ~/srasta-edge/releases/20261022-demo-v8-camera-burst-r3
.venv/bin/python scripts/install_pi_user_service.py \
  --rx-port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
  --subcarrier-order esp_idf_native \
  --camera-model artifacts/models/movenet-lightning/model.tflite \
  --camera-python /usr/bin/python3 --start
sudo loginctl enable-linger srasta
systemctl --user is-enabled srasta-edge.service
loginctl show-user srasta -p Linger
```

Pada instalasi sekarang, `enable-linger` sudah berhasil. `Linger=yes` membuat
manager user berjalan saat boot tanpa perlu login SSH. Unit memulai ulang
proses jika gagal; reader mencoba membuka port RX yang sama ketika USB
belum tersedia. Boot sesungguhnya harus diperiksa sesudah `sudo reboot`:
pastikan unit aktif, `/health` online, frame bertambah, serta cloud terhubung.

Hentikan unit sebelum menjalankan simulator atau reader foreground pada
port API/serial yang sama. Foreground live memakai `.env` di folder rilis;
untuk memakai credential layanan yang sudah dipasang, berikan
`--env /home/srasta/srasta-edge/edge.env` pada helper. Jangan menjalankan
service Mac dengan device cloud yang sama secara bersamaan.

Untuk memeriksa app Pi dari Mac:

```bash
ssh -N -L 8015:127.0.0.1:8000 srasta@srasta-edge.local
```

Buka <http://127.0.0.1:8015>. Tunnel hanya untuk pemeriksaan lokal; app remote
tetap menerima data lewat Supabase.

## Batas model demo

- Fall v8 adalah model sementara yang disetujui: recall validation 62,5%,
  specificity 64,9%; belum memenuhi target akurasi 80%/80%.
- Model publik sleep/empty dan presence dapat dimuat untuk eksperimen,
  tetapi tidak kompatibel sebagai model presence lokal terverifikasi.
  Tidak dipasang ke jalur live. Kandidat riset tiga kelas memiliki normal
  proxy HAR; belum ada classifier awake/normal lokal yang tervalidasi.
- Probe sintetis membuktikan checksum, loading, dan eksekusi lintas runtime.
  Ia tidak mengukur akurasi, false alert, atau estimasi napas manusia.
- Data publik mentah tetap pada Mac; CLI inferensi rekaman publik membutuhkan
  source metadata dan payload yang sah, sehingga keberadaan artifact di Pi
  saja belum berarti inferensi rekaman publik sudah tersedia di sana.

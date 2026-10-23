# Deployment Pi dan kamera — 22 Oktober 2026

## Perubahan yang benar-benar dipasang

Source runtime dari checkpoint Git `21678366d2ab945a1205d86f7ac4cf1a930e5eee`
dipaketkan ulang dengan build web **local mode**, lalu dipasang ke folder baru:
`/home/srasta/srasta-edge/releases/20261022-demo-v8-camera-burst-r3`.
Unit user `srasta-edge.service` kini menunjuk folder tersebut. Ini memasang
burst tiga frame dan penyimpanan pose/skeleton yang pada handoff sebelumnya
baru diuji di Mac. Model fall v8, threshold, motion gate dan kontrak CSI sama.
Tidak ada training atau peningkatan angka akurasi dalam pekerjaan ini.

Arsip lokal `artifacts/pi/20261022-demo-camera-burst-r3.tar.gz`:

- Ukuran: **25.180.089 byte**, 136 file termasuk manifest, 135 payload berhash.
- SHA-256: `0ae70228696bbd533a28f9b848447065d2c4dac628e5024755c284d34a818f04`.
- Checksum arsip dicocokkan setelah transfer; seluruh payload diverifikasi di Pi.
- Memuat runtime/web, fall v8, MoveNet beserta lisensi, model occupancy riset,
  fixture sintetis dan script install/acceptance. Model riset tetap tidak live.
- Tidak memuat env/credential, DB, raw CSI atau gambar. Arsip tidak ikut Git;
  source dan selected model snapshots sudah tersedia pada branch handoff.

Build dan pack pada Mac:

```bash
cd web
VITE_ACCESS_MODE=local VITE_SUPABASE_URL= VITE_SUPABASE_PUBLISHABLE_KEY= VITE_VAPID_PUBLIC_KEY= npm run build
cd ..
.venv/bin/python scripts/pack_pi_demo.py \
  --output artifacts/pi/20261022-demo-camera-burst-r3.tar.gz \
  --camera-model artifacts/models/movenet-lightning/model.tflite \
  --research-run artifacts/research/20261019-occupancy-calibrated
```

Untuk mengulang pembuatan, pilih nama output baru. Arsip berikutnya dapat
berbeda SHA karena metadata build/arsip; bandingkan manifest payload juga.

## Host, environment dan pemulihan

SSH mDNS `srasta@srasta-edge.local` berhasil. IP hotspot sebelumnya sudah berubah;
alamat numerik bukan konfigurasi tetap. Tidak ada perubahan Wi-Fi/SSH daemon.
Autentikasi memakai public key yang dipasang pemilik pada Pi; private key tetap
lokal dan ignored, tidak diterbitkan.

- ARM64 / Linux 6.18.50+rpt-rpi-v8 / CPython 3.13.5.
- Ruang kosong sebelum pemasangan 6,1 GB; suhu awal 39,9°C;
  `get_throttled=0x0` pada saat pemeriksaan, bukan uji beban panjang.
- Delapan versi pin requirements cocok; `pip check` lolos. Reuse symlink venv
  4 Oktober tanpa pip install/upgrade, mempertahankan environment rollback.
- Backup unit + SQLite konsisten dibuat saat layanan berhenti:
  `~/srasta-edge/backups/20261022-before-camera-burst-20261022T035039Z/`.
  File DB/unit privat; credential 0600 tetap pada path semula.
- Unit managed sebelumnya disimpan. Kolom `camera_validations.pose_json`
  terverifikasi setelah start; persistent events/camera rows tetap nol.
- Saat menyiapkan ringkasan diagnostik, helper ad hoc salah menganggap pose
  sebagai list, padahal kontraknya `{format,keypoints}`. Penanganan kegagalan
  memulihkan layanan lama. Ringkasan diperbaiki tanpa mengubah runtime atau
  mengambil gambar ulang; pemasangan berikutnya berhasil. Backup tetap utuh.

Perintah operasi/rollback: [PI_OPERATIONS.md](../PI_OPERATIONS.md).

## Hasil terukur

| Pemeriksaan | Hasil | Batas bukti |
| --- | --- | --- |
| `code/pi_acceptance.py` pada Pi | passed, 135 payload hashes | Software/sintetis, bukan CSI manusia |
| Mac/Pi parity fall | 3 window, max probability difference **0,0** | Fixture sintetis INT8 |
| 200 inferensi setelah 20 warmup | median **2,981 ms**, p95 **3,048 ms**, max **3,137 ms** | Waktu model, bukan latensi deteksi kejadian |
| Model occupancy | 2 publik + 3 kandidat dimuat dan dieksekusi | Research only; live tetap disabled |
| Kamera model sintetis | MoveNet loaded, COCO17 17×3 | Tidak membuka sensor pada acceptance software |
| Kamera fisik OV5647 | Sensor terdeteksi, burst 3 frame, pose bounded 17×3 | Hasil **uncertain**, “Keypoint tubuh kurang andal” |
| Gating kamera terisolasi | Normal tidak capture, event sama tidak diulang, kamera idle sesudahnya | Pemicu sintetis lokal; bukan kejadian CSI nyata |
| Latensi burst kamera | **3.384,6 ms** | Satu pengukuran termasuk startup/capture/inferensi; bukan distribusi |
| Local HTML + JS/CSS | HTTP merespons, byte cocok dengan paket | Pemeriksaan HTTP, bukan visual acceptance HP |
| Service restart | active/running, PID berganti, NRestarts=0 | Restart proses, belum reboot fisik |
| Autostart configuration | enabled, Linger=yes | Konfigurasi, belum uji boot release ini |
| Blynk dan cloud sync | connected, worker_running, last_error null setelah restart | Bukan uji push HP atau caregiver command round-trip |
| TX/RX | **Tidak dapat dipasang oleh pemilik saat sesi ini** | Live CSI dan trigger fisik belum diuji |

Uji kamera menggunakan `code/camera_acceptance.py` dengan layanan dihentikan
sementara, DB temp terisolasi, tanpa alert production. Foto tidak disimpan/
diunggah; koordinat hasil lengkap tetap pada file diagnostik privat di Pi.
Laporan publik hanya memuat outcome/shape/latensi, tanpa koordinat/event UID.
Keypoint lemah tidak diubah menjadi postur pasti atau skeleton buatan.

Sesudah restart, snapshot pada `2026-10-22T03:53:33Z`:
`source=unavailable`, `simulation=false`, `monitoring_online=false`,
`state_verified=false`, accepted/quarantine **0/0**, kamera available tetapi
inactive. `/health.ok=false` dan serial disconnected memang diharapkan tanpa
RX. Worker serial tetap berjalan menunggu port lama yang diverifikasi;
installer memakai `--keep-current-rx-if-disconnected`, bukan memilih port baru.
Tidak ada event palsu dimasukkan ke DB produksi.

## Bukti mesin yang ikut repo

Di [`20261022-pi-checks/`](20261022-pi-checks/):

- `software-acceptance.json`: output acceptance ARM asli, tidak mengandung data orang.
- `camera-summary.json`: ringkasan diagnostik tanpa titik tubuh pribadi.
- `deployment-summary.json`: status setelah restart, hash asset dan batas tes.

Verifikasi Mac tambahan pada source yang dipaketkan: **119 backend tests**,
**30 web tests**, TypeScript/Vite build dan asset check 32 snapshot lolos.
Tes SQL/Deno sudah tercatat 21 Oktober; tidak diulang atau diklaim fresh pada
deployment ini karena kontrak cloud tidak diubah.

## Yang masih harus diuji

1. RX UART/COM + TX powered: pilot CSI, profil/rate/gap/loss, inferensi,
   disconnect/reconnect fisik. Tidak menganggap status cloud sebagai CSI hidup.
2. Penataan kamera/pencahayaan tubuh utuh dan postur lokal beranotasi.
3. Event CSI aktual → burst → SQLite → snapshot cloud → event UID/skeleton
   yang sama pada caregiver. Jangan membuat fake event ke production untuk QA.
4. Caregiver ACK/bantuan round-trip, push HP saat app tertutup, reboot fisik,
   offline/recovery panjang dan alarm audio/GPIO. Alarm tetap disabled.
5. Training/validasi lokal accepted, recall/specificity/event metrics dan FAR.
   Fall demo tetap proxy validation **62,5% / 64,9%**, belum target ≥80%/80%.

Tidak ada klaim fall terdeteksi benar, akurasi postur, atau keberhasilan seluruh
produk dari pengujian software dan satu burst diagnostik ini.

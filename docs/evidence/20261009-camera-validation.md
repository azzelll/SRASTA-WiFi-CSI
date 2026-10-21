# Validasi kamera SRASTA — 9 Oktober 2026

## Integrasi yang dipasang

Rilis Pi: `/home/srasta/srasta-edge/releases/20261009-demo-v8-camera-r1`.
SHA-256 paket `artifacts/pi/20261009-camera-release-final.tar.gz`:
`2b24e88cdfaf7899303b7f0e343f2ae282172e4f120f9701ea204f386426c68e`.
Seluruh 59 hash file dalam manifest diperiksa saat ekstraksi di Pi.
Environment tetap memakai symlink ke rilis `20261004-demo-v8`; rilis itu
masih diperlukan.

Alur: anomali model CSI yang masih terkini → satu tangkapan kamera untuk
event tersebut → MoveNet → ringkasan postur → SQLite dan app caregiver.
Kamera juga dapat menangani state `critical` untuk event jatuh yang sah
jika pemeriksaan melewatkan transisi `anomaly`. Simulasi/replay, transport
terputus, inferensi kedaluwarsa, dan event yang sudah diperiksa tidak
memicu tangkapan otomatis. UID mengikat hasil ke kejadian yang benar.

Camera helper menggunakan `/usr/bin/python3` dengan Picamera2; interpreter
MoveNet memakai LiteRT pada environment layanan. Sensor dibuka saat
tangkapan diperlukan dan ditutup setelahnya. Gambar serta keypoint tidak
disimpan atau dikirim oleh integrasi ini; penyimpanan/sinkronisasi hanya
memuat UID, waktu, outcome, teks, dan latensi. Kontrak cloud menolak field
gambar/keypoint dan outcome yang mengaku sebagai konfirmasi jatuh.

## Model dan uji kamera asli

[MoveNet Lightning INT8 v4](https://www.tensorflow.org/hub/tutorials/movenet)
diunduh dari sumber resmi Google. SHA-256:
`cd7cc22fa946e5d146a7b98d496853e1923e22828d3972d579973f27f91bb105`.
Input `[1,192,192,3]` uint8 RGB, output `[1,1,17,3]` float32.
Gambar penuh 640×480 dipertahankan dengan letterbox. MoveNet memperkirakan
pose; aturan arah torso menghasilkan bukti pendukung postur, bukan model
klasifikasi jatuh terlatih. Threshold dan state machine fall CSI tetap sama.

Uji `camera_acceptance.py` memakai kamera OV5647 asli dan model pada Pi,
dengan pemicu sintetis terisolasi serta database sementara. Tidak membuat
event pada database live atau mengirim peringatan cloud.

- Normal tidak mengaktifkan kamera; anomali terisolasi memicu satu tangkapan.
- Event yang sama tidak ditangkap ulang; kamera tidak aktif setelah selesai.
- Capture + inferensi berhasil, latensi **2.235,36 ms**.
- Outcome **`uncertain`**, teks **“Keypoint tubuh kurang andal”**.
- Gambar tidak disimpan; event cloud tidak dikirim.

Bukti lokal: `artifacts/pi/20261009-camera-check/20261009-camera-acceptance.json`.
Uji ini membuktikan jalur kamera/model; kualitas postur masih perlu diperiksa
dengan tubuh terlihat utuh dan pencahayaan cukup.

## Layanan, dashboard, dan cloud sebelum dihentikan

Readback pada 9 Oktober pukul 01.02 WIB menunjukkan unit aktif,
`NRestarts=0`, kamera tersedia namun tidak aktif, dan cloud terhubung.
Supabase mengembalikan ringkasan kamera yang sama. Dashboard Pi menampilkan
**Validasi kamera — Siap saat anomali**. RX tidak terpasang: source
`unavailable`, serial terputus, frame valid 0, dan belum ada event live.

App caregiver produksi: <https://srasta-caregiver.vercel.app>.
Deployment Vercel pada sesi ini: `dpl_AeYGibBhEGeQzeASKKna9vb8LTgC`;
fungsi `edge-sync` juga diperbarui. Hasil kamera hanya muncul pada event
dengan UID yang sesuai; hasil global tidak ditempelkan ke event lain.

Bukti lokal pada `artifacts/pi/20261009-camera-check/`:

- `20261009-camera-ready.json`: status layanan Pi dan kamera.
- `cloud-readback.json`: ringkasan yang benar-benar tersimpan di Supabase.
- `camera-ready-dashboard.jpg`: tampilan sebelum layanan dihentikan.
- `python-tests.log`: 41 tes lulus.
- `web-tests.log`: 10 tes lulus, TypeScript dan Vite build berhasil.
- `cloud-contract-tests.log`: 5 tes kontrak lulus.

## Penghentian sesuai permintaan user

`systemctl --user stop srasta-edge.service` berhasil: `MainPID=0`,
`ActiveState=inactive`, `SubState=dead`. Pemeriksaan proses tidak menemukan
runtime SRASTA atau preview/capture kamera. Autostart tetap `enabled`.
Percobaan `sudo -n /sbin/poweroff` ditolak oleh autentikasi Pi:
`sudo: a password is required`. User diminta menjalankan `sudo poweroff`
langsung pada terminal Pi, lalu mengonfirmasi selesai. Pemeriksaan SSH
berikutnya timeout; tunnel dashboard di Mac berakhir dengan koneksi ditutup
oleh Pi. Tidak ada lagi tunnel sesi ini. Ini konsisten dengan shutdown yang
dilaporkan user; penghentian daya listrik TX/RX/adaptor perlu dilakukan fisik.
Bukti lokal: `artifacts/pi/20261009-camera-check/shutdown-status.json`.

## Bukti yang masih diperlukan

- Pemicu dari CSI asli ke kamera dan event caregiver, setelah RX kembali
  terpasang serta TX mendapat daya.
- Validasi postur lokal beranotasi dengan framing tubuh utuh.
- Dampak kamera pada false alert, recall, dan specificity; belum diukur.
- Boot ulang rilis kamera ini belum diuji. Autostart rilis sebelumnya sudah
  pernah diuji, tetapi bukan bukti boot kamera rilis baru.

Tidak ada klaim deteksi jatuh benar, peningkatan akurasi, atau pengurangan
false alert dari satu tangkapan diagnostik tersebut.

# Operasi Pi SRASTA

Checkpoint terakhir: **22 Oktober 2026**. Periksa ulang status sebelum memakai
perangkat. [Bukti pengujian](evidence/20261022-pi-deployment.md) mencatat batasnya.

## Masuk dan jalankan layanan

Dari terminal **Mac**, boleh dari folder mana saja:

```bash
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=3 srasta@srasta-edge.local
```

Mac dan Pi harus satu jaringan yang mengizinkan koneksi antardevice. IP DHCP
bisa berubah setiap jaringan/hotspot terhubung ulang. Jika mDNS tidak bekerja,
lihat `hostname -I` di terminal Pi/daftar perangkat router, lalu gunakan IP yang
baru. `Connection refused` berarti koneksi ke alamat tersebut ditolak; periksa
bahwa alamat benar milik Pi dan SSH aktif, bukan langsung mengganti SSH key.
`Permission denied (publickey,password)` berbeda: server terjangkau, autentikasi
belum diterima. Masukkan password langsung di terminal, jangan di chat/Git.

Setelah prompt menjadi `srasta@srasta-edge`, perintah berikut juga **tidak
memerlukan folder tertentu**:

```bash
systemctl --user start srasta-edge.service
systemctl --user status srasta-edge.service --no-pager
systemctl --user show srasta-edge.service -p WorkingDirectory -p ActiveState -p SubState -p NRestarts
curl -fsS http://127.0.0.1:8000/health
```

Release yang diperiksa: `~/srasta-edge/releases/20261022-demo-v8-camera-burst-r3`.
Layanan memakai akun `srasta`, bukan `sudo systemctl`. Perintah lain:

```bash
systemctl --user stop srasta-edge.service
systemctl --user restart srasta-edge.service
systemctl --user is-enabled srasta-edge.service
loginctl show-user srasta -p Linger
```

`enabled` + `Linger=yes` sudah diperiksa. Restart service sudah diuji; boot fisik
release ini belum. Untuk uji boot, jalankan `sudo reboot` di Pi, tunggu Pi kembali,
SSH lagi, lalu ulangi pemeriksaan status/health. Jangan reboot saat merekam data.
Untuk shutdown gunakan `sudo poweroff`, tunggu shutdown selesai sebelum cabut
daya. Setelah poweroff, pasang ulang adaptor untuk menyalakan Pi.

## Cek CSI setelah board tersedia

RX harus memakai konektor **UART/COM** ke USB Pi; TX cukup diberi daya.
Jangan mengubah Wi-Fi Pi menjadi jaringan CSI: firmware TX/RX punya jaringan
CSI sendiri, Wi-Fi rumah/hotspot Pi dipakai SSH/cloud.

```bash
ls -l /dev/serial/by-id
systemctl --user restart srasta-edge.service
curl -fsS http://127.0.0.1:8000/health
```

RX yang sebelumnya terverifikasi:
`/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`. Jangan mengganti unit ke
port tebakan; identifikasi ulang jika symlink berbeda. Native USB/JTAG board
ini tidak mengirim JSONL UART. Pastikan tidak ada serial monitor/recorder lain.

`/health.ok=true`, `serial_connected=true`, `stream_recent=true` dan
`accepted_frames` bertambah menunjukkan jalur menerima paket. Ini belum
membuktikan akurasi deteksi. Gunakan aktivitas biasa, jangan sengaja jatuh.
Jika RX belum terpasang, `ok=false`, zero frames dan sumber `unavailable` memang
diharapkan; cloud tersambung tidak berarti CSI tersedia.

Ringkasan tanpa frame/event/pose pribadi:

```bash
python3 - <<'PY'
import json, urllib.request
def read(path):
    return json.load(urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=5))
snapshot, status = read('/api/caregiver'), read('/status')
summary = {k: snapshot[k] for k in (
    'source', 'monitoring_online', 'state_verified', 'accepted_frames',
    'quarantined_frames', 'capture_rate_hz', 'blynk_connected')}
summary['transport'] = {k: status['transport'].get(k) for k in ('connected', 'running', 'reconnects')}
summary['camera'] = {k: snapshot['camera'].get(k) for k in ('available', 'active', 'result')}
summary['cloud'] = {k: snapshot['remote'].get(k) for k in ('enabled', 'connected', 'worker_running')}
print(json.dumps(summary, indent=2))
PY
```

Jika perlu log, lihat langsung di Pi dengan
`journalctl --user -u srasta-edge.service -n 40 --no-pager`; tinjau sebelum
dibagikan. Credential ada di `~/srasta-edge/edge.env` mode 0600, jangan dicetak.

## Kamera diagnostik, tanpa alert production

Orientasi dudukan diperbarui 26 Oktober 2026 atas permintaan pemilik:
`camera_capture.py` memutar gambar **180 derajat** sebelum letterbox dan
inferensi MoveNet. RGB, pandangan penuh dan bentuk input 192x192 dipertahankan.
Untuk foto manual dengan orientasi yang sama, gunakan
`rpicam-still --nopreview --rotation 180 --timeout 2000 --output /tmp/srasta-camera-180.jpg`.
Tes `test_camera_capture.py` memakai Python OS dengan NumPy/Pillow; tes
`test_camera.py` memakai venv inferensi dengan dependensi backend.

Tes orang dan skeleton dari terminal **laptop Mac**, sebelum masuk SSH:

```bash
cd "/Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_CSI_Bench_Blynk"
bash scripts/test_camera_skeleton.sh --prepare 10
```

Berdiri normal dengan kepala sampai kaki terlihat kamera dan cahaya cukup.
Sesudah countdown, skrip memakai key Pi lokal yang sudah terdaftar, menjeda
service edge, dan menjalankan burst tiga frame dengan MoveNet pada runtime
aktif. Service dipulihkan otomatis. Laptop membuka `skeleton.html`; ringkasan
`result.json` disimpan di `artifacts/private/camera-skeleton/CAM_*/` yang ignored.
Hanya koordinat terukur yang dibawa ke laptop, tanpa foto atau alert produksi.
Titik berskor di bawah 0,30 dan tulang yang terhubung ke titik tersebut tidak
digambar; pose yang terlalu sedikit/berimpit tampil sebagai belum jelas.
Ini satu cuplikan skeleton dari burst, bukan video langsung atau bukti akurasi.
Gunakan `--no-open` untuk menyimpan laporan saja; `--key` dan `--host` tersedia
jika akses SSH berbeda. Tidak perlu jatuh saat tes.

Kamera tetap idle sampai ada kejadian model terkini. Preview kamera lain harus
ditutup sebelum tes. Jalankan blok ini di Pi; ia memulihkan layanan jika
sebelumnya aktif, termasuk ketika tes gagal. Output memuat koordinat pose,
jadi lihat lokal dan jangan commit hasil lengkapnya.

```bash
(
  set -eu
  SRASTA_WAS_ACTIVE=$(systemctl --user is-active srasta-edge.service || true)
  trap 'if [ "$SRASTA_WAS_ACTIVE" = active ]; then systemctl --user start srasta-edge.service; fi' EXIT
  systemctl --user stop srasta-edge.service
  cd "$HOME/srasta-edge/releases/20261022-demo-v8-camera-burst-r3"
  .venv/bin/python code/camera_acceptance.py \
    --model artifacts/models/movenet-lightning/model.tflite \
    --camera-python /usr/bin/python3
)
```

Tes menggunakan sensor asli dan **pemicu sintetis terisolasi**, tiga frame,
sekali per event, tanpa mengirim event/foto ke cloud. `software_passed=true`
bukan bukti postur benar. Pada 22 Oktober hasil masih “Keypoint tubuh kurang
andal”. Atur pencahayaan dan arah kamera agar tubuh utuh terlihat, kemudian
uji lagi. Tidak perlu menjatuhkan diri. Horizontal bukan kepastian tidur/jatuh.

Dashboard Pi bisa diperiksa dari Mac melalui tunnel (terminal Mac terpisah):

```bash
ssh -N -L 8000:127.0.0.1:8000 srasta@srasta-edge.local
```

Buka <http://127.0.0.1:8000>. Ini app lokal Pi; app caregiver remote tetap
<https://srasta-caregiver.vercel.app>. Uji diagnostik terisolasi tidak muncul
sebagai peringatan live di kedua app.

## Backup dan rollback release 22 Oktober

Backup privat sebelum perubahan:
`~/srasta-edge/backups/20261022-before-camera-burst-20261022T035039Z/`.
Isinya unit sebelumnya, backup SQLite konsisten dan `rollback.json`. DB live
tetap `~/srasta-edge/state/live.sqlite3`; migrasi menambah kolom `pose_json`.
Config credential tetap pada path semula, tidak dipindah ke paket/Git.

Jika release baru perlu dibatalkan, jalankan di Pi:

```bash
systemctl --user stop srasta-edge.service
cp "$HOME/srasta-edge/backups/20261022-before-camera-burst-20261022T035039Z/srasta-edge.service" \
  "$HOME/.config/systemd/user/srasta-edge.service"
chmod 600 "$HOME/.config/systemd/user/srasta-edge.service"
systemctl --user daemon-reload
systemctl --user start srasta-edge.service
systemctl --user show srasta-edge.service -p WorkingDirectory -p ActiveState
```

Ini mengembalikan runtime 9 Oktober, mempertahankan DB live. Jangan menimpa DB
dengan backup tanpa meninjau data kejadian baru; penambahan kolom kompatibel
dengan reader lama. Backup DB disediakan untuk pemulihan terpisah.
Rollback terakhir disiapkan tetapi belum dicoba setelah instalasi sukses.

Environment rilis baru adalah symlink ke
`~/srasta-edge/releases/20261004-demo-v8/.venv`. Semua delapan versi pin cocok
dan `pip check` lolos; tidak ada pip install yang mengubah environment bersama.
**Jangan hapus release 4/9 Oktober atau menjalankan pip upgrade pada environment
bersama.** Upgrade dependensi berikutnya perlu venv baru agar rollback utuh.

Untuk mengambil data, gunakan [capture quickstart](CAPTURE_QUICKSTART.md).
Recorder membutuhkan clone repo lengkap, bukan folder runtime ini. Hentikan
service sebelum recorder membuka RX, lalu jalankan lagi sesudahnya.

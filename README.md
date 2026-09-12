# SRASTA — local caregiver product

SRASTA memproses WiFi CSI secara lokal dan menampilkan lima status caregiver: **standby, normal, inactive, anomaly, critical**. Ruang lingkup mengikuti [proposal produk](https://docs.google.com/document/d/15EJxdUXP2X9X5V8FEKO8p9wN2s1fkgW3l0qTIBnsN_s/edit), `AGENTS.md`, `AGENT.md`, dan `AI_CONTEXT.md`.

```text
ESP32-S3 TX / hotspot HP yang dikonfigurasi
  -> ESP32-S3 RX LLTF/HT20 -> USB JSONL
  -> validasi, amplitude [time,52], preprocessing bersama, model/aturan
  -> lima status, SQLite, alarm lokal
  -> FastAPI + WebSocket -> dashboard navy/PWA
  -> opsional Blynk/MQTT (nonaktif secara default)
```

**Status bukti:** aplikasi lokal tersedia, termasuk simulator berlabel, replay, serial, riwayat/acknowledgement, estimasi napas dengan penahanan saat kualitas rendah, adapter kamera saat anomali, dan notifikasi opsional. Kandidat model tetap **belum layak deployment**. Lihat [bukti engineering](ENGINEERING_EVIDENCE.md) untuk hasil aktual dan batasnya; keberhasilan simulator bukan bukti deteksi jatuh.

## Mulai di Windows

Jalankan dari root repository ini menggunakan Python 3.12:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r code/requirements-train.txt -r code/requirements-dev.txt
.venv/Scripts/python -m playwright install chromium
.venv/Scripts/python code/run_edge_service.py --demo --db artifacts/demo.sqlite3
```

Buka **http://127.0.0.1:8000**. Panel lab menguji kelima status. Simulator tidak mengaktifkan kamera, GPIO, atau notifikasi eksternal. Tombol panggilan membuka dialog nomor; panggilan hanya diserahkan ke perangkat setelah caregiver menekan **Mulai panggilan**.

```powershell
.venv/Scripts/python code/tools/verify_local.py
```

Perintah tersebut memulai server simulator sementara, menjalankan seluruh unit/API/replay test serta pengujian browser desktop/ponsel/offline, lalu menghentikan server miliknya sendiri. Dependensi atau dataset yang hilang menghasilkan kegagalan, bukan skip tersembunyi. Tambahkan `--firmware` untuk build TX/RX setelah setup toolchain.

- [RUNBOOK_LOCAL.md](RUNBOOK_LOCAL.md): setup, dataset, training, replay, semua status, tes, dan recovery.
- [HARDWARE_SETUP.md](HARDWARE_SETUP.md): topologi hotspot satu RX, konfigurasi privat, build/flash, verifikasi serial, Pi/kamera/alarm.
- [ENGINEERING_EVIDENCE.md](ENGINEERING_EVIDENCE.md): perintah dan hasil terukur terbaru.
- [ENGINEERING_CHECKLIST.md](ENGINEERING_CHECKLIST.md): selesai, belum terbukti, dan blocker eksternal.

## Kontrak dan privasi

LLTF-only HT20, tepat 128 signed byte `[imaginary,real]`; `hypot` dan indeks tetap `6..31,33..58` menghasilkan 52 fitur. Tidak ada resize/padding/pergeseran fitur. Sender, metadata, urutan, timestamp, dan profil divalidasi; frame tidak kompatibel ditolak. Gap memulai ulang pengumpulan jendela. Data terputus tidak membuktikan pengguna diam atau napas berhenti.

Raw CSI hanya diproses di memori; SQLite/API/dashboard/notifikasi menyimpan ringkasan tanpa MAC/password/video. Kamera membuka perangkat hanya atas anomali dan menghasilkan keypoint, lalu ditutup. GPIO dan layanan eksternal membutuhkan konfigurasi eksplisit. Dashboard default terbatas ke loopback dan memakai pemeriksaan origin/host serta token sesi untuk mutasi. Service worker hanya menyimpan shell statis, tidak status/event/token.

Dataset publik tetap lokal, tidak diunggah atau diubah. Split U21 tetap terkunci dan tidak diunduh. Artefak `data/`, model, database, credential, dan hasil build diabaikan Git. Notebook serta `code/runs/` pengguna dipertahankan. Preprocessing versi `causal-v2-raw-history` menolak konfigurasi lama; model harus dilatih ulang, bukan mengganti hash agar terlihat cocok.

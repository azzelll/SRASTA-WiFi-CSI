# Development langsung di Raspberry Pi 4B

Checkpoint 22 Oktober 2026. Dependency, build dan tes dijalankan melalui SSH
pada Pi ARM64. Komputer Windows hanya menjadi terminal/penyunting.

## Folder

| Peran | Lokasi pada Pi |
| --- | --- |
| Clone lengkap | `/home/srasta/SRASTA-WiFi-CSI` |
| Branch | `handoff/2026-10-21` |
| Commit dasar | `ac1dc33069d8701d626d61e88b32611231df21c2` |
| Venv development baru | `/home/srasta/SRASTA-WiFi-CSI/.venv` |
| Node 22.19.0 ARM64 | `/home/srasta/.local/share/srasta-tools/node-v22.19.0-linux-arm64/bin` |
| Log pemeriksaan | `artifacts/setup/20261022-pi-setup/` dalam clone |
| Runtime aktif | `/home/srasta/srasta-edge/releases/20261022-demo-v8-camera-burst-r3` |
| Service runtime | `srasta-edge.service`, localhost port 8000 |
| Simulator terpisah | `srasta-setup-simulator.service`, localhost port 18735 |

Python Pi adalah 3.13.5. Node resmi dipasang dalam direktori user setelah hash
arsip diverifikasi dengan SHASUMS256.txt dari nodejs.org. Environment
production/rollback bersama tidak di-upgrade atau diganti.

## Dependency development

Pada clone baru, gunakan venv baru. Jangan menjalankan instalasi ini pada
venv release produksi yang merupakan symlink ke release 4 Oktober.

```bash
cd ~/SRASTA-WiFi-CSI
python3 -m venv .venv
.venv/bin/python -m pip install -r code/requirements-pi-dev.txt
.venv/bin/python -m pip check
python3 scripts/check_handoff_assets.py
```

Requirements development menyertakan TensorFlow untuk tes export INT8, LiteRT
untuk inferensi, dan Pillow untuk tes letterbox kamera. Ini bukan dependency
minimal deployment. Picamera2 tetap memakai Python OS pada runtime kamera.

## Mengulang tes dan build

```bash
cd ~/SRASTA-WiFi-CSI
PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 \
.venv/bin/python -m unittest discover -s code/tests -v

export PATH="$HOME/.local/share/srasta-tools/node-v22.19.0-linux-arm64/bin:$PATH"
cd web
npm ci --no-audit --no-fund
npm test
VITE_ACCESS_MODE=local VITE_SUPABASE_URL= \
VITE_SUPABASE_PUBLISHABLE_KEY= VITE_VAPID_PUBLIC_KEY= npm run build
npm run test:cloud
cd ..
npm exec --yes --package=deno@2 -- deno test --no-check \
  supabase/functions/edge-sync/contract_test.ts
```

Tes SQL menggunakan PGlite lokal; tes Deno tidak melakukan typecheck penuh.
Keduanya tidak mengirim event/command ke Supabase produksi.

## Simulator

Simulator yang sedang berjalan memakai unit user **transient**, bukan
autostart produksi. Unit ini hilang saat Pi reboot. Startup mengosongkan
environment eksternal; alarm disabled, tanpa sensor kamera/cloud/Blynk.
DB-nya `artifacts/caregiver_simulator.sqlite3`, terpisah dari DB live.

```bash
systemctl --user show srasta-setup-simulator.service -p ActiveState -p WorkingDirectory
curl -fsS http://127.0.0.1:18735/api/caregiver
```

Untuk menghentikan simulator:

```bash
systemctl --user stop srasta-setup-simulator.service
```

Untuk menjalankannya lagi secara foreground setelah stop/reboot:

```bash
cd ~/SRASTA-WiFi-CSI
env -i HOME="$HOME" PATH=/usr/bin:/bin LANG=C.UTF-8 \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
bash scripts/run_local.sh simulator --alarm disabled --port 18735
```

Pastikan `source=simulator` dan `simulation=true`. Pengendali simulasi menguji
lima status UI; hasilnya bukan pengukuran orang, CSI atau akurasi. Jangan
mengirim request demo ke port produksi 8000.

## Membuka app Pi dari Windows

Jalankan pada CMD/PowerShell Windows baru, lalu biarkan terminal terbuka:

```powershell
ssh -i C:\Users\LENOVO\.ssh\srasta_codex_setup_20261022 -o IdentitiesOnly=yes -N -L 127.0.0.1:18000:127.0.0.1:8000 -L 127.0.0.1:18735:127.0.0.1:18735 srasta@10.129.224.155
```

- http://127.0.0.1:18000 adalah runtime Pi yang sudah terpasang.
- http://127.0.0.1:18735 adalah simulator Pi terpisah.

Gunakan IP Pi saat ini bila DHCP berubah. Binding API/forwarding hanya
loopback; tidak mengubah SSH daemon atau membuka port publik. Private key
tetap di luar Git. Izin browser otomatis tidak diberikan pada checkpoint
ini, sehingga tampilan visual belum diverifikasi oleh agen.

## Sesudah TX/RX tersedia

Runtime produksi tetap aktif dan tidak direstart selama setup ini. Saat
pemeriksaan RX/TX belum terpasang: source unavailable, monitoring offline,
state unverified, zero frames. Kamera tersedia tetapi idle; tidak mengambil
gambar baru.

Identifikasi RX UART/COM dan daya TX, kemudian ikuti
[capture quickstart](CAPTURE_QUICKSTART.md) untuk pilot 15 detik. Satu RX
hanya satu reader; hentikan service pembaca RX sebelum menjalankan recorder.
Label, split orang dan review manusia harus benar, bukan berasal dari model.

Fall v8 tetap demo dengan proxy validation historis recall 62,5% /
specificity 64,9%; belum target 80%/80%. Presence/breathing publik tetap
research-only. Tidak melatih atau mengganti model release dalam setup ini.

[Bukti pengujian](evidence/20261022-pi-software-reproduction.md).

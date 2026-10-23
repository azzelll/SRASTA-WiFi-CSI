# Integrasi handoff dan panel Pi ke main — 23 Oktober 2026

Pemilik meminta pemeriksaan push teman pada handoff 21 Oktober, kemudian
meminta pembaruan tersebut masuk ke `main`. Pemeriksaan origin dan GitHub
menemukan PR #2 dari `rafasoelistiono:codex/pi-device-panel-20261023`, commit
`d24b3e4088d33fdceb2ab302e54e8f99e91e8c9f`, dengan dasar handoff `394e6a3`.
Branch handoff origin sendiri belum memuat commit panel tersebut.

PR #2 diarahkan dari `handoff/2026-10-21` ke `main`, lalu digabung dengan
expected head SHA di atas. GitHub mengonfirmasi merged pada commit
`83bb1b7390b14bfb7a4f08522c079705e734d4fc`.
`git diff --quiet d24b3e4 83bb1b7` lulus: tree hasil merge identik dengan
kandidat yang diuji. Tidak ada konflik atau perubahan source tambahan.
README, HANDOFF dan prompt AI diperbarui agar clone memakai `main`.

## Verifikasi fresh pada Mac

CPython 3.12.13, Node 24.11.1, npm 11.6.2. Command dari root repo:

```bash
PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 \
.venv/bin/python -m unittest discover -s code/tests -v
python3 scripts/check_handoff_assets.py
bash -n scripts/test_devices.sh scripts/collect_local_csi.sh \
  scripts/run_local.sh scripts/run_pi_demo.sh scripts/install_pi_demo.sh
cd web
npm test
VITE_ACCESS_MODE=public npm run build
npm run test:cloud
cd ..
git diff --check
```

| Pemeriksaan | Hasil |
| --- | --- |
| Backend | 128 tes dijalankan, 127 lulus, 1 skip platform; 9,926 detik |
| Skip platform | Tes termios Linux 1.000.000 baud; konstanta B1000000 tidak tersedia di Mac |
| Web | 37 tes / 9 file lulus |
| TypeScript dan Vite public build | Lulus; 1.630 modul, JS 492,45 kB sebelum gzip |
| Cloud SQL lokal | PGlite migration/RLS, isolasi tenant, command/receipt, public RPC dan push queue lulus |
| Aset handoff | 32 diperiksa, 0 kegagalan |
| Shell syntax | Lima script lulus bash -n |

Tidak ada dependency test yang dilewati dan dihitung lulus. Tes Linux dan
pengujian perangkat Pi yang dilaporkan kontributor tetap merupakan checkpoint
terpisah pada [bukti panel](20261023-device-panel.md) dan
[reproduksi ARM64](20261022-pi-software-reproduction.md).

Pemeriksaan ini tidak mengoperasikan Pi, GPIO, kamera atau sumber CSI,
melatih model, mengirim notifikasi, maupun memasang ulang runtime/cloud.
Model dan metrik akurasi tidak berubah. Main berisi snapshot model dan indeks
yang sudah dipublikasikan pada handoff; tidak menambahkan raw recording,
credential, database, atau output eksperimen baru.

# Checkpoint handoff GitHub — 21 Oktober 2026

## Cakupan

Pemilik meminta seluruh pekerjaan proyek yang relevan dipush dan disiapkan
untuk dilanjutkan AI anggota tim. Cabang baru `handoff/2026-10-21` memuat
checkout Mac/Pi terbaru. Cabang remote September pada `92f5985` tetap utuh;
tidak force-push atau mengganti implementasi remote itu secara diam-diam.

Handoff menambahkan `HANDOFF.md`, panduan capture, prompt AI, indeks model/hash,
placeholder web environment, dan pin versi development yang telah digunakan.
Source firmware/backend/AI/web/cloud, tes, script serta bukti bertanggal ikut.
`code/start_demo.sh` kini meneruskan ke simulator resmi, tanpa port/model usang
atau `pkill` luas. Packer menyertakan license MoveNet. `.DS_Store`, cache clangd,
cache proposal/log AI, raw CSI, secret dan DB lokal tidak dipublikasikan.

Selected weights/config serta metadata split yang disetujui pemilik ikut Git:
32 berkas, 26.237.930 byte. Tidak ada source recording, per-record prediction
archive atau seluruh folder eksperimen. `data/curated` hanya metadata index;
CRLF aslinya dipertahankan untuk menjaga hash. Model lama invalid tidak dipilih.

## Pemeriksaan fresh pada snapshot file Git

File staged diekspor dengan `git checkout-index` ke folder baru di luar repo.
Tidak ada `.env`, raw corpus, DB live atau model untracked yang terbawa.
Python memakai virtualenv development yang sudah ada; `node_modules` ditautkan
ke instalasi terkunci yang sudah ada. Jadi ini membuktikan kelengkapan **file
source/aset dari index**, bukan pemasangan dependency dari internet pada mesin
bersih atau kompatibilitas semua OS.

Lingkungan: macOS ARM64, Python 3.12.13, Node v24.11.1.

| Pemeriksaan | Hasil aktual |
| --- | --- |
| `python3 scripts/check_handoff_assets.py` | 32/32 ukuran dan SHA-256 cocok |
| `PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 <venv>/bin/python -m unittest discover -s code/tests -v` | 119 tests, 7,432 detik, OK; tidak ada skip |
| `npm test` dari `web/` | 7 file, 30 tests lulus |
| `npm run build` dari `web/` | TypeScript + Vite lulus; 1.630 modules; JS `index-jGrE46tZ.js` |
| `npm run test:cloud` dari `web/` | PGlite migration, anonymous deny, tenant isolation, command/receipt idempotency, push lease/dedup dan membership revocation PASS |
| `deno test --no-check --cached-only supabase/functions/edge-sync/contract_test.ts` | 6 lulus, 0 gagal; tanpa typecheck penuh |
| `bash -n` pada wrapper capture/local/Pi/install/start_demo | Lulus |
| `SRASTA_PYTHON=<venv>/bin/python bash scripts/collect_local_csi.sh --help` | Exit 0 dari snapshot; tidak membuka port hardware |
| Simulator dari wrapper, env `/dev/null`, alarm disabled, port localhost 18735 | HTTP `/` dan `/api/caregiver` 200; `source=simulator`; server ditutup setelah tes |
| `git diff --cached --check` | Lulus; atribut mempertahankan CSV dan license upstream |

Percobaan HTTP pertama ditolak sandbox pada `bind()` (`operation not permitted`)
setelah startup. Pengulangan dengan izin lokal yang sesuai lulus. Tidak ada
perubahan pada runtime untuk menyembunyikan error itu. Bukti ringkas:
[`simulator-http.json`](20261021-handoff-checks/simulator-http.json).

## Rebuild dan acceptance paket

Command dari snapshot setelah build web:

```bash
<venv>/bin/python scripts/pack_pi_demo.py \
  --output /private/tmp/srasta-handoff-rebuilt-pi.tar.gz \
  --camera-model artifacts/models/movenet-lightning/model.tflite \
  --research-run artifacts/research/20261019-occupancy-calibrated
# Ekstrak ke folder baru, lalu jalankan script dari hasil ekstraksi:
<venv>/bin/python code/pi_acceptance.py --output /private/tmp/srasta-handoff-pi-acceptance.json
```

Arsip: 25.179.862 byte, 136 file termasuk manifest (135 hash payload).
SHA-256 build ini:
`e0470456bed6c2079d1f60491f57ffcf88b21f42a4045cc776805497f038d2f3`.
Tar menyimpan metadata build, jadi rebuild berikutnya tidak harus punya hash
arsip identik; per-file hashes tetap diverifikasi oleh manifest.

Acceptance dari paket hasil ekstraksi lulus di **Mac ARM64**, bukan Pi:
integritas 135 file, route app, loading/inferensi sintetis TFLite, dua model
publik, tiga model riset, dan COCO17 MoveNet. Sensor kamera tidak dibuka.
Model riset tetap `local_deployment_ready=false`, tidak diaktifkan live.
[`package-acceptance-mac.json`](20261021-handoff-checks/package-acceptance-mac.json)
mencatat detail dan batasnya. Arsip sementara ini tidak perlu di-commit karena
dapat dibangun dari file yang disertakan.

## Pemeriksaan publikasi dan batas yang tersisa

Seluruh blob pada staged tree diperiksa pola private key/token/JWT, nama path
terlarang, symlink dan ukuran. Tidak ditemukan credential cocok, raw H5/JSONL,
DB, symlink, cache privat atau file ≥50 MB. Dua assignment dokumentasi cloud
adalah placeholder yang ditinjau. Ini pemeriksaan pola terbatas, bukan audit
keamanan menyeluruh. Secret `.env` asli tidak dibaca/disalin untuk publikasi.

Tidak dilakukan training ulang, pengambilan data manusia, flash ESP32,
instalasi Pi, akses kamera, deploy cloud/web baru, notifikasi production atau
uji HP pada checkpoint ini. Karena itu tidak ada peningkatan recall/specificity
atau klaim keberhasilan live baru. Model v8 dan gap pada `HANDOFF.md` tetap.

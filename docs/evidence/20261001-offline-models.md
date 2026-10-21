# Model dan pipeline tanpa pengambilan data baru

Tanggal: 1 Oktober 2026. Scope breathing yang diminta pengguna adalah
`sleep / normal / empty`; `normal` berarti orang terjaga. Klasifikasi ini
terpisah dari estimator angka napas/menit yang sudah ada.

Tidak ada rekaman baru, akses serial, flash board, upload corpus, atau commit
artifact dalam pekerjaan ini. Training memakai sumber lokal yang sudah ada.
Default layanan tetap paket v8.

## Hasil training

| Pekerjaan | Data dan split | Hasil | Keputusan |
| --- | --- | --- | --- |
| Fall v9: level + adjacent difference | Primary ESP32-S3: train 288, validation U19 77 | Recall 52.5%; specificity 62.16%; INT8 parity passed | Tidak menggantikan v8. |
| Fall v10: TCN + temporal moments | Split primary yang sama | Recall 50%; specificity 78.38%; INT8 parity passed | Tidak menggantikan v8. |
| Fall v11: grouped motion encoder transfer | Source-train ESP-Fi encoder; fine-tune dan representative quantization primary train; validation U19 | Recall 75%; specificity 40.54%; INT8 parity passed | Tidak menggantikan v8. |
| Motion TCN tujuh kelas, relative | ESP-Fi source-train: subjek 2–7 train 420; subjek 8 validation 70; source test subjek 1 tidak dibuka | Accuracy 35.71%; macro F1 0.333; INT8 parity passed | Artifact penelitian. |
| Motion TCN tujuh kelas, log difference/raw Hampel | Split ESP-Fi yang sama | Accuracy 40%; macro F1 0.378; INT8 parity passed | Encoder penelitian terpilih dari dua konfigurasi; belum valid untuk ESP32-S3 lokal. |
| Public HAR native baseline | Source-train CSI-Bench saja; U06 validation; pengguna lain train; maksimal 400 per kelas per split | Accuracy 31.49%; macro F1 0.304 | Baseline penelitian; bukan model aktivitas lokal. |
| Breathing native baseline v2 | Source-train CSI-Bench saja; U06 train, U23 validation; 2,000 per kelas per split | Accuracy 50%; macro F1 0.333; empty recall 0%, sleep recall 100% | Gagal membedakan kelas pada domain validation; belum layak dipasang ke edge. |

**Target fall recall 88% / specificity 80% belum tercapai.** Paket v8 tetap
dipakai layanan: recall 62.5%, specificity 64.86% pada validation. Semua angka
fall merupakan proxy label rekaman, bukan recall event lokal. U21 tidak dibuka
atau digunakan untuk pemilihan kandidat dalam pekerjaan ini.

Motion memakai label asli `arm_wave`, `fall`, `jump`, `run`, `squat`, `turn`,
`walk`. Head tujuh kelas disimpan bersama encoder dan ekspor INT8; runtime
fall menolak head penelitian tersebut. Transfer v11 membuang head sumber dan
melatih head binary serta kalibrasi INT8 dengan data primary saja.

Breathing publik hanya mempunyai `sleep/empty`; U24 dikeluarkan karena tidak
mempunyai `empty`. Native channels dipertahankan; fitur statistik/spektral
diringkas tanpa padding/resizing carrier menjadi 52. Perbedaan user, perangkat,
dan ruangan antarpartition membatasi interpretasi skor. Ini bukan benchmark
resmi atau validasi ESP32-S3. HAR memiliki label `seated-breathing`, tetapi
menggabungkannya dengan corpus sleep membutuhkan audit konteks/asal data;
model tidak diberi label `normal` hasil tebakan.

### Percobaan breathing yang ditolak

Percobaan native pertama mengambil metadata seluruh corpus sebelum filter
source-train diperbaiki, sehingga payload official test publik turut dibaca.
Artifact pertama ditandai `INVALIDATED.md`, tidak menjadi model terpilih,
dan tidak digunakan untuk klaim benchmark/deployment. V2 membatasi payload
ke `train_id.json`, lalu membagi berdasarkan user sebelum sampling. Test
SRASTA tetap tidak dibuka. Test otomatis memeriksa batas source-train.

## Presence dan inactivity

- `code/train_local_presence.py` membaca sesi lokal accepted saja, memakai
  interval direview, dan menuntut train/validation dengan dua label, subjek
  terpisah, serta satu capture profile.
- Local test dan pilot tidak dibaca untuk fitting. Packet gap dan batas
  anotasi memisahkan window; anotasi tumpang tindih ditolak.
- Sesi lokal tersedia masih pending review/provenance. Readiness report
  mempunyai nol window eligible dan tidak menghasilkan model presence.
- `--presence-model` menyambungkan artifact lokal sesuai profil ke edge.
  Artifact breathing/HAR publik tidak dapat menjadi model presence.
- Timer inactivity memakai presence terpisah, motion, dan clock receiver.
  Unknown menghasilkan inactivity unavailable; empty tidak memulai timer.
  Gap, clock reset, reconnect, atau gerak memutus interval.
- Inactivity dipublikasikan sebagai `inactive`, empty sebagai `standby`, dan
  state jatuh tetap memiliki prioritas. Perubahan presence/timer tercatat dalam
  event ledger. `/status` dan `/api/caregiver` membawa presence, inactivity,
  stationary duration, dan field breathing condition yang saat ini null.
- Tidak ada klasifikasi tiga kelas breathing terpasang ke layanan atau
  pembuktian empat kelas dari satu model. UI produksi belum menerima model baru.

## Bukti software

Seluruh **82 tests backend lulus**, tanpa skip. Test tambahan memeriksa batas
timer, unknown/empty occupancy, pemutusan clock, fitur native, penolakan
artifact penelitian, tidak membaca test capture, serta state inactivity/event
ledger hingga API caregiver. Ini bukti software, bukan accuracy perangkat.

Replay satu H5 primary train melewati model v8 dan shared preprocessing.
`/health`, `/status`, `/api/caregiver`, `/events` mengembalikan HTTP 200.
Snapshot menyebut sumber replay/simulation, menjaga monitoring live false,
dan tidak memuat raw CSI/MAC. Presence tetap unknown dan inactivity null
ketika tidak ada classifier presence. Source corpus tidak diubah.

## Menjalankan ulang

Jalankan dari root repository. Gunakan folder output baru; script menolak
menimpa hasil lama. TX/RX tidak diperlukan.

```bash
.venv/bin/python code/train_motion_pretrain.py \
  --normalization-mode log_difference --hampel-history raw \
  --out-dir artifacts/research/new-motion-run

.venv/bin/python code/train_breathing_baseline.py \
  --out-dir artifacts/research/new-breathing-run

.venv/bin/python code/train_public_activity_baseline.py \
  --out-dir artifacts/research/new-har-run

.venv/bin/python code/train_local_presence.py \
  --out-dir artifacts/research/new-presence-readiness

.venv/bin/python code/offline_acceptance.py \
  --model artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/model.tflite \
  --out-dir artifacts/research/new-offline-acceptance

PYTHONPATH=code .venv/bin/python -m unittest discover -s code/tests -v
```

Script training utama juga menyediakan `--architecture difference`,
`--architecture moments`, dan `--architecture compact --pretrained-motion`.
Transfer encoder harus memakai preprocessing yang sama dengan artifact sumber.
Threshold/candidate dipilih dengan validation saja.

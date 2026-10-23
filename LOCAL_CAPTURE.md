# Pengambilan CSI lokal

Untuk setup dari clone, port Mac/Pi, dan arti isian CLI, baca
[panduan tim](docs/CAPTURE_QUICKSTART.md). Panduan ini menjelaskan detail format
dan QA; catatan bertanggal di bagian akhir adalah bukti historis.

## Jalankan satu script

Sambungkan TX dan RX sesuai label fisik. Jaga kedua board di posisi yang sama
sepanjang sesi. Jalankan dari Terminal:

```bash
bash scripts/collect_local_csi.sh --root "$HOME/SRASTA_LOCAL_CAPTURE"
```

Script memakai port RX layanan SRASTA yang sedang berjalan. Jika layanan tidak
aktif, script menampilkan daftar port dan meminta nomor port RX. Posisi USB
MacBook kiri/kanan tidak menentukan peran board. Pilihan manual:

```bash
bash scripts/collect_local_csi.sh --port /dev/cu.PORT_RX
```

Isi kode orang, split, lokasi, ruangan, dan pengamat. Gunakan kode yang sama
untuk orang yang sama pada semua sesi. Jangan memasukkan nama, kontak,
kredensial, atau informasi pribadi. Satu orang hanya boleh mempunyai satu
split; assignment disimpan sebelum merekam dan tidak dapat diganti.

Recorder terbaru memakai urutan subcarrier `esp_idf_native` untuk firmware
RX repository ini. Konfigurasi menyimpan urutan beserta hash; raw I/Q tetap
utuh, sedangkan inferensi memetakan frekuensi ke urutan centered sebelum
mask 52 kanal. Gunakan `--subcarrier-order centered` hanya untuk source yang
sudah diverifikasi berurutan centered. Rekaman sebelum perbaikan 5 Oktober
2026 perlu audit metadata urutan sebelum dipakai untuk fitting; source
rekaman lama tidak diubah atau diam-diam diinterpretasikan ulang.

## Ikuti instruksi di CLI

| Tahap | Yang dilakukan | Waktu default |
| --- | --- | --- |
| Ruangan kosong | Semua orang keluar dari ruangan setelah menekan Enter. Tunggu bunyi akhir sebelum kembali. | Persiapan 20 detik + rekam 3 menit |
| Aktivitas normal | Satu orang berjalan biasa, berbalik, duduk/berdiri, atau mengambil barang ringan bila nyaman. | Persiapan 20 detik + rekam 3 menit |
| Diam/inaktif | Duduk atau berbaring nyaman. Tetap pada posisi tersebut dan bernapas seperti biasa. | Diam awal 61 detik + rekam 3 menit |

Total sekitar **11 menit**, ditambah waktu mengisi metadata dan konfirmasi.
CLI menampilkan countdown, jumlah paket valid, dan karantina. Setiap kondisi
dimulai setelah Anda menekan Enter dan berakhir dengan bunyi terminal.
Setelahnya jawab apakah kondisi benar-benar sesuai selama interval REKAM.
Jika tidak, script menyimpan `aborted_event`, bukan label kelas yang direncanakan.
Pada Mac, wrapper menjaga komputer agar tidak tidur selama script berjalan.

Persiapan, perpindahan posisi, dan waktu menjawab tidak otomatis diberi label.
`inactive` berarti stationary setelah minimum 60 detik, bukan diagnosis medis.
Sesi ini mengumpulkan tiga kelas nonfall. Kelas `fall_anomaly` memerlukan sesi
terpisah di bawah aturan pengambilan jatuh pada
[protokol capture](docs/esp32_s3_capture_protocol.md). Script ini tidak meminta
pengguna melakukan jatuh.

Durasi bisa diperpanjang tanpa mengubah alur:

```bash
bash scripts/collect_local_csi.sh --duration 600 --prepare 30
```

`--duration` berlaku untuk setiap kondisi, minimum 60 detik. Persiapan keluar
ruangan minimum 10 detik. Persiapan inactive tetap memenuhi minimum 60 detik.

## Penyimpanan otomatis

Default:

```text
SRASTA_LOCAL_CAPTURE/          # --root; default berada di sebelah folder repo
  subjects.jsonl                # registry split per orang
  sessions/SES_<tanggal>_<id>/
    capture_config.json        # profil radio, pseudonim, hash, asal model
    frames.jsonl               # CSI signed I/Q asli + semua metadata
    events.jsonl               # label dan waktu pengamat, review pending
    predictions.jsonl          # prediksi model pada clock RX
    quarantine.jsonl           # diagnostik penolakan tanpa raw I/Q
    capture_summary.json       # waktu, jumlah paket, loss, status selesai
    checksums.json             # SHA-256 semua file bukti asli
    qa_report.json             # pemeriksaan awal otomatis
    runtime.sqlite3            # log model terisolasi dari layanan caregiver
```

Folder harus di luar semua working tree Git dan `data/`. Folder berizin 0700,
file 0600; raw MAC hanya berada pada arsip lokal ini. Tidak ada upload cloud,
Git, atau pengubahan corpus publik. Session ID unik; hasil lama tidak ditimpa.
`--root /folder/lokal/lain` dapat mengubah lokasi penyimpanan.

Satu **Ctrl+C** menghentikan sesi, menutup dan menyimpan file, lalu menulis
status incomplete. Interval yang belum dikonfirmasi ditandai aborted.
Disconnect/reconnect/reset RX mengakhiri sesi; script tidak menyambungkan dua
clock receiver menjadi satu rekaman. Jalankan sesi baru setelah koneksi pulih.
Exit code: 0 untuk capture selesai (review boleh masih pending), 2 jika kualitas
archive ditolak, 1 untuk kegagalan, 130 jika dihentikan dengan Ctrl+C.

Recorder memuat model sebelum membuka serial. Jika layanan edge dari checkout
ini memakai RX, script memverifikasi PID, folder kerja, dan argumennya, menjeda
layanan itu, lalu menjalankannya kembali otomatis setelah sesi. Selama rekaman,
dashboard caregiver tidak mendapat update CSI dari layanan live. Serial monitor
lain harus ditutup. App dan database caregiver tidak menerima label/prediksi
pengambilan data ini.

## QA dan review

Pemeriksaan otomatis memeriksa hash, profil 128 I/Q/52 kanal, monotonic clock,
sequence gap, sender yang sama, konsistensi registry split, dan anotasi.
Ambang dideklarasikan sebelum capture: loss maksimal 1%, karantina maksimal
1%, maksimum gap packet 0.15 detik untuk coverage, dan minimum 60 detik
observasi nonfall yang sudah direview. Pelanggaran tidak diperbaiki dengan
padding, reordering, penghapusan paket, atau relabeling.

`pending` setelah sesi normal memang diharapkan: jawaban operator belum sama
dengan review independen. Perlu pengamat kedua yang menyaksikan interval atau
proses referensi sinkron yang disetujui. Kode izin dan provenance cohort baru
juga perlu lengkap. Jika identitas firmware belum diketahui, hasil tetap pending.
Model tidak pernah menentukan ground truth.

Untuk memeriksa ulang, gunakan path session yang dicetak script:

```bash
.venv/bin/python code/tools/qa_capture.py "/path/session"
```

Pengamat kedua **yang menyaksikan kondisi** dapat melakukan review:

```bash
.venv/bin/python code/tools/qa_capture.py "/path/session" --reviewer ANN_002
```

Review ditambahkan ke `reviews.jsonl`; bukti CSI dan anotasi awal tidak diubah.
Report baru berada di `qa_reports/`. Perbedaan pendapat menolak sesi sampai
proses rekonsiliasi yang benar, bukan memilih label menurut prediksi.

## False alert dan empat kelas

Setelah review diterima, perhitungan eksplisit:

```bash
.venv/bin/python code/tools/evaluate_local_alerts.py "/path/session"
```

Penyebut hanya interval nonfall direview dengan coverage prediksi aktual.
Gap packet, warm-up, dan outage inference dikeluarkan. Satu episode suspected
yang berubah menjadi confirmed dihitung satu alert. Tanpa prediksi atau review,
rate adalah unavailable, bukan nol. Episode yang sudah aktif sebelum interval
eligible dicatat sebagai censored, beserta waktu state anomaly pada nonfall.

Laporan memberi false alert per jam dan batas atas Poisson satu sisi 95%.
Rekaman beberapa menit dengan nol alert tidak membuktikan target dua alert per
hari; sekitar 36 jam nonfall tanpa alert dibutuhkan untuk batas atas tersebut.
Angka FAR berbeda dari specificity classifier.

Target **recall 88% / specificity 80%** dan empat kelas belum terpenuhi oleh
script ini. Data baru harus lengkap, direview, memiliki subjek terpisah untuk
train/validation/test, dan mencakup event jatuh dengan empat batas waktu yang
wajib. Training/kalibrasi memakai train dan validation; test yang dibekukan
tidak dipakai memilih model, preprocessing atau threshold. Jangan membuka
kembali U21 untuk tuning. Evaluasi test dilakukan setelah kandidat dibekukan.

## Verifikasi pengembangan, 1 Oktober 2026

- 16 fixture tests recorder dan seluruh 70 tests backend lulus. Suite backend
  mencakup kontrak CSI, timer state, model, adapter dan caregiver.
- Pilot pertama menyimpan 348 frame, loss 13%; QA rejected. Model loading
  memblokir callback USB. Raw pilot tetap disimpan; tidak dipakai training.
- Setelah model dipindahkan sebelum pembacaan serial: pilot nyata 15.1 detik,
  477 frame valid, nol karantina, nol sequence missing, 41 prediksi. Layanan
  dashboard berhasil dijalankan kembali otomatis. Pilot tetap tanpa label dan
  tidak membuktikan deteksi jatuh, FAR, empat kelas, atau target recall/specificity.
- Uji Ctrl+C pada koneksi nyata menyimpan 1.590 frame / 49.6 detik dan 175
  prediksi, lalu keluar 130 serta menjalankan kembali layanan dashboard.
  Sesi incomplete ditolak QA dan tidak mempunyai label aktivitas. Semua
  pengujian perangkat telah dihentikan; sesi kondisi pengguna belum dimulai.

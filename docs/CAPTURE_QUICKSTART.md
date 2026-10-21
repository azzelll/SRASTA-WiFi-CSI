# Ambil data SRASTA — panduan anggota tim

Panduan ini sesuai CLI yang ada pada handoff **21 Oktober 2026**. Mulai dengan
setup Python dan hash model di [`HANDOFF.md`](../HANDOFF.md). Recorder saat ini
mengambil **tiga kondisi nonfall**, bukan otomatis seluruh dataset lima fitur.

## 1. Hubungkan perangkat dan cek sumber

1. Board berlabel **RX** memakai konektor **UART/COM** ke komputer yang
   menjalankan recorder. Jika RX ke Pi, jalankan recorder di Pi dari **clone repo lengkap** (paket runtime Pi tidak memuat recorder), atau pindahkan
   USB data RX ke Mac; Mac tidak bisa membaca `/dev/ttyUSB0` Pi secara langsung.
2. TX cukup diberi daya lewat Pi/adapter/Mac. Kedua board memakai jaringan CSI
   sendiri; Wi-Fi rumah Pi untuk SSH/cloud terpisah. Jangan flash ulang board
   yang sudah bekerja. Firmware saat ini: TX SoftAP channel 6, UDP sekitar
   50 Hz; RX JSONL UART **1.000.000 baud**, LLTF/HT20, 128 byte I/Q.
3. Cocokkan port dengan mencabut **satu** board yang labelnya diketahui, lihat
   port yang hilang, lalu pasang kembali. Label TX/RX bukan posisi USB kiri/kanan.
4. Posisikan TX/RX stabil, awalnya sekitar 2–5 m dengan tinggi 0,8–1,2 m, area
   aktivitas di antaranya dan hindari penghalang logam. Ini titik awal penataan,
   bukan jaminan cakupan. Jarak, tinggi, orientasi, ruangan dan penghalang harus
   dicatat. Jangan pindahkan board selama sesi; konfigurasi baru = sesi baru.
5. Tutup Arduino Serial Monitor, `idf.py monitor`, console serial dan pembaca
   lain. Satu RX hanya boleh dipakai satu proses. Sistem memerlukan `lsof`.

Daftar port di Mac:

```bash
ls /dev/cu.usbserial* /dev/cu.usbmodem* 2>/dev/null
```

Di Pi/Linux:

```bash
ls -l /dev/serial/by-id/ /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

Nomor lama tidak menjamin identitas. Jika layanan Pi aktif, hentikan terlebih
dahulu dari akun yang menjalankannya:

```bash
systemctl --user stop srasta-edge.service
```

Wrapper dapat menjeda/memulihkan layanan foreground dari checkout yang sama
setelah PID dan working directory cocok. **Jangan mengandalkannya untuk service
systemd dari folder release lain.** Catat layanan yang dihentikan untuk dipulihkan
setelah rekaman. Selama capture, caregiver tidak menerima CSI live dari RX itu.

## 2. Pilot sebelum sesi berlabel

Ganti nilai port berikut dengan RX yang baru diverifikasi. Jangan salin port
contoh tanpa pemeriksaan. Jalankan dari root repo:

```bash
# Contoh Mac; pada Pi biasanya /dev/ttyUSB0 atau symlink /dev/serial/by-id/...
SRASTA_RX_PORT=/dev/cu.PORT_RX
bash scripts/collect_local_csi.sh \
  --port "$SRASTA_RX_PORT" --root "$HOME/SRASTA_LOCAL_CAPTURE" \
  --pilot-only --pilot-seconds 15
```

Pilot memastikan file/decoder/prediksi bisa berjalan. Periksa frame valid >0,
rate dari timestamp aktual, drop, gap dan karantina pada summary/QA. Pilot
tanpa anotasi memang bisa pending; ini tidak membuktikan kualitas model.
Jika nol paket, cek TX powered, label RX, konektor UART, baud, channel dan
pembaca serial lain. Jangan mengubah panjang CSI atau mask agar paket lolos.

CLI default memakai `esp_idf_native`: mask invalid word pada posisi aslinya,
petakan 64 posisi native ke centered dengan `fftshift`, baru fixed mask 52.
Ini deklarasi urutan frekuensi firmware, bukan resize/padding. Profile hash
tersimpan; rekaman sumber yang centered memerlukan deklarasi tersendiri.

## 3. Jalankan sesi terpandu

```bash
bash scripts/collect_local_csi.sh \
  --port "$SRASTA_RX_PORT" --root "$HOME/SRASTA_LOCAL_CAPTURE"
```

Tanpa `--port`, script menampilkan daftar pilihan atau memakai port layanan
lokal yang diketahui. Default 180 detik per kondisi, sekitar 11 menit + form.
Mac otomatis dijaga agar tidak tidur selama recorder berjalan.

### Isi form CLI

| Isian | Contoh / cara menjawab |
| --- | --- |
| Kode orang | `LOC_001`, atau Enter memakai default. **Harus berawalan `LOC_`**; `SHY001`/`SHY_001` ditolak. Gunakan kode sama untuk orang sama selamanya. |
| Split | `1` = train, `2` = validation, `3` = test. Putuskan sebelum melihat hasil; satu orang tidak boleh pindah split. |
| Kode lokasi / ruangan | `SITE_001`, `ROOM_001`; gunakan konsisten. |
| Kode pengamat | `ANN_001`; pengamat kedua harus kode berbeda, misalnya `ANN_002`. |
| Geometri | Contoh `sisi berlawanan, 3m, tinggi 1m, orientasi tetap`. Jangan masukkan alamat/nama pribadi. |
| Firmware masih sama? | Jawab `y` hanya jika benar diketahui; `n` bila tidak diketahui. |
| Cohort baru, bukan dataset publik? | Jawab sesuai kenyataan; jangan sekadar memilih `y` agar QA hijau. |
| Kode izin/protokol | Masukkan referensi prosedur pengambilan yang memang sudah disetujui tim. **Jika belum ada, Enter**; hasil tetap pending. Jangan mengarang nomor izin. |

Kode protokol adalah provenance penerimaan data dalam pipeline proyek, bukan
pernyataan bahwa setiap demo memerlukan jenis izin hukum tertentu. Koordinator
tim menetapkan prosedur/consent yang sesuai sebelum data dipakai training.
AI tidak boleh mengisi referensi persetujuan atau menjadi pengamat fiktif.

Registry `subjects.jsonl` mengunci split. Rencanakan beberapa orang yang
terpisah untuk train/validation/test; mengganti ruangan tidak membuat orang
yang sama menjadi test independen. Jika melanjutkan arsip dari laptop lain,
pindahkan registry asli bersama sesi secara privat.

### Ikuti tahap, Enter dan konfirmasi

| Tahap | Yang dilakukan setelah menekan Enter | Waktu |
| --- | --- | --- |
| Kosong | Semua orang keluar dari ruangan; tunggu bunyi selesai baru kembali | 20 detik persiapan + 180 detik rekam |
| Normal | Satu orang beraktivitas biasa: berjalan, berbalik, duduk/berdiri, mengambil barang ringan bila nyaman | 20 detik persiapan + 180 detik rekam |
| Diam/inaktif | Duduk/berbaring nyaman, posisi tetap dan bernapas normal | 61 detik diam awal + 180 detik rekam |

**Antartahap ada Enter** untuk menyatakan siap. Setelah rekaman, jawab `y/n`
apakah kondisi benar selama interval REKAM. Tidak ada gerakan pemicu khusus.
Persiapan, transisi dan waktu menjawab tidak otomatis diberi label. Jika kondisi
tidak sesuai, jawab `n`; raw tetap disimpan dan interval menjadi aborted.
Jangan menahan napas dan jangan melakukan jatuh untuk sesi ini.

Untuk memperpanjang setiap kondisi:

```bash
bash scripts/collect_local_csi.sh --port "$SRASTA_RX_PORT" \
  --root "$HOME/SRASTA_LOCAL_CAPTURE" --duration 600 --prepare 30
```

`--duration` minimum 60 detik. Memanjangkan sesi tiga kondisi ini belum sama
dengan protokol ADL bebas sepanjang hari atau sleep dengan anotasi referensi.

## 4. Hasil otomatis dan pemeriksaan

```text
$HOME/SRASTA_LOCAL_CAPTURE/
  subjects.jsonl
  sessions/SES_<UTC>_<id>/
    capture_config.json     profil/hash, kode orang/split, geometri, asal model
    frames.jsonl            CSI asli + sequence/timestamp/metadata lengkap
    events.jsonl            anotasi operator, belum otomatis accepted
    predictions.jsonl      output model; BUKAN ground truth
    quarantine.jsonl       diagnostik frame ditolak
    capture_summary.json   jumlah, durasi, loss, status selesai
    checksums.json         hash bukti asli
    qa_report.json         QA awal
    runtime.sqlite3        DB penelitian terisolasi dari caregiver
```

Default tanpa `--root` berada di sebelah folder repo. Folder rekaman wajib di
luar working tree Git dan `data/`; file privat, tidak diupload. Jangan mengedit
raw, menghapus paket buruk, mengubah split atau mengganti anotasi menurut model.
Tekan Ctrl+C sekali untuk berhenti sambil menyimpan status incomplete; koneksi
putus/reset RX juga mengakhiri sesi. Setelah pulih, buat sesi baru.

Pakai **path sesi yang dicetak recorder**, bukan folder root seluruh arsip:

```bash
SRASTA_SESSION="$HOME/SRASTA_LOCAL_CAPTURE/sessions/SES_GANTI_DENGAN_HASIL"
.venv/bin/python code/tools/qa_capture.py "$SRASTA_SESSION"
```

Exit 0 capture selesai **tidak berarti accepted**. QA bisa pending karena belum
ada review independen/provenance. Batas kualitas sudah ditentukan sebelum
capture: loss ≤1%, quarantine ≤1%, gap packet maksimum 0,15 detik untuk coverage,
minimum 60 detik nonfall direview. Jangan longgarkan batas setelah melihat hasil.

Pengamat kedua yang **benar-benar menyaksikan kondisi** melakukan review:

```bash
.venv/bin/python code/tools/qa_capture.py "$SRASTA_SESSION" --reviewer ANN_002
.venv/bin/python code/tools/evaluate_local_alerts.py "$SRASTA_SESSION"
```

Review ditambahkan, bukan menimpa bukti awal; report berikutnya di `qa_reports/`.
Panggilan reviewer tidak otomatis menyelesaikan provenance yang belum lengkap.
Tanpa review/coverage cukup, FAR unavailable, **bukan nol**. False alerts/hour
berbeda dari specificity. Nol alert dalam 3 menit tidak membuktikan target
≤2/hari; batas atas Poisson 95% memerlukan sekitar 36 jam exposure eligible
tanpa alert. Simpan alasan pending/rejected dan data gagal sebagai bukti.

Sesudah capture Pi, pulihkan layanan yang sebelumnya dihentikan:

```bash
systemctl --user start srasta-edge.service
systemctl --user status srasta-edge.service --no-pager
```

## 5. Data untuk lima fitur: apa yang masih kurang

| Fitur | Data yang berguna sekarang | Data tambahan yang diperlukan |
| --- | --- | --- |
| Presence | Kosong vs normal/diam, setelah QA dan review accepted | Orang/ruangan/sesi terpisah; validasi lokal |
| Motion | Aktivitas normal dan diam | Transisi bergerak–diam–bergerak dengan batas waktu pengamat |
| Inactivity | Diam setelah persiapan ≥60 detik | Interval normal/diam panjang, aktivitas kembali, evaluasi timer dan false alert |
| Breathing `sleep/normal/empty` | Empty lokal; kandidat publik yang sudah dilatih bisa untuk riset | Awake-lying dan tidur alami dengan anotasi observer/referensi sinkron; diam **tidak boleh diganti nama sleep** |
| Fall | Nonfall sebagai pembanding; fall v8 tersedia untuk demo | Event jatuh terkontrol, aman, terawasi, referensi empat batas waktu dan review independen |

CLI saat ini **tidak mempunyai mode sleep/fall terpandu**. AI penerus harus
menambahkan protokol, anotasi/schema dan pengujiannya lebih dulu. Jatuh hanya
oleh pelaksana dewasa terlatih dengan prosedur disetujui, pengawasan dan sarana
sesuai; jangan meminta lansia atau orang tanpa pelatihan menjatuhkan diri.
Empat timestamp wajib: onset, event end, post-event inactivity start dan end,
pada clock RX yang sama. Detail: [`esp32_s3_capture_protocol.md`](esp32_s3_capture_protocol.md).

Trainer presence lokal sudah ada, tetapi menolak data belum accepted atau split
bercampur. Setelah data mencukupi:

```bash
PYTHONPATH=code .venv/bin/python code/train_local_presence.py \
  --root "$HOME/SRASTA_LOCAL_CAPTURE" \
  --out-dir artifacts/releases/NEW_LOCAL_PRESENCE_RUN
```

Gunakan output baru. Trainer memerlukan train/validation subject-disjoint,
kedua label, dan satu capture hash yang konsisten. Keberhasilan training bukan
izin membuka test untuk tuning. Target 80%/80% harus diukur, tidak dijanjikan.

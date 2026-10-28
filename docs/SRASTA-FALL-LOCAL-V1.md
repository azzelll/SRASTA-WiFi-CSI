# Prosedur pengambilan data jatuh terkontrol SRASTA

| Identitas | Nilai |
| --- | --- |
| Kode referensi | `SRASTA-FALL-LOCAL-V1` |
| Versi | 1.0 |
| Tanggal penyusunan | 26 Oktober 2026, WIB |
| Status | **DRAFT — belum disetujui untuk pelaksanaan** |
| Lingkup awal | Satu event untuk pemeriksaan alur recorder dan anotasi |
| Pelaksanaan | Mengikuti rencana keselamatan lokasi dan persetujuan peserta |

Dokumen ini menjabarkan penggunaan recorder dari
[protokol capture](esp32_s3_capture_protocol.md) dan
[handoff fall](FALL_ENGINEERING_HANDOFF.md). Dokumen ini tidak mengajarkan
teknik menjatuhkan diri dan tidak menyatakan bahwa lokasi, alat, atau peserta
sudah diperiksa. Metode gerakan serta kelayakan sarana ditetapkan pengawas
yang kompeten sebelum pelaksanaan.

**Pembuatan dokumen dan kode referensi tidak berarti persetujuan sudah ada.**
Penanggung jawab tim/lokasi harus meninjau dan menyetujui versi ini, termasuk
rencana keselamatan yang berlaku. Penuhi proses persetujuan institusi/lokasi
jika diwajibkan oleh tempat pengambilan data. Catat persetujuan yang sebenarnya
dalam arsip privat sebelum memasukkan kode di form recorder.

## 1. Tujuan dan batas sesi

- Mengumpulkan CSI asli dari satu kejadian jatuh terkontrol dan interval diam
  setelahnya, dengan empat tanda waktu pengamat pada clock RX.
- Satu perintah `fall-observer` menghasilkan satu event dalam satu folder sesi.
- Pemeriksaan awal dilakukan pada satu event dahulu. Rencana pengulangan,
  jeda istirahat, dan jumlah maksimum harus ditetapkan pengawas; dokumen ini
  tidak menetapkan kuota jatuh yang harus dipenuhi peserta.
- Prediksi model, LED, OLED, atau bunyi perangkat tidak menentukan label dan
  tidak menjadi aba-aba untuk melakukan gerakan.
- Recovery/bangun bukan bagian dari interval diam. Recorder saat ini tidak
  otomatis memberi label recovery.

## 2. Pembagian tugas

| Peran | Tanggung jawab |
| --- | --- |
| Penanggung jawab tim/lokasi | Meninjau metode, sarana, persetujuan peserta, aturan penghentian, dan memberi keputusan pelaksanaan |
| Pelaksana dewasa terlatih | Berpartisipasi secara sukarela dan menjalankan hanya metode yang diizinkan pengawas |
| Pengawas/spotter | Memeriksa area serta sarana, mendampingi pelaksanaan, dan menghentikan percobaan bila diperlukan |
| Pengamat/operator | Mengoperasikan terminal dan menandai empat batas kejadian yang benar-benar disaksikan |
| Reviewer independen | Saksi lain yang memeriksa interval serta empat batas; berbeda dari pengamat pertama |

Pelaksana tidak merangkap operator tombol saat kejadian. Pengawasan fisik
tidak boleh ditinggalkan untuk mengoperasikan laptop. Pengawas boleh menjadi
reviewer bila merupakan orang berbeda dari annotator pertama dan benar-benar
menyaksikan intervalnya. Alternatif referensi tersinkron harus sudah disetujui
dan memiliki bukti; jangan membuat pengamat atau referensi fiktif.

## 3. Persiapan dan keputusan mulai

Penanggung jawab/pengawas memeriksa dan mencatat:

- [ ] Metode gerakan telah ditetapkan oleh pengawas yang kompeten.
- [ ] Pelaksana dewasa terlatih, bersedia, dan memenuhi persyaratan prosedur
      lokasi; bukan orang yang sedang tidak sehat atau peserta rentan.
- [ ] Permukaan benturan/matras sesuai, area bebas penghalang, spotter siap,
      dan akses bantuan tidak terhalang.
- [ ] Tidak ada rencana benturan kepala, jatuh dari tangga/furnitur,
      kehilangan kesadaran, atau jatuh tanpa pendamping di permukaan keras.
- [ ] Semua memahami bahwa peserta atau pengawas boleh menghentikan percobaan
      kapan saja; tidak ada kewajiban menyelesaikan durasi atau jumlah event.
- [ ] Proses persetujuan peserta serta rencana keselamatan lokasi telah dipenuhi.
- [ ] Pengamat pertama dan reviewer telah ditentukan; posisi mereka dicatat
      agar kehadiran/gerakan orang lain tidak menjadi perubahan yang tidak dicatat.
- [ ] Target diam pascakejadian, istirahat, dan batas pengulangan telah disepakati.
- [ ] RX/TX stabil dan pilot teknis telah diperiksa; tidak ada pembaca serial lain.

Hentikan percobaan untuk ketidaknyamanan, nyeri, pusing, kelelahan, gangguan
area, atau kondisi lain yang dinilai tidak aman. Dahulukan bantuan yang
dibutuhkan; jangan menunda bantuan untuk menyelesaikan label atau timer.

## 4. Setup recorder pada Mac

Perintah berikut untuk checkout Mac yang sudah dipakai merekam empty/presence.
RX harus tersambung ke USB data Mac. USB RX yang tersambung ke Pi tidak dapat
dibaca oleh recorder Mac. TX tetap diberi daya. Pertahankan geometri TX/RX
dalam satu sesi, dan catat sarana/posisi baru yang mengubah kondisi ruangan.

```bash
cd "/Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_CSI_Bench_Blynk"
bash scripts/collect_local_csi.sh --pilot-only --pilot-seconds 15
```

Pilih port berdasarkan identitas fisik RX. Periksa frame valid, loss,
karantina, serta gap sesuai [capture quickstart](CAPTURE_QUICKSTART.md).
Pilot tanpa label tidak otomatis accepted dan bukan data jatuh.

Setelah prasyarat pelaksanaan dan pilot terpenuhi:

```bash
cd "/Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_CSI_Bench_Blynk"
bash scripts/collect_local_csi.sh --protocol fall-observer --prepare 30
```

Pengambilan pada Pi memerlukan clone development yang benar-benar memuat
recorder ini, registry peserta yang konsisten, dan penanganan service pemegang
RX sesuai [operasi Pi](PI_OPERATIONS.md). Jangan menganggap command Mac
atau folder release runtime sebagai setup recorder Pi yang sudah diverifikasi.

## 5. Form sesi

| Isian | Cara mengisi |
| --- | --- |
| Kode peserta | Gunakan kode `LOC_` yang sama untuk orang yang sama |
| Split | Pertahankan split peserta yang sudah dikunci; putuskan peserta baru sebelum capture |
| Lokasi/ruangan | Gunakan kode lokasi dan ruangan yang konsisten |
| Kode pengamat | Kode `ANN_` milik operator yang benar-benar menyaksikan kejadian |
| Geometri | Catat posisi, jarak, tinggi, sarana benturan, serta keberadaan pengamat; tanpa alamat/nama pribadi |
| Firmware dan cohort | Jawab sesuai kondisi sebenarnya |
| Kode izin/protokol | Isi `SRASTA-FALL-LOCAL-V1` **hanya setelah versi ini benar-benar disetujui dan prasyarat sesi terpenuhi** |
| Konfirmasi kesiapan fall | `y` hanya bila prosedur, pelaksana terlatih, pengawasan, dan sarana benar-benar siap |

CLI memeriksa bahwa referensi prosedur tidak kosong; CLI tidak memverifikasi
persetujuan lapangan dengan membaca dokumen ini. Mengetik kode tidak dapat
menggantikan persetujuan yang sebenarnya. AI tidak memberi persetujuan atas
nama penanggung jawab, menjadi saksi, atau menjawab konfirmasi kondisi.

## 6. Urutan satu event dan empat tanda waktu

1. Operator mengisi form. Semua pihak bersiap sesuai rencana pengawas.
2. Tunggu persiapan 30 detik selesai. Ini persiapan teknis; gerakan dilaksanakan
   menurut aba-aba pengawas setelah kesiapan dipastikan.
3. Operator menekan Enter pada empat batas aktual berikut, tanpa menunggu
   prediksi, warna LED, atau bunyi perangkat.

| Urutan prompt | Saat menekan Enter |
| --- | --- |
| `ONSET kejadian` | Saat gerakan kejadian mulai |
| `AKHIR kejadian fall` | Saat gerakan kejadian jatuh selesai |
| `MULAI diam pascakejadian` | Saat interval diam benar-benar mulai, setelah gerakan penyesuaian yang diperlukan selesai |
| `AKHIR diam pascakejadian` | Saat interval diam yang direncanakan berakhir, sebelum recovery/bangun |

Target durasi diam harus ditetapkan pengawas sebelum percobaan. Evaluator
software memeriksa konfirmasi setelah setidaknya 10 detik diam; angka ini
adalah kebutuhan evaluasi timer model, bukan ketentuan keselamatan peserta.
Recorder tidak menyediakan countdown otomatis untuk empat batas tersebut.
Pengamat memakai pencatat durasi terpisah bila dibutuhkan. Hentikan kapan
pun jika peserta membutuhkan bantuan atau tidak nyaman.

Batas harus memenuhi `onset < akhir fall <= awal diam < akhir diam`.
Clock yang disimpan adalah clock RX; penekanan tombol memiliki ketidakpastian
reaksi manusia dan tidak menjadi referensi latency presisi.

4. Operator menjawab konfirmasi akhir sesuai yang disaksikan: `y` bila benar,
   `n` bila tidak sesuai. Catat gangguan/perbedaan kondisi dalam catatan sesi
   privat tanpa mengubah raw atau mengarang batas kejadian.
5. Tunggu pesan penyimpanan dan hasil QA. Satu event selesai; evaluasi arsip
   sebelum memutuskan pengulangan berikutnya bersama pengawas.

## 7. Penghentian dan penanganan data

- Peserta atau pengawas dapat membatalkan kapan saja. Operator menghentikan
  recorder dengan `Ctrl+C` bila perlu; data parsial tetap dipertahankan.
- Bila empat batas sudah dicatat tetapi kondisi tidak sesuai, jawab `n`.
- Serial terputus, clock tidak urut, kondisi berubah, atau percobaan dihentikan
  tidak boleh diperbaiki dengan mengedit raw/config agar terlihat lengkap.
- Utamakan bantuan; dokumentasikan pembatalan setelah keadaan aman.
- Tidak ada pengulangan otomatis. Setelah gangguan, mulai sesi baru setelah
  pengawas memastikan kesiapan dan kebutuhan istirahat terpenuhi.

## 8. QA dan penyimpanan

Pada command Mac di atas, recorder menyimpan raw, metadata, event, prediksi,
checksum, dan laporan QA di folder baru:

```text
/Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_LOCAL_CAPTURE/sessions/SES_...
```

Simpan kode/ID folder sesi yang dicetak terminal. Jangan memublikasikan raw,
rekaman referensi, data identitas, atau bukti persetujuan pribadi ke Git/cloud.
Gunakan kode peserta; simpan bukti persetujuan privat terpisah dari source.

Pemeriksaan teknis dapat dijalankan tanpa memberi review manusia:

```bash
SRASTA_SESSION="/Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_LOCAL_CAPTURE/sessions/SES_GANTI_DENGAN_HASIL"
.venv/bin/python code/tools/qa_capture.py "$SRASTA_SESSION"
```

Reviewer independen yang benar-benar menyaksikan interval menjalankan CLI
review dengan kode `ANN_` miliknya sesuai panduan. Jangan menjalankan review
atas nama orang lain. Referensi prosedur, review, kualitas paket, dan anotasi
yang memenuhi kontrak semuanya diperlukan; exit 0 recorder belum berarti
`accepted`. Jangan mengubah status, split, atau label berdasarkan prediksi.
Dokumen ini tidak mengesahkan sesi lama secara retroaktif.

## 9. Catatan persetujuan dan kesiapan privat

Salin template berikut ke catatan tim privat. Isi dengan informasi sebenarnya;
kosong berarti belum diputuskan, bukan otomatis disetujui. Identitas lengkap
atau bukti consent pribadi tetap di penyimpanan privat tim.

```text
Referensi prosedur: SRASTA-FALL-LOCAL-V1
Versi yang ditinjau: 1.0
Kode/ID penanggung jawab:
Keputusan penanggung jawab: BELUM DIPUTUSKAN / DISETUJUI / DITOLAK
Tanggal dan waktu keputusan:
Referensi rencana keselamatan lokasi dan consent yang berlaku:
Kode/ID pengawas/spotter:
Kode/ID pelaksana dan verifikasi kelayakan oleh pengawas:
Kode pengamat/operator:
Kode reviewer independen:
Kode lokasi/ruangan:
Metode gerakan yang diizinkan, ditetapkan pengawas:
Permukaan benturan/sarana dan hasil pemeriksaan pengawas:
Posisi serta tugas pengawas/operator/reviewer:
Target durasi diam yang disetujui:
Jeda istirahat dan batas pengulangan yang disetujui:
Kesiapan bantuan dan aturan penghentian:
Keputusan mulai sesi oleh pengawas: BELUM DIPUTUSKAN / SIAP / TUNDA
ID folder sesi setelah capture:
Gangguan, pembatalan, atau tindak lanjut:
```

Persetujuan satu dokumen tidak menyatakan setiap sesi berikutnya sudah siap.
Perubahan metode, sarana, atau aturan yang memengaruhi keselamatan memerlukan
peninjauan ulang dan versi baru. Pertahankan jejak keputusan serta versi yang
dipakai saat capture; jangan mengganti arti referensi pada arsip lama.

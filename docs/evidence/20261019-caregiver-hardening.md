# Validasi kamera dan ketahanan caregiver — 19 Oktober 2026

## Perubahan software

### Kamera per kejadian

Sensor dibuka hanya untuk anomali/kritis CSI yang live dan masih baru. Satu
kejadian menjalankan satu burst berisi tiga frame, berjarak sekitar 0,3 detik
setelah pemanasan exposure satu detik. Helper memiliki timeout sepuluh detik.
Ketiga frame diproses oleh MoveNet yang sama; model tidak dilatih ulang.

Keputusan postur memerlukan sedikitnya dua frame andal yang searah, tanpa
frame andal dengan arah berlawanan. Dua mendatar dan satu tegak menghasilkan
`uncertain`. Tubuh tidak terbaca, tertutup, terpotong pada tepi, atau arah
diagonal juga tidak dipastikan. Tidak terbaca **tidak berarti ruangan kosong**.
Aturan ini adalah pemeriksaan konsistensi software, belum hasil kalibrasi
akurasi postur. Label tegak masih dapat berarti berdiri atau duduk; berbaring
tidak membuktikan tidur maupun jatuh.

Satu pose terukur dengan skor torso terbaik dikirim sebagai ringkasan COCO17.
Koordinat tidak dirata-rata atau diganti ilustrasi. Foto tidak disimpan atau
diunggah; hanya ringkasan kejadian dan pose yang masuk SQLite/cloud.

### Detail kejadian dan respons

Riwayat membuka detail event UID yang dipilih. Detail memuat sumber kejadian,
skor CSI saat kejadian, dasar peringatan, hasil kamera untuk UID yang sama,
waktu pemeriksaan, dan respons caregiver. Pose historis diberi penjelasan
bahwa itu bukan kondisi orang saat ini. Pose asli tidak ditempelkan pada
kejadian atau sesi simulasi/replay.

Status perintah dibedakan menjadi pending, applied, expired, dan rejected.
UI baru mengatakan respons diakui setelah diterapkan perangkat. Tombol
pending dinonaktifkan; kedaluwarsa/ditolak dapat dicoba ulang. Permintaan
bantuan terpisah dari pengakuan dan tidak melakukan panggilan otomatis.
Pengakuan tidak mengubah kondisi kritis menjadi normal. Poll lama tidak
mengembalikan receipt terminal menjadi pending; refresh yang bersamaan
dijalankan bergantian, dengan pembatalan saat berpindah akun/perangkat.

### Pemulihan kegagalan

- Serial: putus-sambung port terkonfigurasi mereset sesi, membuang baris JSON
  yang belum lengkap, lalu menerima urutan paket baru. Uji memakai PTY lokal,
  belum pencabutan USB fisik pada Pi.
- Cloud: timeout mematikan status connected; outbox SQLite tetap mengirim UID
  yang sama setelah restart. Seluruh batch perintah divalidasi sebelum ada
  tindakan. Pengiriman receipt yang diulang tidak mengulangi bantuan.
- Kamera: gagal menyimpan dicoba ulang tanpa memotret ulang, dan hasil pending
  menahan capture berikutnya sampai tersimpan. Jika pembacaan dedup SQLite
  gagal, capture ditunda. Error provider/sensor tidak mematikan worker.
  Pending save berada di memori sampai SQLite berhasil; pemulihan setelah
  listrik padam di sela kegagalan disk belum dijamin.

## Bukti pengujian

| Pemeriksaan | Hasil | Batas bukti |
|---|---|---|
| Backend unittest | 119 lulus | Termasuk model MoveNet pada piksel sintetis; sensor tidak dibuka |
| Web Vitest | 30 lulus | Renderer, UID, receipt, refresh; bukan login perangkat pengguna |
| TypeScript dan Vite build | Lulus | Build lokal dan build Vercel |
| Database cloud lokal | Lulus | PGlite: RLS/tenant, lease/dedup/outbox; bukan delivery push |
| Integrasi runtime/API | Lulus | Satu rekaman train memakai model asli; alur alarm/pose memakai keputusan dan tiga frame keypoint sintetis |
| Browser desktop/HP | Lulus | Komponen asli dengan fixture sintetis berlabel, 1440×900 dan 390×844 |

Laporan integrasi:
`artifacts/research/20261019-camera-burst-integration/report.json`.
Tidak membuka payload test, menulis gambar, atau mengirim notifikasi uji.

Browser membuktikan tombol pending dinonaktifkan tanpa klaim sudah diakui,
applied mengubah respons, expired membuka kirim ulang, bantuan tidak mengakui
peringatan, dan kamera gagal tidak menggambar skeleton. Lebar dokumen pada HP
390 px sama dengan viewport 390 px. Screenshot sintetis ada di
`artifacts/ui/20261019-event-detail/desktop.png`, `mobile.png`, dan
`mobile-expired.png`; route preview terpisah dari build produksi.

## Web dan paket Pi

Web terdeploy pada akun `madeshandykrisnanda@gmail.com`, proyek
`srasta-caregiver`, ke <https://srasta-caregiver.vercel.app>.
Deployment: `srasta-caregiver-ce4uihebk-azzellls-projects.vercel.app`.
HTTP 200 dan marker komponen baru diperiksa pada bundle
`/assets/index-BwXYQXgX.js`; detail readback di
`artifacts/research/20261019-camera-burst-integration/deployment.json`.
Kontrak cloud pose tidak berubah sehingga fungsi `edge-sync` tidak dideploy
ulang untuk pembaruan ini. Tidak ada event atau perintah sintetis yang dikirim
ke produksi.

Paket baru: `artifacts/pi/20261019-demo-camera-burst-r2.tar.gz`, dengan manifest
hash per file dan checksum arsip terpisah. Lihat
[panduan paket](../pi-offline-package.md). Arsip sebelumnya tetap disimpan.
Acceptance paket memeriksa hash, startup route, inferensi sintetis fall,
loading model riset, serta loading/eksekusi MoveNet tanpa sensor.

**Paket belum dipasang pada Pi dan kamera asli belum diuji dalam sesi ini.**
Acceptance Mac tidak membuktikan parity ARM, daya tahan USB/Wi-Fi fisik,
latensi burst Pi, login/notification pada HP, atau akurasi deteksi. Model fall
v8 dan metrik recall/specificity tidak berubah. Berikutnya: install release
baru di Pi, uji kamera terisolasi dan UID sampai app, kemudian uji pemulihan
koneksi fisik. Tidak perlu melakukan jatuh untuk pemeriksaan pemasangan.

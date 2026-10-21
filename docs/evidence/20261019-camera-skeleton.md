# Skeleton kamera pada panel caregiver — 19 Oktober 2026

## Perubahan

Panel Validasi Kamera memakai koordinat keluaran MoveNet dari satu cuplikan
kejadian. Garis dan sendi mengikuti koordinat tersebut, bukan ilustrasi posisi
yang dipilih dari label. Titik dengan skor di bawah 0,3 dan tulang yang
menghubungkannya tidak digambar. Jika titik tidak cukup, UI mengatakan hasil
belum jelas atau koordinat belum tersedia. Tidak ada skeleton pengganti.

- `horizontal`: **Berbaring**, dengan penjelasan belum memastikan tidur/jatuh.
- `not_horizontal`: **Postur tegak**, masih dapat berarti berdiri atau duduk.
- `uncertain`: hasil belum jelas; titik yang cukup andal masih dapat terlihat.
- `error`: kamera terhambat, tanpa cuplikan skeleton.

Ini adalah snapshot kejadian, bukan video atau pemantauan kamera terus-menerus.
Pemicu kamera tetap kejadian anomali/kritis model CSI yang fresh, live, dan
memiliki UID valid. UI memerlukan kecocokan UID serta snapshot live yang baru;
hasil dari replay, simulasi, event lain, atau data kedaluwarsa disembunyikan.

## Jalur dan kontrak

`kamera → MoveNet → pose tervalidasi → SQLite → edge-sync → snapshot → SVG`

Field opsional `camera_validation.pose` memiliki tepat dua properti:

```json
{"format":"movenet-coco17","keypoints":["17 triple numerik [y,x,skor]"]}
```

Contoh di atas menjelaskan struktur, bukan payload valid. Payload sesungguhnya
harus memiliki tepat 17 array berisi tiga angka finite 0–1. String, boolean,
NaN, koordinat di luar rentang, jumlah titik salah, atau properti tambahan
ditolak. Python membulatkan ke empat angka desimal sebelum menyimpan/kirim.

SQLite menambahkan kolom nullable `pose_json` pada database lama, tanpa
menghapus catatan. Hasil lama tetap `pose=null`. Snapshot Supabase memakai
kolom JSONB yang sudah ada, sehingga tidak memerlukan migrasi tabel cloud.
Foto dan raw CSI tidak dikirim; integrasi kamera tidak menyimpan foto.
Autentikasi per device, tenant RLS, serta kebijakan pemicu tetap berlaku.

## Bukti software

- Backend: **107 tes lulus**, termasuk pose finite/bounds, penolakan extra
  fields, migrasi SQLite lama, restart, dan satu pemeriksaan per UID.
- Web: **22 tes lulus**; renderer mempertahankan koordinat, menghilangkan
  titik lemah, tidak mengarang pose, dan menyembunyikan hasil tak cocok/stale.
- `npm run build`: TypeScript dan build produksi lulus.
- Kontrak Edge Function: **6 tes lulus**, pose valid diterima dan format
  salah ditolak; ringkasan legacy tetap diterima.
- `npm run test:cloud`: migrasi/RLS, tenant isolation, command lease,
  dedup/outbox, dan membership revocation lulus pada database uji lokal.
- Integrasi offline: replay sumber + keputusan/keypoint sintetis melalui
  runtime, API, persistensi, dan payload allowlist lulus. Alarm jaringan mati.
  Laporan: `artifacts/research/20261019-skeleton-integration/report.json`.
- Tampilan browser diperiksa pada 1440×900 dan 390×844. Lebar dokumen pada
  viewport 390 adalah 390; teks hasil tidak terpotong. Screenshot di
  `artifacts/ui/20261019-skeleton/desktop.png` dan `mobile.png` memakai data
  sintetis berlabel jelas, bukan kamera asli. Preview lokal terpisah dari build.

## Deployment

- Akun Vercel diperiksa: `madeshandykrisnanda@gmail.com`, username `azzelll`.
- Proyek `srasta-caregiver`, ID `prj_ZGLuSEAgmr09gpgTLcteN65Di16T`, team
  `team_YT0FhWq3pnR5pqA8tT7dXrVu`.
- Produksi: <https://srasta-caregiver.vercel.app>, HTTP 200, bundle produksi
  `/assets/index-CsRJuF1o.js` berisi renderer skeleton baru.
- Deployment: `srasta-caregiver-lfg41igdu-azzellls-projects.vercel.app`.
- Supabase `cvsexwxyjxvxdwxmlpav`: fungsi `edge-sync` **versi 6, ACTIVE**.
  Request tanpa credential setelah deployment menghasilkan **HTTP 401**.
- Readback deployment: `artifacts/research/20261019-skeleton-integration/deployment.json`.

Tidak mengirim event sintetis ke perangkat produksi. Pemeriksaan asset dan
fungsi terdeploy belum membuktikan sesi login caregiver menerima kamera live.

## Pi dan pekerjaan yang masih perlu dibuktikan

Paket `artifacts/pi/20261019-demo-skeleton-camera.tar.gz` menyertakan runtime,
renderer, MoveNet yang sama, model fall v8 yang sama, dan manifest SHA-256.
Paket diperiksa setelah diekstrak di Mac; belum dipasang/diuji pada Pi ARM.
Lihat [panduan paket](../pi-offline-package.md).

Sebelum mengklaim jalur live selesai: pasang paket pada release Pi baru,
periksa RX dan kamera, lalu cocokkan UID dan koordinat tangkapan asli dengan
panel caregiver. Gunakan pemeriksaan kamera terisolasi dan aktivitas biasa;
tidak perlu melakukan jatuh. Uji ini belum mengukur akurasi postur, false
alert, atau membuktikan tidur. Model dan metrik fall tidak berubah.

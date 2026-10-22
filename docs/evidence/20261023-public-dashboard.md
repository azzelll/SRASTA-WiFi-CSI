# Dashboard tanpa login — 23 Oktober 2026

## Permintaan dan perubahan

Pemilik meminta langsung ke dashboard Vercel tanpa login, termasuk tombol
Akui dan Minta bantuan. Mode `public` memakai daftar perangkat opt-in dan
snapshot/receipt cloud nyata melalui RPC terbatas. Browser tidak membuat akun,
memulihkan sesi Auth, menerima admin key, atau mengakses token Pi.

Migrasi `202610230001_public_dashboard.sql` menambahkan konfigurasi privat,
RPC read/action/push, atribusi tindakan publik, dedup lintas browser dan
pencabutan akses. Direct table RLS dan autentikasi device ingest tetap berlaku.
Kontrak CSI, model, UI Figma dan runtime Pi tidak diubah.

## Verifikasi software

```bash
cd web
npm test
npm run test:cloud
VITE_ACCESS_MODE=public npm run build
cd ..
git diff --check
```

- 37 tes web lulus: entry page tanpa sesi, RPC public vs authenticated,
  penolakan admin key, penolakan dashboard revoked, dan regresi UI sebelumnya.
- PGlite lulus: migrasi, default deny, isolasi perangkat, RPC publik opt-in,
  atribusi null user, command ID conflict/dedup, TTL, receipt simulated edge,
  push registration/lease/dedup/revocation. Tidak ada pesan push dikirim.
- TypeScript dan build Vite lulus. Output JS sekitar 492 kB sebelum gzip.

## Penerapan dan batas bukti

Pemilik mengonfirmasi pembukaan akses publik dan kedua tombol pada 23 Oktober.
Migrasi dijalankan atomik di Supabase SQL Editor dan dicatat pada migration
history. Hasil SELECT menunjukkan tepat satu konfigurasi, **SRASTA Edge**,
dengan `enabled`, `allow_commands`, dan `allow_push` bernilai true.

`VITE_ACCESS_MODE=public` disimpan pada environment Production Vercel.
Deployment dari source commit `c666159` berstatus **READY**:

- App: <https://srasta-caregiver.vercel.app>.
- Deployment ID: `dpl_8DFAdEvqcwny1MaxcHAQk8rmdLKe`.
- [Inspector](https://vercel.com/azzellls-projects/srasta-caregiver/8DFAdEvqcwny1MaxcHAQk8rmdLKe).

Pemeriksaan HTTPS dengan publishable key saja, tanpa sesi pengguna:

- Daftar menampilkan satu perangkat yang dipilih, snapshot/receipt HTTP 200.
- UUID perangkat yang tidak dipublikasikan menghasilkan null.
- Enam tabel publik tetap menolak anon SELECT dengan HTTP 401.
- RPC menolak tindakan tidak valid dengan HTTP 400 tanpa menambah command.
- Pada 00:31 WIB, cloud melaporkan `source=live`, monitoring/serial/state
  verified true, 8.314 frame diterima; snapshot berumur 0,55 detik dan observasi
  CSI 0,56 detik. Ini bukti ringkasan CSI fresh saat pemeriksaan tersebut.
  Tidak menyatakan mutu classifier atau membuktikan kejadian jatuh.

[Hasil pemeriksaan tersanitasi](20261023-public-checks.json).
Browser produksi membuka Beranda langsung tanpa login, menampilkan Perangkat
Online dan tren CSI. Pengaturan memilih SRASTA Edge dan menampilkan akses
tanpa login tanpa tombol logout. Tidak ada error/warning console saat diperiksa.
Tidak ada alert pada snapshot ini; tombol tindakan tetap muncul sesuai konteks
peringatan. Validasi kedua tindakan/receipt dilakukan di SQL lokal, bukan dengan
mengakui kejadian atau meminta bantuan palsu pada perangkat nyata.

Uji SQL lokal tidak membuktikan push HP atau tindakan yang diterapkan Pi
fisik. Tidak mengirim kejadian palsu ke perangkat produksi; tidak ada uji
jatuh manusia. Data lama/offline tetap ditampilkan sebagai demikian.
Lihat `CLOUD_SETUP.md` untuk aktivasi satu perangkat dan rollback.

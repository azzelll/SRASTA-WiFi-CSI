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

Penerapan Supabase/Vercel dan pemeriksaan browser produksi masih menunggu
konfirmasi tindakan pembukaan akses melalui browser. Bagian ini harus
diperbarui setelah hasil penerapan benar-benar diperiksa.

Uji SQL lokal tidak membuktikan push HP atau tindakan yang diterapkan Pi
fisik. Tidak mengirim kejadian palsu ke perangkat produksi; tidak ada uji
jatuh manusia. Data lama/offline tetap harus ditampilkan sebagai demikian.
Lihat `CLOUD_SETUP.md` untuk aktivasi satu perangkat dan rollback.

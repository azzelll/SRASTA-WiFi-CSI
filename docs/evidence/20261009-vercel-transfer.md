# Transfer pemilik Vercel — 9 Oktober 2026

User meminta proyek SRASTA dipindahkan ke akun
`madeshandykrisnanda@gmail.com` dan akun Jitu dikeluarkan dari Vercel CLI.

## Hasil transfer

- Proyek: `srasta-caregiver`, ID `prj_ZGLuSEAgmr09gpgTLcteN65Di16T`.
- Source team saat pemeriksaan awal: `teamatjitus-projects`.
- Akun tujuan diperiksa lewat API sebelum menerima transfer:
  `madeshandykrisnanda@gmail.com`, username `azzelll`.
- Team tujuan: `azzellls-projects`, ID
  `team_YT0FhWq3pnR5pqA8tT7dXrVu`, membership user `OWNER`.
- Source membuat transfer request; CLI melakukan logout lalu login sebagai
  akun tujuan. Permintaan diterima lewat API dengan team tujuan yang sudah
  diperiksa. Kode transfer hanya dipakai selama sesi dan tidak disimpan
  dalam artifact atau dokumentasi.
- Readback proyek mengembalikan `accountId` team tujuan dan
  `transferCompletedAt=1791525532341` (9 Oktober 2026, 12.58 WIB).
- Domain `srasta-caregiver.vercel.app` terdaftar dan verified pada proyek
  tujuan; akses HTTPS diperiksa menghasilkan HTTP 200.
- Deployment produksi `dpl_AeYGibBhEGeQzeASKKna9vb8LTgC` tetap `READY`.
- Empat nama environment proyek terbaca setelah transfer:
  `VITE_ACCESS_MODE`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_PUBLISHABLE_KEY`, `VITE_VAPID_PUBLIC_KEY`.
  Nilainya tidak ditampilkan atau ditulis ke bukti.

[Dashboard proyek](https://vercel.com/azzellls-projects/srasta-caregiver)
dan [app caregiver](https://srasta-caregiver.vercel.app).

## Konfigurasi CLI dan lokal

`vercel link --yes --project srasta-caregiver --scope azzellls-projects`
berhasil menghubungkan `web/` ke team baru. Vercel memperbarui token OIDC
lokal melalui alur CLI resminya; `.env.local` dan `.vercel/project.json`
tetap diabaikan Git.

Pemeriksaan akhir mencocokkan email principal CLI, project ID, org ID,
serta memastikan email dan ID team lama tidak tersisa pada `auth.json`
dan `config.json` Vercel CLI. Setelah logout, satu cache pemetaan nama team
lama masih ada; hanya entri cache tersebut yang dihapus.

Bukti lokal tanpa token/kode transfer berada di
`artifacts/vercel/20261009-owner-transfer/owner-readback.json` dan
`cli-readback.json`. Perubahan ini tidak membuat deployment baru.

Alur mengikuti dokumentasi resmi
[Claim Deployments](https://vercel.com/docs/deployments/claim-deployments)
dan [vercel logout](https://vercel.com/docs/cli/logout).

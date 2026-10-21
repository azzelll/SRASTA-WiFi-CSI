# Akses caregiver dari luar rumah

Target: frontend PWA HTTPS di Vercel; Supabase Auth, Postgres/RLS, Realtime,
dan Edge Function. Edge membuka koneksi keluar saja. Port inferensi tidak
dipublikasikan. Pengguna telah login dan mengizinkan pembuatan proyek.

## Pemilik Vercel, 9 Oktober 2026

Proyek `srasta-caregiver` sudah ditransfer ke team `azzellls-projects`,
milik akun yang diminta user (`madeshandykrisnanda@gmail.com`). Vercel CLI
sekarang login sebagai `azzelll`; folder `web/` juga sudah ditautkan ke team
baru. Sesi login lama dan cache team lama pada konfigurasi CLI sudah dihapus.

- [Dashboard proyek](https://vercel.com/azzellls-projects/srasta-caregiver).
- App: <https://srasta-caregiver.vercel.app>, diperiksa HTTP 200.
- Project ID: `prj_ZGLuSEAgmr09gpgTLcteN65Di16T`.
- Team ID: `team_YT0FhWq3pnR5pqA8tT7dXrVu`.
- [Bukti transfer dan konfigurasi CLI](docs/evidence/20261009-vercel-transfer.md).

## Pembaruan skeleton kamera, 19 Oktober 2026

UI produksi sudah memuat renderer skeleton dari koordinat MoveNet. Fungsi
`edge-sync` versi 6 menerima ringkasan opsional `pose` berisi tepat 17 triple
`[y, x, skor]` bernilai 0–1, format `movenet-coco17`. Kontrak menolak nilai
tidak valid dan properti tambahan seperti gambar. Autentikasi device tetap
berlaku; request tanpa credential diperiksa kembali menghasilkan HTTP 401.

Koordinat hanya ditampilkan untuk event UID yang cocok pada snapshot live
yang baru. Data replay, simulasi, kedaluwarsa, error, atau rekaman lama tanpa
koordinat tidak menghasilkan skeleton buatan. Foto tidak diunggah. Pi masih
memerlukan paket runtime baru sebelum mengirim koordinat; deployment web
sendiri belum membuktikan jalur kamera asli sampai caregiver. Lihat
[bukti dan batas pengujian](docs/evidence/20261019-camera-skeleton.md).

Pembaruan caregiver berikutnya pada tanggal yang sama menambahkan detail event
terpilih, pose historis bertimestamp, dan receipt pending/applied/expired/
rejected. Panel kondisi terkini tetap mensyaratkan snapshot fresh; detail
riwayat dapat menampilkan hasil lama untuk UID yang cocok dan memberi label
bahwa itu bukan kondisi saat ini. Kontrak pose tetap sama; fungsi cloud tidak
perlu dideploy ulang. Uji database lokal dan preview browser sintetis lulus;
delivery kamera/push asli ke HP masih memerlukan uji live. Lihat
[laporan ketahanan caregiver](docs/evidence/20261019-caregiver-hardening.md).

## Deployment yang telah diverifikasi, 1 Oktober 2026

- App: <https://srasta-caregiver.vercel.app>, proyek Vercel
  `srasta-caregiver` pada `teamatjitus-projects`.
- Supabase: `srasta-caregiver`, ref `cvsexwxyjxvxdwxmlpav`, Free/NANO,
  Singapore. URL: <https://cvsexwxyjxvxdwxmlpav.supabase.co>.
- Migrasi `202610010001` dan `202610010002` tercatat pada database remote.
  Enam tabel publik memakai RLS; device token dan antrean push berada pada
  schema privat. Fungsi `edge-sync` telah dideploy.
- Auth memakai tautan email, signup publik dinonaktifkan, dan redirect dibatasi
  ke origin app. Owner telah terdaftar sebagai anggota device.
- Ringkasan CSI asli diterima melalui HTTPS; saat RX dicabut, heartbeat cloud
  tetap berjalan dengan `monitoring_online=false` dan metrik pengamatan kosong.

Roundtrip RPC caregiver melalui HTTPS ke SQLite dan receipt Supabase lulus
pada device simulasi terpisah, termasuk restart, retry setelah respons hilang,
dan pencabutan membership saat JWT masih aktif. Device uji sudah dihapus.
Delivery push pada HP, aksi melalui UI HP, dan pengukuran Raspberry Pi masih
memerlukan bukti tersendiri. Detail bukti ada di
[engineering evidence](docs/evidence/20261001-caregiver-engineering.md).

## 1. Supabase

Buat proyek `srasta-caregiver` pada organisasi pengguna, region terdekat
misalnya Singapore. Gunakan paket free bila tersedia. Pengguna mengisi dan
menyimpan password database sendiri, serta menyelesaikan syarat akun bila ada.
Jalankan semua migrasi `supabase/migrations/` lewat CLI yang sudah login:

```bash
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase db push
npx supabase functions deploy edge-sync
```

Function `edge-sync` memiliki verifikasi JWT gateway nonaktif karena memakai
credential **per device**. Ia tetap menolak request tanpa token valid.
Hash SHA-256 token disimpan di schema privat yang tidak dibaca browser; token
tidak memberi akses seluruh proyek. Edge Function memakai backend key yang
diinjeksi Supabase ke environment fungsi. Override opsional
`SRASTA_SUPABASE_SECRET_KEY` hanya boleh berada di secret Supabase, bukan
Git/frontend/edge. Pasang VAPID lewat file lokal dengan permission `0600`:

```bash
npx supabase secrets set --env-file /absolute/path/private-cloud.env
```

Isi file privat:

```text
VAPID_PUBLIC_KEY=<generated public key>
VAPID_PRIVATE_KEY=<generated private key>
VAPID_SUBJECT=<https app origin or owner mailto>
```

VAPID diperlukan untuk push ketika app tertutup. Tanpa VAPID, dashboard dan
perintah dapat bekerja, tetapi push belum aktif. Jangan memasukkan private
key ke variabel `VITE_*`. UI frontend hanya menerima publishable key.

## 2. Device dan membership

Buat UUID device dan credential acak minimal32 karakter di file lokal0600.
Masukkan device dan hashnya sebagai admin. SQL berikut adalah template,
bukan data pasien/credential aktual:

```sql
insert into public.devices(id,label) values('<DEVICE_UUID>','SRASTA Edge');
insert into srasta_private.device_secrets(device_id,token_sha256)
values('<DEVICE_UUID>','<SHA256_OF_DEVICE_TOKEN>');
insert into public.device_members(device_id,user_id)
values('<DEVICE_UUID>','<AUTH_USER_UUID>');
```

Caregiver login memakai Supabase Auth yang terdaftar pada membership device.
Pengguna mengisi credential caregiver sendiri; jangan membuat password di chat.
Jangan mengirim undangan kepada orang lain tanpa instruksi pengguna.
Pengaturan Auth signup perlu mengikuti akun caregiver yang disetujui pemilik.
RLS: signed-out tidak dapat membaca; caregiver melihat device yang ditugaskan;
membership/credentials/status/receipt tidak dapat diubah langsung dari browser.

## 3. Edge `.env`

```text
SRASTA_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
SRASTA_DEVICE_ID=<DEVICE_UUID>
SRASTA_DEVICE_TOKEN=<per-device token>
```

CloudSync mengirim ringkasan allowlist setiap 5 detik dan mengambil perintah
pending. Events/receipt memakai outbox SQLite. Network timeout5detik dan
backoff5–60detik; cloud tidak menghentikan inferensi/alarm. TTL command2menit
dibuat server. UUID command mencegah tindakan berulang saat retry. UI menampilkan
“Menunggu edge” sampai transaksi SQLite diterapkan dan receipt dipublikasikan.
Antrean push memakai lease 60 detik dan `SKIP LOCKED` agar heartbeat yang
bertumpuk tidak mengambil job yang sama. Satu batch maksimal 8 job; gagal
dikirim mencoba ulang dengan backoff, maksimal 5 percobaan dalam 10 menit.
Kegagalan setelah penyedia push menerima pesan tetapi sebelum receipt tersimpan
masih dapat menghasilkan pengiriman ulang; tag event membantu browser
menggabungkan notifikasi. Tidak ada klaim pengiriman tepat satu kali.

## 4. Vercel

Import/deploy folder `web/`, frameworkVite, build `npm run build`, output`dist`.
Repository belum di-commit/push oleh pekerjaan ini; gunakan CLI pada folderweb
atau lakukan publikasi Git sesuai instruksi pengguna.
Variabel environment Vercel:

```text
VITE_ACCESS_MODE=cloud
VITE_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable key>
VITE_VAPID_PUBLIC_KEY=<VAPID public key>
```

`web/vercel.json` menyediakan SPA rewrite dan security headers. Domain HTTPS
Vercel dimasukkan pada Supabase Auth Site URL/redirect URLs. UI login tidak
memiliki token Blynk, device token, atau Supabase secret key. Localenv tidak
diunggah; buildfrontend hanya memakai empat variabel yang telah ditentukan.

## 5. Gate sebelum menyatakan akses remote selesai

- Jalankan migrasi/RLS pada proyek asli dan periksa akun A/B serta signed-out.
- Login pada HP dengan seluler, bukan WiFi rumah; terima CSI nyata dengan
  source`live` dan waktu baru. Gunakan aktivitas aman, tidak melakukan jatuh.
- Trigger5status simulasi yang selalu diberi label; ACK dan assistance harus
  round-trip melalui cloud ke SQLite, dan kedaluwarsa bila edgeoffline.
- Terima push warning/critical pada HP (termasuk app tertutup/HomeScreen),
  periksa dedup dan fallback ketika izin notifikasi tidak diberikan.
- Matikan koneksi cloud: alarm/inferensi lokal berjalan, appremote stale.
  Sambungkan ulang: outbox dikirim tanpa membuat aksi/event berulang.
- Cabut/reset RX: app tidak menampilkan normal terkini dari data lama;
  frame valid dapat diterima kembali tanpa menganggap gap sebagai diam.
- Periksa desktop/mobile, installPWA, logout, gantiuser/device, dan RLS
  sesudah membership dicabut. Jangan mengumumkan gate ini lulus dari unit test.

Referensi: [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security),
[Edge Function security](https://supabase.com/docs/guides/functions/auth),
[Vercel Vite](https://vercel.com/docs/frameworks/frontend/vite).

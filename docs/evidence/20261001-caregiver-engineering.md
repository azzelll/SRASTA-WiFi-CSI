# SRASTA caregiver engineering — 1 Oktober 2026

## Hasil yang sudah terverifikasi

- App produksi: <https://srasta-caregiver.vercel.app>, deployment
  `dpl_FxT7ZGtPgY5HfJxUbLWsK8bZE6FX`, READY, HTTP 200 dan CSP.
- Supabase `srasta-caregiver`, ref `cvsexwxyjxvxdwxmlpav`, Singapore;
  migrasi `202610010001` dan `202610010002` tercatat lokal/remote.
  Enam tabel publik memakai RLS. Function `edge-sync` sudah terdeploy.
- Device SRASTA Edge, token per-device, membership pemilik, Auth redirect
  HTTPS, signup publik nonaktif, dan VAPID server/frontend sudah dikonfigurasi.
  Tidak ada password/token/private key di source/frontend.
- RLS produksi diuji: pemilik membaca perangkatnya, user tanpa membership
  membaca nol, anon ditolak, authenticated tidak dapat memanggil edge ingest.
  HTTP tanpa device token ditolak 401. Ringkasan CSI asli diterima HTTP 200.
- Pengguna berhasil masuk. Sesi caregiver produksi terlihat langsung di Safari.
  Login email memakai magic link; agent tidak mengirim email/undangan.
- UI direvisi lagi setelah koreksi pengguna: login tanpa hero/slogan, satu
  jenis font sans, panel putih dengan hierarki data, indikator severity,
  napas/sinyal berdampingan, grafik, kesehatan perangkat, dan tindakan kejadian.
  Desktop 1440 dan ponsel 390 diperiksa di Safari. Figma acuan belum dapat
  dibaca karena connector menolak akses file; tidak ada klaim sesuai Figma.
- Push menyertakan severity, device UUID dan event UUID. Klik notifikasi membuka
  kejadian pada perangkat yang diizinkan; ID tidak valid diabaikan. Simulator
  tetap diberi label dan tidak mengisi grafik dengan CSI palsu.

## CSI asli

Run pada 04:31:54 UTC berjalan 1.330,317 detik (22,17 menit):

| Ukuran | Hasil |
| --- | --- |
| Frame valid | 43.270 |
| Karantina | 14 |
| Loss sequence | 0,03465% |
| Laju saat snapshot | 31,9 Hz |
| Host frame dropped | 0 |
| USB stall/reconnect | 0 / 0 |
| Inferensi TFLite Mac | 0,261 ms |
| Input/metadata | 52 amplitudo, sequence/timestamp meningkat, channel 6 |
| Blynk MQTT TLS | Terhubung |

Ringkasan: `artifacts/live_capture_smoke_20261001.json` (ignored).
Ini bukti transport/integrasi; bukan akurasi aktivitas/jatuh atau push HP.

Restart cloud mengungkap dua masalah yang sudah direproduksi dan diperbaiki:

1. macOS meninggalkan baud custom 1 MHz pada termios; `setraw` menolaknya.
   Normalisasi speed sebelum raw mode dan recovery `termios.error` diuji.
2. SSE menahan shutdown sehingga proses lama masih membaca RX. Graceful
   shutdown dibatasi 5 detik. Simulator dengan SSE terbuka keluar 5,3 detik.

Setelah proses lama dihentikan, RX pulih dan source `live`, inferensi, Blynk,
serta sync cloud aktif. Counter karantina/reconnect awal restart tersebut
mencakup periode dua pembaca; tidak digabung ke run bersih 22 menit di atas.
Pengguna kemudian mencabut TX/RX. Cloud terverifikasi menampilkan source
`unavailable`, monitoring offline, dengan heartbeat tetap baru.

Setelah pengguna menyambungkan kembali board, RX muncul di
`/dev/cu.usbserial-3130`. Probe validator menerima 128/128 frame tanpa gap.
Paket v8 kemudian berjalan pada CSI asli; pengamatan tambahan 180,158 detik:

| Ukuran | Hasil |
| --- | --- |
| Frame selama pengamatan | 5.779 |
| Snapshot online | 179 / 179 |
| Rata-rata laju capture | 32,281 Hz |
| Rata-rata inferensi Mac | 0,308 ms |
| Loss sequence pada akhir run | 0,0215% |
| Karantina sejak startup run | 3 |
| Status/event selama pengamatan | normal / tidak ada event |

Ringkasan: `artifacts/live_v8_smoke_20261001.json` (ignored). Aktivitas tidak
beranotasi independen; angka ini tidak dilaporkan sebagai FAR, recall, atau
validasi ruangan. UI lokal 390 piksel menampilkan metrik live dan desain terbaru
setelah tab yang masih memuat bundle lama direfresh.

## Roundtrip cloud dan Blynk

`code/cloud_acceptance.py` dijalankan melalui HTTPS terhadap proyek Supabase
produksi dengan device **simulasi sementara**, credential dan SQLite terpisah:

- Semua lima status tersimpan dan terbaca oleh sesi Auth owner yang sah.
- ACK menargetkan event anomaly sebelumnya; event critical terbaru tetap
  belum diakui. Bantuan manual menghasilkan satu tindakan tanpa auto-call.
- Perintah masuk dari RPC caregiver lewat Edge Function ke SQLite. Setelah
  runtime direstart sebelum mengunggah receipt, keduanya menjadi `applied`
  pada Supabase tanpa menggandakan tindakan.
- Server sengaja dibiarkan commit sebelum respons HTTP diputus. Retry setelah
  restart tidak menggandakan event atau tindakan dan mengosongkan outbox.
  Ini fault injection, bukan pemutusan internet fisik.
- Anon ditolak. JWT yang masih aktif kehilangan akses baca/perintah segera
  setelah membership device uji dicabut.
- Device uji dihapus, sesi QA direvoke dengan scope lokal; sesi Safari/HP
  tidak dipakai oleh script. Tidak ada langganan push pada device uji.

Bukti: `artifacts/cloud-acceptance-20261001-02/report.json` (ignored).

`code/blynk_acceptance.py` juga lulus pada Blynk yang sebenarnya:

- Satu MQTT client per token; layanan CSI ditutup bersih sebelum uji.
- V12=1 dibaca kembali sebelum status critical **SIMULASI** diterbitkan.
- HTTPS update V10 diterima lewat MQTT TLS, ACK tersimpan sebagai `blynk_v10`
  di SQLite simulator, dan pin kembali ke 0.
- V11 menghasilkan satu tindakan `blynk_v11`, tanpa auto-call, dan kembali 0.
- Indikator aktivitas Blynk memakai threshold model yang sama. Data terputus
  mengosongkan skor/napas/sinyal dan memberi label status terakhir. Perubahan
  offline segera dipublikasikan tanpa menunggu interval periodik.
- Layanan CSI asli dijalankan kembali sesudah uji.

Bukti: `artifacts/blynk-acceptance-20261001/report.json` (ignored).
Ini membuktikan alur API/cloud/MQTT/SQLite; tombol dan delivery push pada HP
tetap harus diperiksa di perangkat pengguna.

## Model dan batasnya

Paket integration terbaru: `artifacts/releases/20261001-tcn-v8-motion-calibrated/selected`.
Classifier v2 tetap 65.592 byte, full INT8, 500×52, threshold 0,45,
SHA-256 `ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.

- Kandidat baru v4–v7 diuji dengan filter raw-history, log normalization,
  receptive field panjang, skala train, dan temporal segments. Kandidat-kandidat
  tersebut tidak mengungguli v2 atau gagal parity; tidak menjadi model default.
- Diagnosis trigger v2: threshold motion 0,02 menolak seluruh train/validation
  window, termasuk fall. v8 mempertahankan bobot/threshold classifier, lalu
  mengalibrasi motion floor dari persentil 1 fall **train saja**: 0,0003443831.
- Recording-level trigger proxy pada validasi U19 berubah dari recall fall 0%
  menjadi 62,5%, specificity 64,9%, macro F1 0,636. Ini perbaikan trigger,
  bukan peningkatan akurasi classifier atau event-level/lapangan.
- Replay satu rekaman fall train benar-benar melalui EdgeRuntime dan memicu
  `suspected_fall`. Bentuk [1,500,52], probability 0,9375, motion 0,00074834,
  inferensi 0,346 ms. Bukan held-out test/performa manusia.
- Model/config/capture hash dibekukan dan perubahan preprocessing dengan hash
  yang dihitung ulang pun ditolak runtime. Override live channel/gap tetap
  dicatat sebagai profil engineering, bukan validasi domain.
- U21 sudah dilaporkan sekali untuk v2 (recall 62,5%, specificity 47,5%). U21
  tidak dibuka lagi untuk v4–v8. Perubahan berikut memerlukan test lokal baru.

Detail dan reproduksi: [MODEL_SETUP.md](../../MODEL_SETUP.md).
Target recall ≥88%, specificity ≥80%, empat kelas/presence/inactivity,
breathing anomaly dan Pi **belum terbukti**. Perbandingan validasi sudah
berulang; ia tidak menggantikan evaluasi independen baru.

## Verifikasi software terbaru

| Pemeriksaan | Hasil | Batas |
| --- | --- | --- |
| Backend unit/replay tests | 54 lulus, 3,467 detik | Fixtures/source replay; bukan lapangan |
| Frontend Vitest | 6 lulus | Render/route/freshness; bukan push delivery |
| Frontend TypeScript/Vite | Exit 0 lokal dan Vercel | Build |
| PGlite cloud | RLS/isolation/targeted commands/receipt/push lease/dedup/revoke lulus | Realtime dan delivery tidak diuji |
| Deno Edge Function | Check exit 0 | Typing |
| API smoke simulator port 8001 | Lima status, SSE, targeted ACK/idempotence, assistance tanpa auto-call lulus | Tidak memakai CSI/cloud |
| Production RLS/HTTP | Bukti di atas | Bukan sesi HP seluler |
| Supabase HTTPS→SQLite→receipt | Lima status, targeted ACK, bantuan, restart/retry, revoke lulus | Device simulasi; bukan UI/push HP |
| Blynk HTTPS→MQTT TLS→SQLite | V10/V11, reset pin, V12 lulus | Simulator; bukan tombol/push HP |
| UI Safari | Produksi signed-in, 390/1440, login preview | Push/PWA HP belum diperiksa |
| Shutdown SSE | Proses simulator keluar 5,3 detik | Layanan terpisah |

Log Python: `/private/tmp/srasta-tests-verified-20261001.log`.
Artifacts/model/raw CSI/private env tetap ignored. Tidak ada commit/push.

## Acceptance yang masih terbuka

1. Label aktivitas biasa dan exposure negatif independen pada CSI v8 sebelum
   menilai false alert. CSI asli setelah reconnect sudah mengalir.
2. HP seluler, install PWA, push warning/critical saat app tertutup, klik menuju
   kejadian, ACK/assistance cloud→SQLite→receipt, dan outage/recovery nyata.
3. Blynk mobile widgets/push dan aksi tombol pada HP. Alur API V10–V11 ke
   SQLite sudah lulus.
4. Raspberry Pi, alarm/buzzer/kamera, latensi dan alarm saat internet offline.
5. Data local independen beserta anotasi, model produk empat kelas, event/FAR,
   dan validasi napas/kamera. Scope proposal tetap dipertahankan seluruhnya.

**Sistem belum lulus seluruh acceptance.** Deployment dan transport CSI telah
terbukti; target model, Pi, dan delivery/response pada HP masih membutuhkan bukti.

# Blynk IoT SRASTA

Pada sesi konfigurasi sebelumnya, template **SRASTA** dan device **SRASTA Edge**
telah dibuat di akun yang diizinkan pengguna. Region koneksi device adalah
`sgp1.blynk.cloud`. Device lama tidak diubah. Kredensial berada di `.env` lokal
dan tidak dicatat dalam dokumen ini.

## Datastream

| Pin | Nama MQTT | Tipe | Rentang |
| --- | --- | --- | --- |
| V0 | System State Code | Integer |0..4|
| V1 | System Status | String | |
| V2 | Activity | String | |
| V3 | Breathing Estimate | Double |0..60|
| V4 | Breathing Quality | Integer |0..100|
| V5 | Fall Anomaly Confidence | Integer |0..100|
| V6 | Signal Quality | Integer |0..100|
| V7 | Last Event | String | |
| V8 | Edge Health | String | |
| V9 | Local Alarm | Integer |0..1|
| V10 | Acknowledge Alert | Integer |0..1|
| V11 | Request Assistance | Integer |0..1|
| V12 | Simulation Mode | Integer |0..1|

V0: standby0, normal1, inactive2, anomaly3, critical4. V5 display name dapat
“Fall/Anomaly Confidence”; nama datastream MQTT menggunakan bentuk tanpa `/`
karena console menolak slash. Napas tidak andal dikosongkan melalui topic erase,
bukan diganti0. V12=1 wajib untuk simulator/replay. Skor model V5 dan kualitas
sinyal V6 juga dikosongkan ketika pengamatan tidak tersedia. V0 mempertahankan
kategori terakhir; tampilkan bersama V1/V8 yang menyatakan data terputus.

## Koneksi persistent dan tindakan

```text
host: sgp1.blynk.cloud
port: 8883 TLS
username: device
password: token device dari .env
keepalive: 45 detik
clean_session: true
```

Paho berjalan dalam loop persistent, menerbitkan ringkasan setiap30 detik atau
ketika status/koneksi pengamatan berubah. TLS diverifikasi. Redirect URI `mqtts://region:8883`
hanya diterima untuk domain resmi Blynk, lalu koneksi lama dihentikan dari
worker sebelum menghubungkan regionbaru. Satu token tidak dipakai dua client.

V10/V11 adalah tombol **push**, bukan switch permanen. Input1 diterapkan
di SQLite lalu widget direset0. Duplicate QoS yang ditandai broker didedup.
ACK Blynk menargetkan alert terakhir yang belum diakui; app SRASTA sendiri
menargetkan UUID kejadian yang dipilih. Permintaan bantuan dicatat sebagai
tindakan caregiver; tidak memanggil nomor darurat otomatis.

## Events

| Code | Tipe | Kondisi |
| --- | --- | --- |
| `srasta_warning` | Warning | inactive/anomaly |
| `srasta_critical` | Critical | critical |
| `srasta_device_offline` | Warning | RX/aliran CSI hilang |

Ketiga event sebelumnya disimpan dengan timeline, homescreen, dan push Device
Owner aktif. Batas notifikasi platform yang terlihat saat konfigurasi adalah
1jam. Adapter membatasi event yang sama60 detik; kondisi critical berkepanjangan
tidak dikirim setiap frame. Rate limit akun/platform dapat menghalangi push
ulang walaupun nilai datastream diperbarui. Deskripsi event simulator/replay
memakai awalan `SIMULASI:`; cooldown simulasi terpisah dari event live.

## Dashboard Blynk dan bukti yang belum selesai

Dashboard mobile Blynk perlu dibuat di app Blynk: halaman status, warning,
critical, dan history; gunakan V0–V12 serta tombol push V10/V11. Dashboard web
console dapat memakai widget label/gauge/superchart dari datastream yang sama.
App caregiver SRASTA yang terpisah sudah memiliki keempat halaman utama dan
alur ACK/history; itu tidak otomatis memasang widget di aplikasi Blynk mobile.

Pada 1 Oktober 2026, MQTT TLS terhubung dan alur API V10/V11→MQTT→SQLite
telah lulus dengan database simulasi terpisah. V12=1 dibaca kembali sebelum
simulasi critical, kedua tindakan tersimpan, kedua pin kembali 0, dan tidak
ada auto-call. Bukti: `artifacts/blynk-acceptance-20261001/report.json` (ignored).
Ini belum membuktikan tombol atau push nyata pada HP. Uji setelah HP Blynk pengguna
terhubung: hentikan client live terlebih dahulu, jalankan simulator dengan
`--env .env` secara eksplisit, periksa
V12=1, trigger anomaly dan critical dengan jarak sesuai rate limit; ACK/V11
harus tercatat pada `/events` dan `/actions`. Setelahnya matikan demo mode untuk
uji CSI asli. Data CSI mentah tidak dikirim ke Blynk.

Referensi protokol: [Authentication](https://docs.blynk.io/en/blynk.cloud-mqtt-api/device-mqtt-api/authentication),
[Datastreams](https://docs.blynk.io/en/blynk.cloud-mqtt-api/device-mqtt-api/datastreams),
[Events](https://docs.blynk.io/en/blynk.cloud-mqtt-api/device-mqtt-api/events).

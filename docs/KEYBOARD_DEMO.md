# Demo manual Raspberry Pi

## Jalankan dari Terminal Mac

Tidak perlu masuk SSH secara terpisah atau pindah folder:

```bash
bash "/Users/Shandy/Documents/Lomba/GEMASTIK/IoT/SRASTA_CSI_Bench_Blynk/scripts/run_keyboard_demo_mac.sh"
```

Launcher memakai key privat proyek yang sudah terdaftar dan host
`srasta@192.168.1.15` (alamat yang diberikan pemilik pada 27 Oktober).
Setelah tulisan IDLE muncul, tekan Space/R/Q di terminal Mac yang sama.
Website HP mengikuti status dari Pi melalui cloud. Mac harus dapat menjangkau
SSH Pi, biasanya pada Wi-Fi yang sama. Key dan cloud credential tidak dicetak.

Jika IP berubah, tambahkan `--host srasta@IP_BARU`. `--mute` membisukan buzzer
dan `--key /path/key` memilih key lain. Saat Q/Ctrl+C, layanan normal Pi
dipulihkan oleh wrapper di Pi. Perintah `--help` menampilkan ringkasan opsi.

## Jalankan di terminal Pi

Jalankan di terminal Pi (termasuk setelah SSH):

```bash
bash ~/SRASTA-WiFi-CSI/scripts/run_keyboard_demo.sh
```

Program mulai **IDLE**: OLED menampilkan IDLE, LED hijau menyala, buzzer diam.
Tekan **Space** sekali, tanpa Enter, untuk **JATUH TERDETEKSI**: LED merah
menyala dan piezo berbunyi cepat. Status bertahan sampai **R** ditekan untuk
kembali idle. **Q**, Ctrl+C, atau koneksi terminal terputus menghentikan demo,
mematikan output, dan memulihkan panel otomatis jika sebelumnya aktif.

Jika menjalankan langsung dari Mac dalam satu perintah SSH, gunakan `ssh -t`
agar tombol diteruskan ke terminal Pi. Tekan tombol di terminal yang menjalankan
program. Untuk demo tanpa bunyi, tambahkan `--buzzer off`.

Wiring mengikuti `device_panel.py`: merah BCM27/pin13, kuning BCM22/pin15,
hijau BCM17/pin11, piezo BCM16/pin36, OLED SSD1306 SPI0 CE0/DC24/reset25.
Program memakai Python OS Pi beserta library panel yang sudah terpasang.
Skrip berbagi lock dengan `test_devices.sh` agar kedua demo tidak berebut GPIO.

OLED dan terminal menandai **simulasi manual**. Program tidak memerlukan
ESP32 atau inferensi model. Tanpa opsi cloud, service CSI tetap berjalan;
panel lokal otomatis dijeda sementara. Tidak membuka kamera.
Status demo tersimpan terpisah dalam
`~/srasta-edge/state/keyboard-demo.json`, berlabel `simulation: true`, tanpa
skor model buatan. Setiap menjalankan program selalu mulai idle, bukan memuat
status jatuh dari sesi sebelumnya.

## Pi → website HP

Jalankan melalui wrapper agar hanya ada satu pengirim cloud untuk perangkat:

```bash
bash ~/SRASTA-WiFi-CSI/scripts/run_keyboard_demo.sh \
  --cloud-env ~/srasta-edge/edge.env
```

Buka <https://srasta-caregiver.vercel.app> di HP dan pilih SRASTA Edge.
Pi dan HP memerlukan internet; HP tidak harus berada di Wi-Fi yang sama.
Gunakan file credential Pi yang sudah ada, tanpa menyalin token ke browser.
Program memulai status IDLE, lalu Space di terminal Pi mengubah perangkat
dan ringkasan cloud menjadi JATUH TERDETEKSI. R mengembalikannya ke IDLE.
Pengiriman status dibangunkan saat tombol berubah dan heartbeat setiap satu
detik. Dashboard mempercepat polling menjadi satu detik setelah mendeteksi
demo Pi; peralihan awal dari pemantauan biasa dapat menunggu polling lima detik.
Waktu aktual bergantung koneksi; bukan klaim latensi deteksi CSI.

Mode ini menjeda service edge dan panel sementara agar status live tidak
menimpa status demo. Keluar dengan Q/Ctrl+C untuk memulihkan keduanya jika
sebelumnya aktif. Hanya snapshot simulasi yang dikirim; tidak menambahkan
care event, mengirim push, menjalankan kamera, atau memproses tindakan caregiver.
Saat internet putus, tombol dan alarm lokal tetap bekerja. Website menandai
DEMO TERPUTUS setelah ringkasan kedaluwarsa; pengiriman berikutnya memakai
status tombol terbaru. Saat keluar, program mencoba menandai demo berhenti,
lalu service live yang dipulihkan kembali menjadi pengirim cloud.

`/?demo=keyboard` di website adalah pratinjau browser mandiri untuk memeriksa
tampilan tanpa Pi. Untuk mengikuti tombol Pi di HP, gunakan URL dashboard
biasa, **tanpa** parameter demo tersebut.

Uji tombol tanpa GPIO/OLED pada Mac/Linux:

```bash
PYTHONPATH=code python3 -m srasta_csi.keyboard_demo --terminal-only \
  --status-file /tmp/srasta-keyboard-demo.json
```

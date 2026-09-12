# Perangkat SRASTA

## Topologi sesi ini

Pengguna mengonfirmasi **satu ESP32-S3 sebagai receiver**, tersambung USB-C ke USB-C; **hotspot HP menggantikan transmitter WiFi**. Port receiver teridentifikasi **COM9** (USB native Espressif). Raspberry Pi, kamera, buzzer/LED belum tersedia; lanjutkan pengujian di laptop. Firmware TX tetap disediakan dan dibangun, tetapi tidak boleh diklaim diuji pada board TX fisik.

Firmware membatasi penerimaan ke BSSID hotspot yang dikonfigurasi. Receiver berasosiasi dengan hotspot, meminta HT20, lalu mengirim ping gateway dengan target 100/s agar ada trafik masuk. Timeout balasan dibatasi satu interval trafik (10 ms pada 100 Hz), sebab ESP-IDF menunggu receive sebelum mengirim ping berikutnya. Counter ping_sent/replies/timeouts/reply_ms tersedia dalam diagnostics numerik. HP menentukan mode/rate paket aktual; paket selain HT/HT20/LLTF-128 tetap ditolak. Target trafik 100 Hz **bukan bukti** sampling 100 Hz tercapai. Topologi hotspot memiliki domain RF/traffic berbeda dari pasangan ESP-NOW TX/RX dan corpus penelitian.

## Toolchain dan konfigurasi

`firmware/platformio.ini`: PlatformIO espressif32 **6.10.0**, ESP-IDF **5.4.0**, board `esp32-s3-devkitc-1`. Environment: `tx`, `rx`, `rx_hotspot`. Console USB Serial/JTAG, baud host 921600. Tidak perlu sambungan UART TX/RX terpisah untuk board dengan USB native ini.

```powershell
.venv/Scripts/python -m pip install platformio==6.2.0
$env:PLATFORMIO_CORE_DIR = Join-Path $env:LOCALAPPDATA 'srasta-pio'
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
.venv/Scripts/python -m platformio device list
```

Gunakan folder core pendek di profil pengguna pada Windows. Pada sesi ini ekstraksi awal dalam repository OneDrive gagal karena panjang path; menjalankan compiler dari `C:\Windows\Temp` gagal dengan Windows error 5. Compiler yang sama dapat berjalan dari folder pengguna. Jangan memakai lokasi cache historis itu pada instruksi baru.

Default dua board: channel 1, sender MAC locally administered sintetis `02:00:00:00:00:01`, target 100 Hz. Template ada di `firmware/include/srasta_config.h`. Override nonsecret melalui `firmware/include/srasta_local.h` yang diabaikan Git. Kedua board harus memakai channel/sender sama.

Untuk hotspot, salin `firmware/hotspot.example.json` ke `artifacts/hotspot.local.json`, kemudian isi SSID, password, channel 2.4 GHz saat ini, dan BSSID HP. Jangan masukkan password di argumen compiler, command line, README, atau chat. Pengguna sudah mengisi berkas privat sesi ini.

```powershell
.venv/Scripts/python code/tools/configure_hotspot.py
.venv/Scripts/python -m platformio run -d firmware -e tx -e rx -e rx_hotspot
```

Generator memvalidasi input dan membuat `firmware/include/srasta_hotspot.local.h`. Header, firmware `.bin`, SDK config, seluruh `.pio`, dan JSON lokal tidak masuk Git. Jangan mendistribusikan binary hotspot: credential tertanam di binary flash. Hotspot yang berubah BSSID/channel/password perlu header baru dan build/flash ulang.

## Flash receiver yang sudah diidentifikasi

Tutup serial monitor/edge service/probe lain terlebih dahulu.

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path $env:LOCALAPPDATA 'srasta-pio'
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
.venv/Scripts/python -m platformio run -d firmware -e rx_hotspot -t upload --upload-port COM9
.venv/Scripts/python code/tools/verify_serial.py --port COM9 --seconds 45 --out artifacts/hardware-serial.json
```

Script verifikasi mengonsumsi frame melalui validator/runtime yang sama dan menulis **ringkasan saja**: profil, jumlah frame valid/ditolak, laju teramati, rentang SNR, MCS, flag invalid-word, waktu inference, serta state. Tidak menyimpan raw I/Q atau MAC. Exit nonzero jika frame valid atau inference tidak tercapai. Bukti harus dibaca, bukan menganggap flash sukses membuktikan CSI sukses.

Lalu jalankan dashboard live:

```powershell
.venv/Scripts/python code/run_edge_service.py --serial-port COM9 --hotspot-config artifacts/hotspot.local.json --db artifacts/live.sqlite3 --port 8000
```

Untuk pasangan dua board kelak, tentukan port masing-masing dahulu. Flash `-e tx -t upload --upload-port <PORT_TX>` dan `-e rx -t upload --upload-port <PORT_RX>`. Jalankan edge `--serial-port <PORT_RX> --sender-mac 02:00:00:00:00:01 --channel 1`. Jangan mengganti peran COM9 menjadi TX pada setup hotspot ini.

## Kontrak RX dan diagnostics

Frame JSONL versi 1 memiliki sequence, waktu mikrodetik monotonic, sender, RSSI/noise, channel, bandwidth, signal mode, MCS, rx_state, len, first_word_invalid, dan 128 signed bytes. CSI callback menyalin ke queue 64 tanpa blocking/print di task WiFi. LLTF aktif; HT-LTF/STBC-LTF/merge/filter dimatikan. [imaginary,real] dipertahankan dari driver, lalu host mengambil indeks `6..31,33..58`. Tidak ada penyesuaian bentuk diam-diam.

Baris `# SRASTA` adalah diagnostics; host mengabaikannya sebagai data. `rejected` menandakan paket sender dengan profil tidak cocok; `queue_dropped` kehilangan di firmware; `observed`, `last_len`, `last_mode` membantu membedakan gagal asosiasi dari format paket yang tidak kompatibel. Sequence gap pada host mencakup paket sender yang ditolak firmware dan antrean hilang, sehingga bukan estimasi packet loss RF murni. Ping ditujukan hanya ke gateway hotspot yang dipilih, bukan host lain.

Recovery: pastikan hotspot 2.4 GHz aktif, data cable mampu transfer, periksa kembali port setelah reset, tutup pembaca serial ganda. Jika upload memerlukan bootloader, tahan BOOT dan tekan RESET lalu lepas BOOT; periksa port baru sebelum mencoba lagi. Jangan membuat payload 104/256 byte terlihat 128 dengan padding/trimming. Jika HP tidak memberikan HT LLTF-128 kontinu, catat blocker traffic/profile dan gunakan pasangan TX/RX terkontrol ketika tersedia.

## Bukti pemulihan USB sesi ini

COM9 pernah terdeteksi tanpa byte/respons reset esptool. Pembukaan ulang otomatis belum memulihkannya; cabut-pasang USB pengguna memulihkan aliran. Uji API 45,17 detik setelah itu: 4.466 frame tambahan (100,00 Hz), 179 inference, semua polling fresh/ready, tanpa tambahan reject/drop/reconnect. Aturan gerakan memakai `--max-packet-gap-ms 100` berdasarkan jitter hotspot terukur. Uptime lama dan akurasi deteksi belum terbukti.

Bukti terpisah: `artifacts/receiver-recovered.json` dan `artifacts/live-ui-recovered/`. Tidak perlu flash ulang pada pemulihan ini; jangan menghapus riwayat alert untuk memperbaiki USB.

## Pi, kamera, dan alarm kelak

Pi membaca RX melalui USB. Gunakan catu stabil, common ground, dan koneksi menurut pinout board. Adapter `--gpio-pins BUZZER GREEN ORANGE RED` memakai **nomor BCM**, empat pin unik. LED memerlukan resistor seri; buzzer beban lebih besar memerlukan transistor/driver sesuai rating, bukan langsung dibebankan ke GPIO. Jangan memakai pin5V sebagai signal input Pi. Wiring aktual belum dipilih atau diuji.

`--camera-model <movenet-lightning.tflite> --camera-index 0` mengaktifkan kamera lokal saat anomali saja. Input MoveNet `[1,192,192,3]`; tiga frame singkat diubah menjadi 17 keypoint. Kamera dilepas setelah capture. UI hanya menerima skeleton; SQLite tidak menyimpan gambar/keypoint. Konsistensi pose horizontal dapat mendukung anomali yang sudah ada, bukan diagnosis jatuh mandiri. Hasil yang terlambat atau milik event lama ditolak. Fixture adapter sudah diuji; kualitas pose dan pembukaan kamera fisik belum terbukti.

Alarm critical aktif sampai acknowledgement; LED merah tetap mengikuti critical. Restart memulihkan critical/ack dari SQLite. Simulasi/replay tidak boleh menjadi bukti buzzer fisik bekerja. Uji fisik hanya ketika perangkat tersedia, tanpa meminta siapa pun menjatuhkan diri.

## Notifikasi opsional

Default nonaktif, simulator/replay tidak mengirim keluar. Aktifkan `--enable-notifications` hanya pada serial dengan credential lokal:

- Blynk: environment `SRASTA_BLYNK_TOKEN`; event code `srasta_inactive`, `srasta_anomaly`, `srasta_critical` harus tersedia pada template Blynk.
- MQTT: `SRASTA_MQTT_HOST`, `SRASTA_MQTT_USER`, `SRASTA_MQTT_PASSWORD`, TLS port 8883, topic `srasta/events`.

Jika kedua konfigurasi tersedia, Blynk dipilih. Hanya id/status/reason/waktu/source yang dikirim. Tidak ada raw CSI, MAC, nama, gambar, atau password di event. Queue dibatasi dan rate-limit 30 detik per severity. Credential hilang atau transport gagal tidak menggagalkan keputusan lokal; kegagalan tampil sebagai counter. Pengiriman eksternal nyata belum dilakukan pada sesi ini.

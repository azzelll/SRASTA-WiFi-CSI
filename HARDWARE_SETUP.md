# TX/RX dan edge SRASTA

## Peran yang telah dikonfirmasi secara fisik

| Label | Port yang pernah terlihat | Firmware | Serial |
| --- | --- | --- | --- |
| TX | `/dev/cu.usbmodem1234561`, lalu `/dev/cu.usbmodem1101` saat download | `firmware/esp32_s3_csi_tx` | USB115200 untuk provisioning |
| RX | `/dev/cu.usbserial-310` | `firmware/esp32_s3_csi_serial` | UART1,000,000 |

Mapping berasal dari cabut/pasang satu board berlabel pada sesi sebelumnya.
Port baru **harus diverifikasi kembali**. Jangan memakai port TX untuk flash
RX. USB Mac kiri/kanan tidak menentukan role. Cabut satu board berlabel,
bandingkan `ls /dev/cu.usb*`, pasang kembali, lalu cek port yang muncul.
Board boleh dicabut ketika tidak sedang flash/provision/ditangkap serial.

## Trafik dan capture

TX menjadi SoftAP `SRASTA_CSI`, channel6 HT20, dan mengirim UDP unicast ke RX
setiap20ms. RX hanya menerima CSI dari BSSID yang dikontrol, LLTF-only,
HT20/HT, panjang128, rx_state0. Kredensial WiFi disimpan NVS melalui USB;
tidak ditanamkan di source. Tidak ada fallback ke hotspot/passive capture.
TX tidak menjalankan animasi RGB. LED RGB TX sudah dikonfirmasi pengguna
padam setelah flash sebelumnya; LED power terpisah bergantung rangkaian board.

Kontrak host: signed `[imag,real]`, `hypot`, indeks6..31+33..58 →52 amplitudo.
Metadata radio/sequence/timestamp diperiksa; mismatch masuk karantina.
Tidak ada padding/resize/penggeseran indeks.

## Build dan flash (ESP-IDF5.5.3)

```bash
. /absolute/path/esp-idf/export.sh
idf.py -C firmware/esp32_s3_csi_tx set-target esp32s3
idf.py -C firmware/esp32_s3_csi_tx build
idf.py -C firmware/esp32_s3_csi_serial set-target esp32s3
idf.py -C firmware/esp32_s3_csi_serial build
# Gunakan port yang baru diverifikasi, bukan menyalin port dari tabel secara buta.
idf.py -C firmware/esp32_s3_csi_tx -p "$SRASTA_TX_PORT" flash
idf.py -C firmware/esp32_s3_csi_serial -p "$SRASTA_RX_PORT" flash
```

Jika TX perlu download mode: tahan BOOT, tekan/lepas RESET/EN, lepas BOOT;
cek port yang muncul; flash **TX saja**. Setelah flash tekan RESET/EN tanpa
BOOT agar firmware berjalan. RX menggunakan UART0 console1M sesuai
`sdkconfig.defaults`. Kecepatan921600 pernah garbled pada CH340 Mac;
115200 kehilangan banyak paket.1M adalah konfigurasi engineering saat ini.

## Provision WiFi

Simpan `SRASTA_WIFI_PASSWORD` pada `.env` lokal (chmod600), lalu:

```bash
.venv/bin/python code/provision_wifi.py --role tx --port "$SRASTA_TX_PORT"
.venv/bin/python code/provision_wifi.py --role rx --port "$SRASTA_RX_PORT"
```

Gunakan opsi port/role/baud yang ditampilkan helper. Provision password yang
sama pada TX/RX, restart kedua board. NVS memiliki key berbeda sesuai role;
source dan log tidak boleh memuat password. Jangan membuka monitor serial
bersamaan dengan edge reader.

## Penempatan dan Pi

Satu ruangan dan satu orang untuk pengujian awal. TX/RX berada pada dua sisi
ruangan, sekitar2–5m, tinggi0.8–1.2m sesuai proposal; hindari penghalang logam.
RX USB ke Pi, TX USB untuk daya. Pi4B memakai adaptor5V3A. Raspberry Pi
akan disambungkan pengguna pada tahap berikutnya.

GPIO Pi3.3V. Buzzer/LED menggunakan driver/resistor dan ground bersama sesuai
komponen, bukan beban5V langsung pada GPIO. BCM18 hanya contoh konfigurasi;
verifikasi wiring fisik sebelum memakai `--alarm gpio`. Kamera Pi/CCTV
tidak aktif kontinu; adapter yang tersedia sekarang adalah kamera Picamera2
dengan MoveNet Lightning lokal. Integrasi CCTV lain belum diuji.

## Bukti dan batasannya

Sebelumnya100frame di1M diterima tanpa gap, semuanya128I/Q→52amplitudo.
Run lebih panjang kemudian kehilangan sekitar6.52%,36karantina, dan stall
setelah2568frame; membuka ulang serial memulihkan aliran. Reader sekarang
menambahkan pemulihan stall dan reset session; keberhasilan jangka panjang
harus diuji ulang pada board setelah reconnect. Hasil short-run bukan bukti
deteksi jatuh, ketepatan napas, atau stabilitas24jam.

Pengujian berikutnya:20menit capture, kehilangan paket dan gap maksimum,
cabut/pasang RX, reset RX, status stale/restore, aktivitas aman sehari-hari,
latensi edge/app, alarm lokal ketika cloud terputus. Jangan meminta orang
melakukan jatuh berbahaya untuk memperoleh bukti.

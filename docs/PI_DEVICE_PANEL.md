# OLED, tiga LED dan piezo lokal

Ditambahkan 23 Oktober 2026 atas permintaan pemilik. Panel membaca
`GET http://127.0.0.1:8000/api/caregiver` di Pi. Satu-satunya reader USB RX
tetap layanan edge. Panel tidak menulis kejadian ke DB/cloud, mengubah model,
atau mengganti state machine, motion gate dan threshold model 0,45.

## Aturan indikator

Nilai yang dipakai adalah `fall_confidence` (0–1), sama dengan skor fall
di dashboard. Nilai ini adalah skor model, bukan akurasi atau konfirmasi jatuh.

| Skor lokal | LED | OLED | Piezo pasif |
| --- | --- | --- | --- |
| >=85% | Merah | INDIKASI JATUH + skor | 120 ms bunyi / 120 ms diam |
| >=75% dan <85% | Kuning | WASPADA + skor | 200 ms bunyi / 800 ms diam |
| <75% | Hijau | SKOR RENDAH + skor | Diam |
| Live terhubung tetapi skor tidak valid/tersedia | Semua mati | MENUNGGU SKOR | Diam |
| CSI/HTTP putus, stale, simulator atau replay | Semua mati | CSI OFFLINE | Diam |

Nada piezo dikonfigurasi 2 kHz, duty 50% saat berbunyi. Ini setelan program,
bukan pengukuran frekuensi/duty dengan osiloskop. LED merah tetap menyala;
yang dipercepat adalah pola bunyi. Warna mengikuti skor mentah, sebelum
pembulatan persen tampilan. Skor persis 75% kuning; persis 85% merah.
Ambang panel diperbarui pada 23 Oktober atas permintaan pemilik.

Data harus berasal dari `live`, non-simulasi, serial terhubung, monitoring
online, timestamp dan stream age maksimal 3 detik. Skor juga harus lolos
`state_verified` dan pemeriksaan finite/range. API edge sendiri hanya
menyajikan confidence inferensi terkini (<10 detik). Cache HTTP kedaluwarsa
setelah 3 detik; HTTP gagal langsung menghasilkan offline. Thread HTTP
terpisah agar timeout request tidak menahan timer piezo.

Panel menampilkan ambang skor khusus permintaan pengguna; state dashboard
tetap mempertimbangkan motion gate/inactivity/kamera. Warna panel bukan
pengganti status kejadian dashboard atau bukti akurasi lokal.

## Wiring yang dipertahankan

Angka 11/13/15 dari pemilik adalah **nomor fisik header**, bukan BCM.

| Komponen | Sinyal | Pin fisik | BCM |
| --- | --- | --- | --- |
| LED merah | Anoda lewat resistor 330 ohm | 13 | 27 |
| LED kuning | Anoda lewat resistor 330 ohm | 15 | 22 |
| LED hijau | Anoda lewat resistor 330 ohm | 11 | 17 |
| Piezo pasif | Positif lewat resistor 330 ohm | 36 | 16 |
| OLED SSD1306 SPI 128x64 | VCC 3,3 V | 1 | — |
| OLED | GND | 6 | — |
| OLED | D0/CLK/SCL | 23 | 11 |
| OLED | D1/MOSI/SDA | 19 | 10 |
| OLED | RES/RST | 22 | 25 |
| OLED | DC | 18 | 24 |
| OLED | CS/CE0 | 24 | 8 |

Mapping LED dikoreksi dari warna fisik yang dilaporkan pemilik pada self-test
26 Oktober 2026: merah **BCM27**, hijau **BCM17**, dan kuning **BCM22**.
Pada konfigurasi sebelumnya, tahap kuning menyalakan merah, tahap merah
menyalakan hijau, dan tahap hijau menyalakan kuning. Panel dan tes memakai
mapping hasil pengamatan tersebut.

Katoda semua LED dan negatif piezo ke rail GND bersama yang tersambung pin 6.
Setiap LED memakai resistor sendiri. Pada 26 Oktober 2026, pemilik memindahkan
piezo ke **BCM16 / pin fisik 36**; konfigurasi panel dan self-test mengikuti pin
tersebut. Konfigurasi memakai piezo pasif kecil yang sesuai GPIO 3,3 V, tanpa
transistor; jenis/arus komponen belum diperiksa langsung.
Jika buzzer ternyata aktif/magnetik atau bebannya tidak sesuai GPIO, hentikan
panel dan gunakan driver yang sesuai. Jangan menyambungkan 5 V ke GPIO.

SPI dan library `RPi.GPIO`, `luma.oled`, Pillow sudah tersedia pada Python OS
Pi saat pemasangan; tidak ada instalasi paket atau perubahan venv produksi.
Rujukan: [wiring luma SPI](https://luma-oled.readthedocs.io/en/stable/hardware.html#spi),
[instalasi rpi-lgpio](https://rpi-lgpio.readthedocs.io/en/latest/install.html).

## Operasi pada Pi

Unit `/home/srasta/.config/systemd/user/srasta-device-panel.service`
menjalankan `/usr/bin/python3 -u -m srasta_csi.device_panel` dari folder
`/home/srasta/SRASTA-WiFi-CSI/code`, dengan `--buzzer passive`.
Source unit ada di `scripts/srasta-device-panel.service`. User srasta sudah
memiliki akses grup gpio/spi. Unit enabled; uji reboot fisik belum dilakukan.
Kegagalan adapter tidak merestart layanan CSI. GPIO dilepas, layar dibersihkan,
dan piezo dimatikan saat SIGTERM/Ctrl+C.

```bash
systemctl --user status srasta-device-panel.service --no-pager
cat ~/srasta-edge/state/device-panel.json
systemctl --user restart srasta-device-panel.service
```

Status file ditulis atomik mode 0600; hanya skor/level/waktu/error adapter,
tanpa raw CSI, event pribadi atau credential. Log transisi ada di journal
jika journal user tersedia; status file tidak bergantung pada journal.

Hentikan panel sebelum program lain memakai pin yang sama:

Cara praktis untuk tes ketiga perangkat sekaligus pada Pi:

```bash
bash ~/SRASTA-WiFi-CSI/scripts/test_devices.sh
```

Skrip menghentikan panel live sementara, menjalankan tes 10 detik, kemudian
memulihkan panel jika sebelumnya aktif. Pemulihan juga dicoba ketika tes gagal
atau dihentikan Ctrl+C. Lock mencegah dua salinan skrip tes bersamaan.
Layanan pembaca CSI tetap berjalan. Tes tidak membutuhkan RX/TX online.

Perintah manual yang setara (pulihkan panel sendiri setelah Ctrl+C):

```bash
systemctl --user stop srasta-device-panel.service
cd ~/SRASTA-WiFi-CSI/code
/usr/bin/python3 -m srasta_csi.device_panel --buzzer passive --self-test
systemctl --user start srasta-device-panel.service
```

Self-test 10 detik: hijau 30%, kuning 80%, merah 90%, offline. OLED bertanda
SIMULASI TES. Tidak mengakses API produksi, membuka kamera/serial, atau
membuat alert. Tidak memerlukan orang melakukan jatuh.

Untuk mematikan autostart dan semua output panel:

```bash
systemctl --user disable --now srasta-device-panel.service
```

Tes logika tanpa GPIO:

```bash
cd ~/SRASTA-WiFi-CSI/code
/usr/bin/python3 -m unittest discover -s tests -p test_device_panel.py -v
```

Status pengujian dan keterbatasan: [bukti pemasangan](evidence/20261023-device-panel.md).

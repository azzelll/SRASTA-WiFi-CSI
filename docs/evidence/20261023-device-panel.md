# Panel lokal Pi — 23 Oktober 2026

## Permintaan dan implementasi

Pemilik meminta indikator skor lokal: >70% merah dan bunyi cepat dengan
tulisan jatuh pada OLED; 50–70% kuning dengan bunyi biasa; <50% hijau.
Nomor header yang diberikan: merah 11, kuning 13, hijau 15. Wiring sebelumnya
dipertahankan: BCM17/27/22 untuk LED; BCM18/pin12 piezo pasif; SSD1306 SPI0
CE0, DC24, reset25. Persis 70% masuk kuning. OLED merah bertuliskan
INDIKASI JATUH, untuk membedakan skor dari konfirmasi kejadian.

Source: `code/srasta_csi/device_panel.py`, unit template
`scripts/srasta-device-panel.service`, panduan `docs/PI_DEVICE_PANEL.md`.
Adapter GET API caregiver localhost; tidak membuka serial atau menulis
kejadian/command/cloud. HTTP polling di thread terpisah dari timer buzzer.
Offline, replay/simulator, data stale atau skor invalid tidak menjadi hijau.

## Pemeriksaan langsung di Pi

- Host srasta-edge, melalui SSH; kode disunting lewat Windows dan dieksekusi
  di Pi. SPI0.0, grup gpio/spi serta library Python OS tersedia. Tidak
  memasang paket, reboot, atau mengubah environment produksi.
- Existing alarm edge adalah disabled, sehingga tidak bersaing untuk BCM18.
- Tes logika terarah: 8 tes, 0,010 detik, OK. Meliputi batas 50/70%, invalid
  score, replay/simulator, stale timestamps, koneksi putus, eksklusivitas LED,
  pola bunyi, mode buzzer off dan cleanup walau PWM gagal.
- Seluruh suite pada dev venv Pi: **128 tests, 35,127 detik, OK**.
  Command:
  `PYTHONPATH=code OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 TF_NUM_INTRAOP_THREADS=2 TF_NUM_INTEROP_THREADS=1 .venv/bin/python -m unittest discover -s code/tests -v`.
- Self-test perangkat 10 detik, exit 0. Label SIMULASI TES di OLED; stage
  green30%, yellow60%, red85%, offline. `pinctrl get` membuktikan BCM22 high
  pada hijau, BCM27 pada kuning, BCM17 pada merah, LED lainnya low pada
  masing-masing stage dan semua low pada stage offline. Tidak membuat
  event produksi, membuka kamera atau mengganti input serial dengan fixture.
- PWM dan transfer OLED selesai tanpa error. Pin buzzer tersampel low;
  pencuplikan pin bukan pengukuran waveform/frekuensi. Tidak ada pembacaan
  balik piksel OLED melalui SPI.
- Adapter stop/start diuji: GPIO LED dilepas menjadi input, BCM18 low.
  Input BCM22 sempat terbaca high sesudah release; ini bukan output driven
  high dan bukan bukti arus/keadaan cahaya LED. Program mengirim LOW sebelum
  melepas pin. Verifikasi visual shutdown tersendiri belum dilakukan.
- Unit panel active/running, enabled, NRestarts=0; start terakhir PID1845.
  Unit edge tetap PID1019, NRestarts=0; tidak direstart selama pemasangan.
- Setelah panel aktif: source live, serial connected, state verified;
  accepted_frames **23.038 -> 23.295** dalam 8 detik (+257), quarantine0.
  Skor API pada dua sampel 0,81640625 dan 0,58203125; status panel tersampel
  yellow, score0,52734375, simulationfalse, errornull. Skor dapat berubah
  selama polling sehingga sampel API dan panel tidak harus identik waktunya.
- SHA256 model v8 tetap
  `ac8ca20e9bd0c70a006b9fc7c410c44e6e887e8ffd1174692be3ac3277436e66`.
- Pemilik kemudian mengonfirmasi **"sudah aman semua"** setelah diminta
  memeriksa OLED, LED dan bunyi fisik. Ini konfirmasi pengguna, bukan
  observasi visual/audio agen atau pengukuran instrumen.

## Artefak dan batas bukti

Log lokal pada Pi (tidak dipublikasikan):
`/home/srasta/SRASTA-WiFi-CSI/artifacts/setup/20261023-device-panel/`:
`hardware-self-test.log`, `hardware-results.json`, `backend-tests.log`,
`live-results.json`. Status live privat:
`/home/srasta/srasta-edge/state/device-panel.json`.
Unit dipasang ke `/home/srasta/.config/systemd/user/srasta-device-panel.service`.

Pemilik menyatakan wiring buzzer tetap seperti sebelumnya; jenis/arus
komponen tidak diukur agen. Program mengasumsikan piezo pasif kecil yang
sesuai GPIO3,3V dengan resistor seri330ohm, bukan beban magnetik/5V langsung.
Boot fisik belum diuji. Model/state machine, UI Figma dan lima fitur tidak
diganti. Tidak ada training, raw recording, ground truth, pengukuran akurasi,
pengambilan kamera baru oleh tes panel, atau upload data pribadi.
Recall62,5%/specificity64,9% tetap hasil historis proxy; ambang panel
50/70 bukan peningkatan akurasi atau kalibrasi probabilitas lokal.

## Skrip tes perangkat yang dapat diulang

Atas permintaan berikutnya, ditambahkan `scripts/test_devices.sh` sebagai
perintah tunggal untuk menghentikan panel sementara, mengunci tes, menjalankan
self-test 10 detik, dan memulihkan panel yang tadinya aktif. Syntax `bash -n`
lulus; eksekusi pada Pi selesai exit0, melalui green/yellow/red/offline,
dan mencetak "Panel live dipulihkan". Penghentian terkontrol dengan SIGINT
pada process group tes menghasilkan exit130 dan juga memulihkan panel.
Tidak menghentikan/restart layanan edge; kedua unit kembali active,
NRestarts0. Komponen fisik pada pengulangan ini tidak diamati agen.

Pada pemeriksaan setelah pengulangan, health edge menunjukkan serial
disconnected, frame0, CSI offline. Panel live dengan benar kembali
menampilkan CSI OFFLINE (simulationfalse), bukan skor hijau sintetis.
Ini kondisi koneksi saat pengecekan baru, tidak membatalkan bukti frame
live pada checkpoint sebelumnya di atas. Tes perangkat tidak membutuhkan
CSI terhubung dan tidak membuktikan akurasi model.

## Pembaruan ambang panel 75/85

Permintaan pemilik berikutnya pada 23 Oktober mengubah ambang panel menjadi
skor >=85% merah, >=75% dan <85% kuning, <75% hijau. Persis85% merah;
persis75% kuning. Aturan lama di checkpoint awal di atas bersifat historis.
Fixture self-test disesuaikan menjadi green30%, yellow80%, red90%, offline.
Kode, tes, panduan dan handoff disinkronkan ke Pi. Delapan tes panel lulus
0,013 detik, termasuk batas74,99/75/84,99/85%. Hanya service panel direstart
dan diperiksa active/running; pola buzzer dan threshold model edge tetap.
Tidak mengulang tes bunyi fisik atau mengukur ulang akurasi model.

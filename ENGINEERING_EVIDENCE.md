# Bukti engineering SRASTA - 11 September 2026

## Hasil dan batas saat ini

Firmware, produk lokal, replay, lima state, SQLite, API/WebSocket, dashboard/PWA dan adapter telah diimplementasikan serta diuji. Setup pengguna: satu ESP32-S3 receiver COM9, hotspot HP, komputasi laptop. Receiver sudah pulih setelah cabut-pasang USB; uji kestabilan dan dashboard setelah pemulihan lulus. **Seluruh definition of done belum terpenuhi:** model jatuh belum mencapai kualitas memadai, kalibrasi kondisi lokal belum selesai, Pi/kamera/alarm fisik belum tersedia, dan penyebab gangguan USB sebelumnya belum dipastikan. Runtime live memakai aturan gerakan eksperimental tanpa keyakinan klasifikasi yang direkayasa.

## Perangkat lunak

```powershell
.venv/Scripts/python code/tools/verify_local.py
```

Hasil terbaru: **50 unit/API/replay test lulus tanpa skip**, 25,813 detik. Browser acceptance lulus pada 1440x1100 dan 390x844: semua lima state, critical acknowledgement, dialog nomor darurat eksplisit tanpa menelepon, teks 200%, offline shell, tanpa cache API/token, tanpa request eksternal/page error. Lihat `artifacts/verification/report.json`, `unit-api-replay.log`, `dashboard.log`, `ui/report.json` dan screenshot `ui/`.

Cakupan: CSI/profile/metadata, fixed mask, gap dan reboot epoch, bounded queue, replay ke SQLite, critical/ack lintas restart, event lama tidak menyenyapkan critical baru, kamera event-only/expired result, notifikasi fail-closed, kualitas napas, Hampel sustained step, parity INT8, pemisahan sesi kalibrasi, proteksi konfigurasi model, dan serial diam yang kemudian kembali mengirim. Fixture tidak membuktikan hardware atau akurasi fisiologis.

Bug riwayat/state browser diperbaiki dengan snapshot konsisten pada lock yang sama, riwayat dalam respons mutasi, dan penolakan respons revision lama dalam sesi yang sama. Browser menguji bahwa respons lama tidak dapat menimpa critical.

## Firmware dan bukti sebelum pergantian hotspot

PlatformIO 6.2.0, espressif32 6.10.0, ESP-IDF 5.4.0, ESP32-S3 DevKitC-1. Build TX/RX terbaru lulus di `artifacts/verification/firmware.log` (39,864 / 39,416 detik). Build dan flash receiver hotspot terbaru COM9 lulus 77,007 detik, 750.016 byte, hash flash diverifikasi: `artifacts/firmware-flash-hotspot-change.log`.

```powershell
$env:PLATFORMIO_CORE_DIR = Join-Path $env:LOCALAPPDATA 'srasta-pio'
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
.venv/Scripts/python code/tools/configure_hotspot.py
.venv/Scripts/python -m platformio run -d firmware -e rx_hotspot -t upload --upload-port COM9
.venv/Scripts/python code/tools/verify_serial.py --port COM9 --seconds 60 --out artifacts/hardware-serial-new-run.json
```

Hentikan pembaca serial lain sebelum flash/probe. Perbaikan nyata: bitmap protocol 11N saja ditolak driver sehingga diganti B/G/N, filter CSI tetap HT20; buffer serial stack menyebabkan overflow sehingga dipindah ke static bounded buffer; DTR/RTS disiapkan sebelum membuka port; folder toolchain/temp Windows perlu berada dalam profil pengguna. Bukti gagal awal dipertahankan.

Pada hotspot sebelum pergantian, probe 60 detik menerima 6.409 frame, **106,85 Hz** berdasarkan timestamp perangkat, SNR 31-37 dB, firmware rejection/queue drop 0 dan host quarantine/sequence gap 0. Ada **4 jendela analisis ditahan karena coverage**, bukan empat frame CSI tidak valid. Counter terbaru membedakan keduanya. Artefak `artifacts/hardware-serial-stable.json`. Inference terakhir sekitar 0,045 ms hanya perhitungan aturan gerakan pada laptop, bukan latency pipeline/model/Pi.

Dashboard serial sebelumnya lulus di `artifacts/live-ui/report.json`: frame 11.220 menjadi 11.397, realtime source serial, simulator tersembunyi, desktop/mobile tanpa overflow atau page error. Bukti ini milik koneksi sebelumnya.

## Hotspot baru, gangguan, dan pemulihan

Konfigurasi privat hotspot diganti sesuai permintaan pengguna. Scan 2,4 GHz channel 2, sinyal scan 96%. Probe 45,09 detik setelah flash menerima **5.049 frame valid**, 112,54 Hz, SNR 29-67 dB, tanpa firmware rejection/queue drop atau host quarantine/sequence gap. **Probe tetap gagal** karena tidak menghasilkan inference kontinu dengan batas gap 50 ms. Artefak `artifacts/hardware-serial-new-hotspot.json`.

Probe timing 30 detik, `artifacts/hotspot-timing.json`: 2.989 paket, median interval 9,696 ms, maksimum 88,813 ms, 10 gap lebih dari 50 ms, tidak ada lebih dari 100 ms. Aturan gerakan dapat memakai `--max-packet-gap-ms 100`, membatasi hold kausal untuk jitter hotspot. I/Q, mask dan target resampling tidak berubah. Gap lebih lama mereset jendela; override dengan model terlatih ditolak karena model harus memakai konfigurasi terserialisasi sendiri.

Setelah restart, COM9 terdeteksi tetapi tidak mengirim byte. Reset ROM dan hard reset esptool tidak mendapat respons. Layanan kini membuka ulang port setelah 5 detik tanpa byte dengan backoff sampai 8 detik, mempropagasi DTR/RTS idle, dan mempertahankan critical. Delapan percobaan awal tetap menghasilkan 0 frame; tidak diklaim sebagai recovery berhasil.

Browser saat sensor tidak tersedia juga diuji, `artifacts/live-recovery/report.json`: banner terputus tampil, simulator tersembunyi, napas ditahan, tanpa overflow/page error pada 1440x1100 dan 390x844. Status `passed_unavailable_state_ui` adalah bukti penanganan gangguan, bukan bukti capture berhasil.

Pengguna kemudian mengonfirmasi cabut-pasang USB. Receiver COM9 pulih **tanpa flashing ulang**. Observer API selama **45,17 detik** mendapatkan tambahan **4.466 frame**, laju timestamp sumber **100,00 Hz**, **179 inference**, seluruh polling fresh/ready, tanpa tambahan reject, queue drop, gap melebihi 100 ms atau reconnect. Artefak `artifacts/receiver-recovered.json`. Penyebab macet USB dan uptime panjang tetap belum terbukti.

Browser live pascapemulihan lulus, `artifacts/live-ui-recovered/report.json`: frame 18.491 menjadi 18.837, realtime source serial, lab simulator tersembunyi, viewports 1440/390, tanpa overflow/page error. Bukti sebelumnya dipertahankan di folder terpisah.

```powershell
.venv/Scripts/python code/tools/test_live_dashboard.py --out artifacts/live-ui-next
```

## Kalibrasi dan layanan aktif

Sesi bergerak sebelum perpindahan menghasilkan 111 ringkasan energi, median 0,000787. Label pengguna berlaku pada sesi, bukan tiap frame; karena posisi/jaringan berubah, hasil ini tidak dipakai untuk threshold setup baru.

Percobaan tenang setelah perpindahan menghasilkan **0 sampel** ketika receiver tidak mengirim: `artifacts/calibration/position2-quiet.json`, status `insufficient_continuity`. Tidak dipakai sebagai baseline. Receiver kini pulih. Sesi tenang ulang yang dikonfirmasi pengguna berhasil: 30,20 detik, 119 observasi, seluruh polling siap analisis, energi median 0,0009468 (rentang 0,0005128-0,0015050). Artefak `artifacts/calibration/position2-quiet-recovered.json`. Sesi aktivitas normal berikutnya dicoba setelah konfirmasi pengguna, tetapi hanya 1 observasi lolos dari 30,05 detik (ready 1,44%) akibat gap paket. Artefak `artifacts/calibration/position2-normal-activity.json` ditolak, sehingga threshold belum diubah. Label normal merupakan kondisi sesi, bukan label bergerak untuk setiap frame.

`code/tools/calibrate_motion.py` menolak data tidak cukup, setup/preprocessing berbeda, kondisi tumpang tindih, distribusi tidak terpisah, atau holdout buruk. Threshold dipilih dari paruh pertama dan diuji pada paruh kedua kronologis. Ini kalibrasi gerak provisional, bukan bukti akurasi jatuh. Ambang presence 0,02 belum dikalibrasi; ambang sudden motion 0,08 terpisah sehingga perubahan presence tidak otomatis mengubah indikasi jatuh.

```powershell
.venv/Scripts/python code/run_edge_service.py --serial-port COM9 --hotspot-config artifacts/hotspot.local.json --max-packet-gap-ms 100 --db artifacts/live.sqlite3 --port 8000
```

Dashboard: http://127.0.0.1:8000/?view=live. `health.fresh` berarti paket tersedia; `inference_ready` berarti jendela sah sudah diproses. Data lama tidak dianggap kondisi pengguna saat ini.

## Data dan model

CSI-Bench: 365 raw ESP32-S3 train/validation diunduh tanpa diubah. Train 288 dari enam subjek; validation 77 U19; locked test 80 U21 belum diunduh/dibaca; excluded 49 U22. Manifest 494 sesuai metadata saat ini; audit lama 472 belum memasukkan 22 nonfall U22 tambahan. SHA256 manifest `b7971084323ad0f5320ede4baa6de6dd4819ad277571fd475ab8f26a525f7e01`.

Replay curated 500 frame melalui RF dan TCN v2 sampai runtime/API/WebSocket lulus: `artifacts/curated-product-replay.json`. Waktu H5 nominal 100 Hz, bukan timestamp RF terukur. Hasil replay standby membuktikan integrasi saja, bukan deteksi contoh jatuh.

[MODEL_EVALUATION.md](MODEL_EVALUATION.md) memuat semua hasil. RF v2 recall fall 0,80 dan specificity 0,378; TCN INT8 recall 0,25 dan specificity 0,892. Delapan belas resep 250/500 frame dipilih dengan grouped CV train; tidak ada yang mencapai recall >=0,88 dan specificity >=0,80 bersamaan. U19 adalah validation pengembangan, bukan test final. TCN v2 parity lulus 77 window: mean abs error 0,00626, max 0,01426, argmax agreement 1,0; model 32.176 byte, mean inference 0,152 ms laptop. Parity bagus tidak membuktikan klasifikasi bagus.

ESP-Fi HAR tambahan: 490 source-train ESP32-C3 CC BY 4.0, commit/Git hash diverifikasi, 70 source-test tidak diunduh. Pretraining tujuh aktivitas kemudian fine-tune SRASTA menghasilkan recall FP32 0,925 tetapi specificity 0,081 (34 false positives dari 37 nonfall). INT8 kolaps; kalibrasi ulang seluruh primary train tetap gagal. Runtime menolak parity gagal/hilang. WiFall hanya ditelaah kartu sumber, belum digunakan. Model/data alternatif diizinkan pengguna, tetapi hasil belum memenuhi kualitas yang diminta.

## Privasi dan bukti yang masih diperlukan

Scan 82 file dalam cakupan Git: 0 file mengandung credential jaringan lokal; 0 path data/artifacts/build masuk Git. Credential dan binary yang mengandungnya hanya lokal/ignored. Tidak ada upload data, pengiriman eksternal nyata, panggilan otomatis, commit/push. Raw CSI/MAC/video tidak masuk SQLite/dashboard. Notebook/runs pengguna dipertahankan.

Belum terukur: event-level precision/recall/F1, false alerts/hour, jatuh lokal berlabel, latency dugaan/konfirmasi dari event fisik, Pi latency, uptime lama, napas manusia dibanding referensi, akurasi pose, alarm fisik, pengiriman Blynk/MQTT nyata, instalasi PWA ponsel dan WebMCP browser asli. Pengguna menyatakan Pi/kamera/buzzer belum tersedia. Semua tetap dicatat sebagai gap produk; tidak pernah meminta orang melakukan jatuh berbahaya.

## Perbaikan trafik setelah uji aktivitas normal

Aktivitas normal menunjukkan gap sumber lebih dari 100 ms sehingga jendela sering dimulai ulang. Penelusuran implementasi `ping_sock.c` pada ESP-IDF 5.4.0 membuktikan bahwa pengiriman berikutnya menunggu `esp_ping_receive`; timeout lama 100 ms dapat menahan sepuluh interval target. Firmware mengubah timeout ke satu interval (10 ms pada target 100 Hz), serta menambah counter ping_sent/replies/timeouts/reply_ms yang seluruhnya berupa angka. Hubungan kausal dengan seluruh gap aktual masih harus dibuktikan melalui flash dan pengukuran baru; kode saja bukan bukti perbaikan radio.

Build firmware terbaru dengan timeout ping satu interval lulus pada ketiga role: TX 60,121 detik, RX 57,367 detik, RX hotspot 40,988 detik; total 158,476 detik. Log `artifacts/firmware-build-paced-ping.log`.

Flash firmware paced-ping pada COM9 lulus dalam 45,351 detik, 750.768 byte, hash diverifikasi (`artifacts/firmware-flash-paced-ping.log`). Uji fisik 30,47 detik setelah itu lulus: tambahan 2.917 frame (97,45 Hz), 117 inference, seluruh polling fresh/ready, tanpa gap di atas 100 ms, frame ditolak, atau queue drop. Counter akhir firmware: 7.848 ping terkirim, 7.271 balasan, 577 timeout; nilai ini kumulatif sejak boot, bukan hanya interval uji. Artefak `artifacts/receiver-paced-ping.json` adalah pengukuran stream tanpa label kondisi orang. Hasil mendukung perbaikan kontinuitas, tetapi bukan eksperimen A/B dengan gerakan identik atau bukti akurasi aktivitas.

Pengambilan aktivitas normal ulang menunggu konfirmasi kondisi terbaru pengguna. Sampel tunggal dari sesi gagal tetap tidak dipakai sebagai baseline atau pembanding.

Setelah pengguna mengonfirmasi aktivitas normal masih berlangsung, capture ulang 30,11 detik lulus kontinuitas: 116 observasi, ready 100%, energi median 0,0011708 (rentang 0,0005605-0,0037928), `artifacts/calibration/position2-normal-paced.json`. Namun perbandingan dengan sesi tenang menghasilkan `not_separated`: p95 tenang pada paruh fit 0,0014473, p25 sesi normal 0,0009790. Threshold tetap null dan ambang runtime belum diubah. Lihat `artifacts/calibration/position2-comparison-normal.json`. Aktivitas normal dapat mengandung jeda diam; hasil ini tidak membuktikan bahwa semua jenis gerakan tidak terdeteksi. Sesi berjalan pelan yang lebih terkontrol diperlukan untuk pembanding gerakan sebelum memilih ambang.

Perubahan timeout memperbaiki kontinuitas pada interval pengujian dan capture normal tersebut, tetapi bukan jaminan tidak akan ada gap lagi: penghitung kumulatif setelahnya masih menunjukkan beberapa gap hingga sekitar 220 ms. Jendela yang melintasi batas tetap ditahan; tidak meningkatkan toleransi hanya agar pengujian terlihat lulus.

## Status kalibrasi setelah respons pengguna

Pengguna menyatakan belum bisa melakukan uji berjalan terkontrol. Pengambilan berlabel tambahan ditunda; tidak mengasumsikan kondisi tenang/bergerak baru dari data sensor. Sesi tenang (119 observasi), aktivitas normal (116 observasi), dan sesi gagal tetap tersimpan lokal. Perbandingan tetap `not_separated`, threshold kalibrasi null. Runtime mempertahankan ambang eksperimen awal 0,02 dengan sudden motion 0,08 dan toleransi gap 100 ms; status sensor tidak dipaksa menjadi normal berdasarkan label percakapan. Model jatuh tetap belum tervalidasi. Kalibrasi dapat dilanjutkan ketika pembanding gerakan aman tersedia pada setup yang diketahui.

## Checkpoint handoff dan pemeriksaan sebelum push

Pengguna meminta pembaruan AGENT.md, prompt kelanjutan dan push GitHub. Handoff memuat keputusan pengguna, topologi satu RX/hotspot, hasil/gap, artefak lokal, langkah reproduksi, serta enam tahap penerimaan produk final. Verifikasi terakhir untuk checkpoint ini: 50 unit/API/replay test lulus tanpa skip (25,813 detik), browser desktop/mobile lulus. Pemindaian 52 berkas perubahan tidak menemukan nilai kredensial jaringan lokal, pola token/kunci privat, berkas di data/artifacts/build, atau berkas lebih dari 1 MB. Artefak privat tetap diabaikan Git.

Pemeriksaan layanan pada awal handoff menunjukkan serial fresh dan inference ready, state standby, 207.026 frame diterima. Counter kumulatifnya mencatat 2 frame ditolak, 402 gap, gap terpanjang sekitar 427,59 detik dan 2 reconnect. Angka ini termasuk riwayat gangguan, tidak menyatakan uptime panjang lulus. Penyebab gap dan pemulihan USB tetap pekerjaan aktif.

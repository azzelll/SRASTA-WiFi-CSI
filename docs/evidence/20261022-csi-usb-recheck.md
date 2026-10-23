# Pemeriksaan ulang CSI dan USB — 22 Oktober 2026

Pemilik meminta pemeriksaan ulang setelah memasang perangkat. Pemeriksaan
langsung melalui SSH pada Pi, tanpa restart service, membuka port serial,
flash firmware, capture kamera, atau mengirim event/command produksi.

- srasta-edge.service active/running, NRestarts=0.
- Dua snapshot berjarak 8 detik: accepted_frames 0 -> 0; quarantine 0 -> 0.
- Source unavailable, monitoring_online=false, state_verified=false.
- Serial disconnected, active_port=null, lines=0, rate=0 Hz; inferensi unavailable.
- /dev/serial/by-id, /dev/ttyUSB*, /dev/ttyACM* dan /dev/serial/by-path
  tidak menunjukkan port RX.
- Sysfs USB hanya memuat hub USB2.0 2109:3431 dan dua xHCI root controller.
  Tidak ada board RX/USB-UART yang terenumerasi pada saat pemeriksaan.

Kesimpulan: CSI belum online; board RX belum terdeteksi melalui USB Pi.
Ini tidak membuktikan komponen rusak atau memastikan penyebab kabel/port.
Periksa RX UART/COM ke USB Pi dengan kabel data, daya TX, dan tujuan kabel.
OLED/LED/buzzer pada GPIO tidak menyediakan sumber CSI. Setelah sambungan
fisik diperbaiki, ulangi pemeriksaan port dan kenaikan frame sebelum pilot QA.

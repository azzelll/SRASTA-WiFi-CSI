#!/usr/bin/env python3
"""One-command guided, continuous, local CSI recording; no staged falls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import glob
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import threading
import time
import uuid
import warnings

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
warnings.filterwarnings("ignore", message=r"\s*Warning: tf.lite.Interpreter is deprecated", category=UserWarning)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srasta_csi.capture_archive import CaptureArchive, digest, private_write, protected_root, qa_capture
from srasta_csi.capture_service import PausedEdgeService, local_status
from srasta_csi.contract import CaptureProfile, FrameValidator
from srasta_csi.edge import EdgeRuntime, EventStore
from srasta_csi.serial_reader import SerialJSONLReader

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO.parent / "SRASTA_LOCAL_CAPTURE"
DEFAULT_MODEL = REPO / "artifacts/releases/20261001-tcn-v8-motion-calibrated/selected/model.tflite"


def ask_code(title, default, prefix):
    while True:
        value = input(f"{title} [{default}]: ").strip().upper() or default
        if re.fullmatch(re.escape(prefix) + r"[A-Z0-9_]{1,32}", value):
            return value
        print(f"Gunakan kode seperti {default}, tanpa nama asli.")


def confirmed(question):
    while True:
        answer = input(question + " [y/n]: ").strip().lower()
        if answer in {"y", "ya", "yes"}:
            return True
        if answer in {"n", "tidak", "no"}:
            return False
        print("Ketik y atau n, lalu Enter.")


def select_port(requested):
    ports = sorted(set(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")))
    status = local_status()
    active = status.get("transport", {}).get("port")
    if requested:
        if not Path(requested).exists():
            raise ValueError(f"Port RX tidak ditemukan: {requested}. Sambungkan kedua board sesuai label.")
        return requested
    if active in ports and status.get("demo_mode") is not True:
        print(f"RX yang sedang dipakai layanan SRASTA: {active}")
        return active
    if not ports:
        raise ValueError("Belum ada port USB. Sambungkan TX dan RX, lalu jalankan script lagi.")
    print("\nPilih port board yang diberi label RX:")
    for index, port in enumerate(ports, 1):
        print(f"  {index}. {port}")
    while True:
        value = input("Nomor port RX: ").strip()
        if value.isdigit() and 1 <= int(value) <= len(ports):
            return ports[int(value)-1]
        print("Pilih nomor dari daftar. Posisi USB kiri/kanan tidak menentukan TX/RX.")


def metadata(args):
    if args.pilot_only:
        return {"subject_id": "LOC_PILOT", "site_id": "SITE_PILOT", "room_id": "ROOM_PILOT", "split": "pilot", "observer_id": "ANN_PILOT", "antenna_arrangement": "unverified_pilot", "authority_ref": "", "independent_local_cohort_attested": False, "firmware_attested": False}
    print("\nIDENTITAS SESI — pakai kode, jangan tulis nama atau informasi pribadi.")
    subject = ask_code("Kode orang (gunakan kode yang sama pada rekaman berikutnya)", "LOC_001", "LOC_")
    print("Split satu orang harus tetap. 1=train, 2=validation, 3=test. Jangan ganti setelah melihat hasil model.")
    split = {"1": "train", "2": "validation", "3": "test"}
    while (choice := input("Split [1]: ").strip() or "1") not in split:
        print("Pilih 1, 2, atau 3.")
    site = ask_code("Kode lokasi", "SITE_001", "SITE_")
    room = ask_code("Kode ruangan", "ROOM_001", "ROOM_")
    observer = ask_code("Kode pengamat/operator", "ANN_001", "ANN_")
    geometry = input("Posisi TX/RX, jarak dan tinggi (contoh: sisi berlawanan, 3m, tinggi 1m): ").strip()[:160] or "not_recorded"
    firmware_attested = confirmed("TX/RX masih memakai firmware SRASTA terakhir, tanpa flash ulang?")
    independent = confirmed("Orang dan rekaman ini baru, bukan peserta/rekaman dari dataset publik yang pernah dipakai?")
    authority = input("Kode izin/protokol penelitian jika sudah ada [Enter jika belum; label akan pending]: ").strip()[:80]
    if authority and not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", authority):
        raise ValueError("Kode izin hanya boleh huruf, angka, garis bawah atau tanda minus.")
    return {"subject_id": subject, "site_id": site, "room_id": room, "split": split[choice], "observer_id": observer, "antenna_arrangement": geometry, "authority_ref": authority, "independent_local_cohort_attested": independent, "firmware_attested": firmware_attested}


class GuidedRecorder:
    def __init__(self, args, meta, root, port):
        self.args, self.meta, self.root, self.port = args, meta, root, port
        self.archive = None
        self.runtime = None
        self.stage_lock = threading.Lock()
        self.probe = FrameValidator(CaptureProfile(channel=args.channel, subcarrier_order=args.subcarrier_order))
        self.probe_frame = None
        self.stop = threading.Event()
        self.worker = None
        self.interval = None
        self.reader = SerialJSONLReader(port, args.baud, self.ingest, on_reconnect=self.reconnected)

    def reconnected(self):
        if self.archive:
            self.archive.failure = "serial_reconnected_start_new_session"

    def ingest(self, line):
        with self.stage_lock:
            if self.archive is None:
                try:
                    self.probe_frame = self.probe.parse_json_line(line)
                    return None
                except ValueError:
                    return {"status": "quarantined"}
            try:
                result = self.archive.record(line)
                if not isinstance(result, dict):
                    # Archive validation and runtime validation keep independent counters.
                    self.runtime.ingest_json_line(line)
                return result
            except Exception as exc:
                self.archive.failure = f"recorder_error_{type(exc).__name__}"
                return {"status": "dropped"}

    def start(self):
        print("\nMenyiapkan model pencatat prediksi sebelum membuka serial...")
        # Loading TensorFlow while holding the serial callback lock overflowed
        # the USB buffer in the first pilot. Warm the model before reception.
        with tempfile.TemporaryDirectory(prefix=".model_warmup_", dir=self.root) as directory:
            self.runtime = EdgeRuntime(self.args.model, Path(directory) / "empty.sqlite3", validator=FrameValidator(CaptureProfile(channel=self.args.channel, subcarrier_order=self.args.subcarrier_order)), max_gap_s=.15, allow_capture_profile_override=True, auto_process_frames=False, queue_size=256)
            self.runtime.store.close()
        self.reader.start()
        print("\nMemeriksa CSI asli dari RX (LLTF/HT20/128 I/Q)...")
        deadline = time.monotonic() + 12
        while self.probe_frame is None and time.monotonic() < deadline:
            time.sleep(.1)
        if self.probe_frame is None:
            raise RuntimeError("Tidak ada frame CSI valid. Pastikan TX/RX hidup, port RX benar, dan channel sama.")
        session_id = "SES_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8].upper()
        binaries = {role: REPO / f"firmware/esp32_s3_csi_{suffix}/build/srasta_csi_{suffix}.bin" for role, suffix in {"tx": "tx", "rx": "serial"}.items()}
        firmware_hashes = {role: digest(path) for role, path in binaries.items() if path.is_file()}
        config = {
            **self.meta, "session_id": session_id, "channel": self.args.channel, "subcarrier_order": self.args.subcarrier_order, "maximum_packet_gap_s": .15, "inactivity_min_s": 60.0,
            "sender_mac": self.probe_frame.sender_mac, "sender_id": "TX_001", "sender_model": "ESP32-S3", "esp_idf_version": "5.5.3",
            "firmware_revision": firmware_hashes.get("rx", "unverified"), "local_firmware_sha256": firmware_hashes,
            "firmware_verification": "operator_attested_last_flash_local_build" if self.meta["firmware_attested"] else "not_verified_against_board",
            "nominal_sender_rate_hz": 50.0, "serial_port": self.port, "serial_baud": self.args.baud,
            "model_sha256": digest(self.args.model), "model_release": self.args.model.parent.parent.name,
            "preprocess_config_sha256": digest(self.args.model.parent / "preprocess_config.json"),
            "prediction_interval_s": .2, "planned_conditions": [] if self.args.pilot_only else ["no_person", "normal", "inactive"],
            "condition_duration_s": self.args.duration, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        with self.stage_lock:
            self.archive = CaptureArchive(self.root, config)
            self.runtime.store = EventStore(self.archive.path / "runtime.sqlite3")
            os.chmod(self.archive.path / "runtime.sqlite3", 0o600)
        self.worker = threading.Thread(target=self.infer, name="capture-inference", daemon=True)
        self.worker.start()
        deadline = time.monotonic() + 5
        while self.archive.last_frame is None and time.monotonic() < deadline:
            time.sleep(.1)
        self.archive.clock()
        print(f"Rekaman kontinu aktif. Folder: {self.archive.path}")
        print("CSI, label pengamat, prediksi, dan pemeriksaan kualitas disimpan terpisah. Ctrl+C menyimpan hasil parsial.")

    def infer(self):
        previous = None
        while not self.stop.wait(.2):
            try:
                self.runtime.process_queue()
                stamp = self.runtime.last_inference_sample_s
                if stamp is not None and stamp != previous:
                    self.archive.prediction(round(stamp*1e6), self.runtime.machine.state, self.runtime.last_probability, self.runtime.last_motion_energy)
                    previous = stamp
            except Exception as exc:
                self.archive.failure = f"inference_error_{type(exc).__name__}"
                return

    def timed(self, seconds, title):
        end = time.monotonic() + seconds
        previous = None
        while time.monotonic() < end:
            stats = self.archive.stats()
            if stats["failed"] or not self.reader.status()["running"]:
                raise RuntimeError(f"Sesi dihentikan: {stats['failed'] or 'serial reader berhenti'}")
            self.archive.clock()
            remaining = max(0, int(end-time.monotonic()+.999))
            if remaining != previous:
                print(f"\r{title}: {remaining:3d} detik | paket valid {stats['accepted_frames']} | karantina {stats['quarantined_frames']}   ", end="", flush=True)
                previous = remaining
            time.sleep(min(.1, max(0, end-time.monotonic())))
        print("\n\a", end="", flush=True)

    def condition(self, name, instructions, event_type, stationary=False):
        print(f"\n{name}\n{instructions}")
        input("Tekan Enter saat siap. ")
        stationary_since = None
        if stationary:
            stationary_since = self.archive.clock()
            self.timed(61, "Tetap diam; persiapan label inactive (minimum 60 detik)")
        else:
            self.timed(self.args.prepare, "Persiapan; kondisi belum diberi label")
        start = self.archive.clock()
        self.interval = (start, event_type)
        self.timed(self.args.duration, "REKAM — pertahankan kondisi")
        end = self.archive.clock()
        print("Waktu kondisi selesai. Anda boleh kembali ke laptop.")
        valid = confirmed("Apakah kondisi tadi sesuai sepanjang waktu REKAM, tanpa orang tambahan/gangguan?")
        extra = {"stationary_since_monotonic_us": stationary_since} if stationary else {}
        event = self.archive.annotate(event_type, start, end, observer_id=self.meta["observer_id"], confirmed=valid, **extra)
        self.interval = None
        print(f"Tersimpan: {event['activity_label']} ({(end-start)/1e6:.1f} detik), review pending.")

    def run(self):
        self.start()
        if self.args.pilot_only:
            self.timed(self.args.pilot_seconds, "PILOT koneksi — tanpa label aktivitas")
            return
        self.condition("1/3 — RUANGAN KOSONG", "Setelah Enter, Anda punya waktu persiapan untuk keluar. Semua orang harus keluar dari ruangan yang dipantau. Biarkan TX/RX tetap di tempat. Tunggu bunyi akhir sebelum kembali.", "no_person")
        self.condition("2/3 — AKTIVITAS NORMAL", "Satu orang di ruangan. Berjalan dengan kecepatan biasa, berbalik, duduk lalu berdiri, mengambil barang ringan bila nyaman. Lakukan seperti aktivitas sehari-hari.", "nonfall_activity")
        self.condition("3/3 — DIAM / INAKTIF", "Duduk atau berbaring dengan nyaman. Setelah Enter, tetap pada posisi itu selama persiapan dan REKAM. Bernapas seperti biasa. Gerakan kecil alami boleh; jangan berjalan atau berganti posisi besar.", "inactivity_without_fall", stationary=True)
        print("\nTiga kondisi selesai. Kelas jatuh belum dikumpulkan; perlu sesi terpisah sesuai protokol dan pengamat.")

    def finish(self, completed):
        self.reader.close()
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=10)
            if self.worker.is_alive() and self.archive:
                self.archive.failure = "inference_worker_did_not_stop"
        if not self.archive:
            if self.runtime:
                self.runtime.close()
            return
        if self.interval and self.archive.last_frame:
            start, kind = self.interval
            end = self.archive.last_frame.local_timestamp_us
            if end > start:
                self.archive.annotate(kind, start, end, observer_id=self.meta["observer_id"], confirmed=False, notes="Interrupted before observer confirmation")
        self.archive.close(completed=completed, transport=self.reader.status())
        if self.runtime:
            self.runtime.close()
        report = qa_capture(self.archive.path)
        private_write(self.archive.path / "qa_report.json", report)
        print(f"\nTERSIMPAN OTOMATIS: {self.archive.path}")
        print(f"Paket valid: {report['frame_count']} | loss: {report['packet_loss_rate']:.2%} | durasi CSI: {report['observed_duration_s']:.1f}s")
        print(f"QA: {report['status']} | prediksi: {report['prediction_count']}")
        for reason in report["issues"] + report["pending_reasons"]:
            print(f"  - {reason}")
        print("Tidak diunggah ke cloud/Git. Label tidak berasal dari tebakan model.")
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rekam CSI asli dengan instruksi kondisi di CLI dan penyimpanan otomatis.")
    parser.add_argument("--port", help="Port RX; otomatis memakai RX layanan SRASTA bila tersedia")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Folder lokal di luar Git/data")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--channel", type=int, default=6)
    parser.add_argument("--subcarrier-order", choices=("centered", "esp_idf_native"), default="esp_idf_native", help="Urutan frekuensi firmware RX; disimpan dalam capture profile")
    parser.add_argument("--baud", type=int, default=1000000)
    parser.add_argument("--duration", type=int, default=180, help="Detik per kondisi (minimum 60, default 180)")
    parser.add_argument("--prepare", type=int, default=20, help="Waktu keluar ruangan/bersiap (minimum 10)")
    parser.add_argument("--pilot-only", action="store_true", help="Uji koneksi saja; tanpa instruksi kondisi atau label training")
    parser.add_argument("--pilot-seconds", type=int, default=10)
    args = parser.parse_args(argv)
    if args.duration < 60 or args.prepare < 10 or args.pilot_seconds < 1 or not 1 <= args.channel <= 14 or args.baud <= 0:
        parser.error("duration >=60, prepare >=10, pilot-seconds >=1, channel 1..14, baud >0")
    args.model = args.model.expanduser().resolve()
    if not args.model.is_file() or args.model.suffix != ".tflite":
        parser.error("Model TFLite lokal belum tersedia. Tentukan --model; raw capture tidak boleh memakai model palsu.")
    os.umask(0o077)
    print("SRASTA — PENGAMBILAN CSI LOKAL")
    print("Sambungkan TX dan RX sesuai label; RX harus mengirim JSONL CSI. Jaga posisi kedua board selama sesi.")
    if args.pilot_only:
        print(f"Pilot koneksi {args.pilot_seconds} detik, tanpa label aktivitas.")
    else:
        print(f"Durasi kondisi: {args.duration}s × 3 + persiapan; sekitar {(args.duration*3+args.prepare*2+61)/60:.0f} menit, di luar waktu menjawab.")
    recorder = None
    completed = False
    report = None
    def terminate(*_):
        raise KeyboardInterrupt
    old_term = signal.signal(signal.SIGTERM, terminate)
    try:
        root = protected_root(args.root)
        port = select_port(args.port)
        meta = metadata(args)
        # Advisory lock prevents two recorder processes with the same storage root.
        import fcntl
        with os.fdopen(os.open(root / ".capture.lock", os.O_RDWR | os.O_CREAT, 0o600), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with PausedEdgeService(REPO, port, root):
                recorder = GuidedRecorder(args, meta, root, port)
                try:
                    recorder.run()
                    completed = True
                finally:
                    report = recorder.finish(completed)
    except (KeyboardInterrupt, EOFError):
        print("\nRekaman dihentikan. Data yang sudah diterima tetap tersimpan; kondisi terputus tidak dipakai sebagai label valid.")
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"\nGagal: {exc}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, old_term)
    return 2 if report and report["status"] == "rejected" else 0


if __name__ == "__main__":
    raise SystemExit(main())

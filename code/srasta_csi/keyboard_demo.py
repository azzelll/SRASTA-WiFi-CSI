"""Manual Pi demo: start idle, press Space for fall, R to reset, Q to quit.

Uses the local OLED/LED/piezo wiring, with optional cloud status for the phone.
Run through scripts/run_keyboard_demo.sh to pause and restore the live panel.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import select
import signal
import sys
import termios
import time
import tty

from srasta_csi.device_panel import Indicator, open_hardware, write_status


IDLE = Indicator("green", "IDLE")
FALL = Indicator("red", "JATUH TERDETEKSI")


def draw_demo(hardware, indicator: Indicator):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("1", (128, 64))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((0, 0), "SRASTA | DEMO", font=font, fill=1)
    draw.line((0, 13, 127, 13), fill=1)
    draw.text((0, 22), indicator.label, font=font, fill=1)
    draw.text((0, 40), "SPACE: jatuh  R: idle", font=font, fill=1)
    draw.text((0, 54), "SIMULASI MANUAL", font=font, fill=1)
    hardware.device.display(image)


def run_demo(*, buzzer: str, status_file: Path, terminal_only: bool, cloud=None):
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    previous_handlers = {}
    stopping = False
    hardware = None
    indicator = IDLE
    changed_at = time.monotonic()
    next_write = 0.0
    last = None
    cloud_state = None

    def stop(*_):
        nonlocal stopping
        stopping = True

    try:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous_handlers[sig] = signal.signal(sig, stop)
        if not terminal_only:
            hardware = open_hardware(buzzer)
        if cloud:
            cloud.set_fallen(False)
            cloud.start()
        tty.setcbreak(fd)
        # Do not carry keys typed before startup into this demo session.
        termios.tcflush(fd, termios.TCIFLUSH)
        print("SRASTA | SIMULASI MANUAL\n"
              "[SPACE] Jatuh  [R] Kembali idle  [Q / Ctrl+C] Keluar", flush=True)
        while not stopping:
            now = time.monotonic()
            if indicator != last:
                changed_at = now
                print(indicator.label, flush=True)
                if hardware:
                    draw_demo(hardware, indicator)
                if cloud:
                    cloud.set_fallen(indicator == FALL)
            if hardware:
                hardware.update(indicator, now - changed_at)
            if indicator != last or now >= next_write:
                write_status(status_file, indicator, buzzer if hardware else "off", None, True)
                if cloud:
                    connected = cloud.status()["connected"]
                    if connected != cloud_state:
                        print("Website: tersambung ke cloud." if connected else
                              "Website: menunggu cloud; kontrol lokal tetap aktif.", flush=True)
                        cloud_state = connected
                next_write = now + .5
            last = indicator
            readable, _, _ = select.select([fd], [], [], .01)
            if readable:
                keys = os.read(fd, 1)
                if not keys:  # SSH/terminal closed.
                    break
                for key in keys.lower():
                    if key in (ord("q"), 3, 4):
                        stopping = True
                        break
                    if key == ord(" "):
                        indicator = FALL
                    elif key == ord("r"):
                        indicator = IDLE
    finally:
        # Always silence/release outputs, even if drawing or status writes fail.
        try:
            if hardware:
                hardware.close()
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, original)
            finally:
                for sig, handler in previous_handlers.items():
                    signal.signal(sig, handler)
                if cloud:
                    cloud.close()
                write_status(status_file, Indicator("stopped", "DEMO BERHENTI"), "off", None, True)
                print("Demo berhenti.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buzzer", choices=("off", "passive", "active"), default="passive")
    parser.add_argument("--status-file", type=Path,
                        default=Path.home() / "srasta-edge/state/keyboard-demo.json")
    parser.add_argument("--terminal-only", action="store_true", help="Try controls without GPIO/OLED")
    parser.add_argument("--cloud-env", type=Path, help="Private Pi edge.env; publish manual status to the phone dashboard")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Jalankan dari terminal interaktif; untuk SSH gunakan ssh -t.")
    try:
        from srasta_csi.keyboard_demo_cloud import cloud_from_env
        cloud = cloud_from_env(args.cloud_env) if args.cloud_env else None
        run_demo(buzzer=args.buzzer, status_file=args.status_file, terminal_only=args.terminal_only, cloud=cloud)
    except (OSError, RuntimeError, ImportError, ValueError) as exc:
        print(f"Demo gagal: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

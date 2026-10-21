"""POSIX serial JSONL reader for ESP32-S3 CSI frames."""

from __future__ import annotations

import os
import sys
import fcntl
import array
import select
import termios
import threading
import tty
import time
from collections.abc import Callable


def configure_serial(fd: int, baud: int) -> None:
    """Configure a POSIX serial fd; macOS needs IOSSIOSPEED above 230400."""
    if baud <= 0:
        raise ValueError("serial baud must be positive")
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}", None)
    if speed is None and sys.platform != "darwin":
        raise ValueError(f"unsupported serial baud: {baud}")
    attrs[4] = attrs[5] = speed if speed is not None else termios.B115200
    # A previous macOS IOSSIOSPEED session leaves the custom numeric speed in
    # tcgetattr. Normalize it before setraw calls tcsetattr with those values.
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    tty.setraw(fd, termios.TCSANOW)
    if speed is None:
        fcntl.ioctl(fd, 0x80045402, array.array("i", [baud]), True)


class SerialJSONLReader:
    def __init__(self, port: str, baud: int, ingest: Callable[[str], object], *, on_reconnect: Callable[[], object] | None = None, stall_timeout_s: float = 5.0):
        self.port = port
        self.baud = baud
        self.ingest = ingest
        if stall_timeout_s <= 0:
            raise ValueError("stall timeout must be positive")
        self.on_reconnect = on_reconnect
        self.stall_timeout_s = stall_timeout_s
        self.stalls = 0
        self.last_byte_monotonic: float | None = None
        self.last_frame_monotonic: float | None = None
        self._buffer = bytearray()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.lines = 0
        self.ignored_lines = 0
        self.read_errors = 0
        self.reconnects = 0
        self.connected = False
        self.active_port: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("serial reader already started")
        self._thread = threading.Thread(target=self._run, name="esp32-csi-serial", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)
        if len(self._buffer) > 16384 and b"\n" not in self._buffer:
            self._buffer.clear()
            self.read_errors += 1
            return
        while b"\n" in self._buffer:
            raw, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            line = raw.strip()
            if not line.startswith(b"{"):
                self.ignored_lines += 1
                continue
            try:
                result = self.ingest(line.decode("ascii"))
                self.lines += 1
                if not isinstance(result, dict) or result.get("status") not in {"quarantined", "dropped"}:
                    self.last_frame_monotonic = time.monotonic()
            except (UnicodeDecodeError, ValueError):
                self.read_errors += 1

    def status(self) -> dict[str, object]:
        return {
            "type": "usb_serial_jsonl",
            "port": self.port,
            "baud": self.baud,
            "lines": self.lines,
            "ignored_lines": self.ignored_lines,
            "read_errors": self.read_errors,
            "running": self._thread is not None and self._thread.is_alive(),
            "connected": self.connected,
            "active_port": self.active_port,
            "reconnects": self.reconnects,
            "stalls": self.stalls,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            fd = -1
            try:
                if not os.path.exists(self.port):
                    raise OSError("configured ESP32 serial port is unavailable")
                self.active_port = self.port
                fd = os.open(self.active_port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
                configure_serial(fd, self.baud)
                self._buffer.clear()
                # The first connection does not reset an existing runtime. On
                # recovery, a reboot may reset receiver sequence and uptime.
                if self.reconnects and self.on_reconnect:
                    self.on_reconnect()
                self.last_byte_monotonic = time.monotonic()
                self.last_frame_monotonic = self.last_byte_monotonic
                self.connected = True
                while not self._stop.is_set():
                    readable, _, _ = select.select([fd], [], [], 0.25)
                    if readable:
                        try:
                            data = os.read(fd, 65536)
                        except BlockingIOError:
                            continue
                        if not data:
                            raise OSError("ESP32 serial port disconnected")
                        self.last_byte_monotonic = time.monotonic()
                        self.feed(data)
                    if time.monotonic() - self.last_frame_monotonic >= self.stall_timeout_s:
                        self.stalls += 1
                        raise OSError("ESP32 serial stream stalled; reopen exact configured port")
            except (OSError, ValueError, termios.error):
                self.read_errors += 1
            finally:
                self.connected = False
                self.active_port = None
                if fd >= 0:
                    os.close(fd)
            if not self._stop.wait(1):
                self.reconnects += 1

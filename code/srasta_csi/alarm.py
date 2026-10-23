"""Local audible alarm, independent of the cloud; GPIO is opt-in for Raspberry Pi."""
from __future__ import annotations

import shutil
import subprocess
import threading


class LocalAlarm:
    def __init__(self, provider, *, mode: str = "audio", gpio_pin: int = 18):
        if mode not in {"audio", "gpio", "disabled"}:
            raise ValueError("unknown alarm mode")
        self.provider = provider
        self.mode = mode
        self.requested = self.active = False
        self.last_error = None
        self.output = None
        self.player = shutil.which("afplay") or shutil.which("aplay") if mode == "audio" else None
        if mode == "gpio":
            from gpiozero import Buzzer
            self.output = Buzzer(gpio_pin)
        self.available = self.output is not None or self.player is not None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="local-alarm")

    def start(self):
        self.thread.start()

    def status(self):
        return {"requested": self.requested, "available": self.available, "active": self.active, "mode": self.mode, "last_error": self.last_error}

    def _run(self):
        from pathlib import Path
        sound = Path(__file__).parent / "alarm.wav"
        while not self.stop.wait(1):
            self.requested = bool(self.provider().get("local_alarm_on"))
            self.active = False
            try:
                if self.output:
                    self.output.on() if self.requested else self.output.off()
                    self.active = self.requested
                elif self.requested and self.player:
                    self.active = True
                    subprocess.run([self.player, str(sound)], timeout=3, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                self.active = False
                self.last_error = "Sortir alarm lokal gagal"

    def close(self):
        self.stop.set()
        self.thread.join(timeout=4)
        if self.output:
            self.output.off()
            self.output.close()

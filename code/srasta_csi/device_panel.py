"""Read-only local CSI score panel: SSD1306 SPI, three LEDs, optional piezo.

This adapter never opens RX, changes inference thresholds, or creates events.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
import urllib.request

LED_PINS = {"red": 27, "yellow": 22, "green": 17}  # physical 13, 15, 11
BUZZER_PIN = 16  # physical 36
URL = "http://127.0.0.1:8000/api/caregiver"
MAX_AGE = 3.0


@dataclass(frozen=True)
class Indicator:
    level: str
    label: str
    score: float | None = None


def select_indicator(snapshot, *, now: float) -> Indicator:
    """Unavailable, replay, stale and malformed data must never look green."""
    offline = Indicator("offline", "CSI OFFLINE")
    if not isinstance(snapshot, dict):
        return offline
    if (snapshot.get("source") != "live"
            or snapshot.get("simulation") is not False
            or snapshot.get("monitoring_online") is not True
            or snapshot.get("serial_connected") is not True):
        return offline
    for key in ("updated_at_s", "observed_at_s"):
        value = snapshot.get(key)
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not -1 <= now - value <= MAX_AGE):
            return offline
    age = snapshot.get("stream_age_s")
    if (type(age) not in (int, float) or not math.isfinite(age)
            or not 0 <= age <= MAX_AGE):
        return offline
    score = snapshot.get("fall_confidence")
    if (snapshot.get("state_verified") is not True
            or type(score) not in (int, float)
            or not math.isfinite(score) or not 0 <= score <= 1):
        return Indicator("waiting", "MENUNGGU SKOR")
    if score >= .85:
        return Indicator("red", "INDIKASI JATUH", score)
    if score >= .75:
        return Indicator("yellow", "WASPADA", score)
    return Indicator("green", "SKOR RENDAH", score)


def buzzer_gate(level: str, elapsed: float) -> bool:
    if level == "red":
        return elapsed % .24 < .12  # 120 ms on / 120 ms off
    if level == "yellow":
        return elapsed % 1.0 < .20  # 200 ms on / 800 ms off
    return False


class Hardware:
    def __init__(self, gpio, device, *, buzzer_mode="off"):
        self.gpio, self.device, self.buzzer_mode = gpio, device, buzzer_mode
        self.pwm = None
        self.claimed = []
        self.level = None
        self.buzzing = False
        gpio.setmode(gpio.BCM)
        try:
            for pin in LED_PINS.values():
                gpio.setup(pin, gpio.OUT, initial=gpio.LOW)
                self.claimed.append(pin)
            if buzzer_mode != "off":
                gpio.setup(BUZZER_PIN, gpio.OUT, initial=gpio.LOW)
                self.claimed.append(BUZZER_PIN)
                if buzzer_mode == "passive":
                    self.pwm = gpio.PWM(BUZZER_PIN, 2000)
                    self.pwm.start(0)
        except BaseException:
            self.close()
            raise

    def update(self, indicator: Indicator, elapsed: float):
        if indicator.level != self.level:
            # Break before make: never deliberately leave two LEDs high.
            self.gpio.output(list(LED_PINS.values()), self.gpio.LOW)
            if indicator.level in LED_PINS:
                self.gpio.output(LED_PINS[indicator.level], self.gpio.HIGH)
            self.level = indicator.level
        enabled = self.buzzer_mode != "off" and buzzer_gate(indicator.level, elapsed)
        if enabled != self.buzzing:
            if self.pwm is not None:
                self.pwm.ChangeDutyCycle(50 if enabled else 0)
            else:
                self.gpio.output(BUZZER_PIN, enabled)
            self.buzzing = enabled

    def draw(self, indicator: Indicator, *, simulated=False):
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("1", (128, 64))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.text((0, 0), "SIMULASI TES" if simulated else "SRASTA CSI LOKAL", font=font, fill=1)
        draw.line((0, 13, 127, 13), fill=1)
        draw.text((0, 18), indicator.label, font=font, fill=1)
        score = "Skor: --" if indicator.score is None else f"Skor: {indicator.score * 100:.1f}%"
        draw.text((0, 32), score, font=font, fill=1)
        if indicator.score is not None:
            draw.rectangle((0, 47, 127, 53), outline=1)
            width = round(indicator.score * 124)
            if width:
                draw.rectangle((2, 49, 1 + width, 51), fill=1)
        draw.text((0, 55), "Indikasi model", font=font, fill=1)
        self.device.display(image)

    def close(self):
        # Try each shutdown step even if one device has failed.
        errors = []
        actions = []
        if self.pwm is not None:
            actions.append(self.pwm.stop)
        if self.claimed:
            actions += [lambda: self.gpio.output(self.claimed, self.gpio.LOW),
                        lambda: self.gpio.cleanup(self.claimed)]
        actions += [self.device.clear, self.device.hide, self.device.cleanup]
        for action in actions:
            try:
                action()
            except Exception as exc:
                errors.append(type(exc).__name__)
        if errors:
            print("cleanup_errors=" + ",".join(errors), flush=True)


def open_hardware(mode):
    import RPi.GPIO as GPIO
    from luma.core.interface.serial import spi
    from luma.oled.device import ssd1306
    serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, bus_speed_hz=4000000)
    try:
        device = ssd1306(serial, width=128, height=64, rotate=0)
    except BaseException:
        serial.cleanup()
        raise
    return Hardware(GPIO, device, buzzer_mode=mode)


class SnapshotReader:
    def __init__(self):
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.snapshot = None
        self.error = None
        self.received = None
        self.thread = threading.Thread(target=self._run, name="panel-http", daemon=True)

    def _run(self):
        while not self.stop.is_set():
            snapshot, error = None, None
            try:
                with urllib.request.urlopen(URL, timeout=.75) as response:
                    snapshot = json.load(response)
            except Exception as exc:
                error = type(exc).__name__
            with self.lock:
                self.snapshot, self.error, self.received = snapshot, error, time.monotonic()
            self.stop.wait(.5)

    def read(self):
        with self.lock:
            if self.received is None or time.monotonic() - self.received > MAX_AGE:
                return None, "SnapshotExpired"
            return self.snapshot, self.error

    def close(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=1.5)


def write_status(path, indicator, mode, error, simulated):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    data = {"updated_at_s": time.time(), "level": indicator.level,
            "score": indicator.score, "label": indicator.label,
            "buzzer_mode": mode, "error": error, "simulation": simulated}
    with open(temp, "w", encoding="utf-8") as stream:
        os.chmod(temp, 0o600)
        json.dump(data, stream, allow_nan=False)
        stream.write("\n")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buzzer", choices=("off", "passive", "active"), default="off")
    parser.add_argument("--self-test", action="store_true", help="Isolated 10-second GPIO/OLED test; no production events")
    parser.add_argument("--status-file", type=Path)
    args = parser.parse_args()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    hardware = reader = None
    last, last_level, changed_at = None, None, time.monotonic()
    next_draw = 0.0
    started = time.monotonic()
    try:
        hardware = open_hardware(args.buzzer)
        if not args.self_test:
            reader = SnapshotReader()
            reader.thread.start()
        while not stop.is_set():
            now = time.monotonic()
            error = None
            if args.self_test:
                stage = int((now - started) / 2.5)
                if stage >= 4:
                    break
                indicator = (Indicator("green", "SKOR RENDAH", .30),
                             Indicator("yellow", "WASPADA", .80),
                             Indicator("red", "INDIKASI JATUH", .90),
                             Indicator("offline", "CSI OFFLINE"))[stage]
            else:
                snapshot, error = reader.read()
                indicator = select_indicator(snapshot, now=time.time())
            if indicator.level != last_level:
                changed_at, last_level = now, indicator.level
                print(json.dumps({"panel": indicator.level, "score": indicator.score,
                                  "simulation": args.self_test, "error": error}), flush=True)
            hardware.update(indicator, now - changed_at)
            if now >= next_draw or indicator.level != (last.level if last else None):
                hardware.draw(indicator, simulated=args.self_test)
                if args.status_file:
                    write_status(args.status_file, indicator, args.buzzer, error, args.self_test)
                next_draw = now + .5
            last = indicator
            stop.wait(.01)
    finally:
        if hardware:
            hardware.close()
        if reader:
            reader.close()
        if args.status_file:
            write_status(args.status_file, Indicator("stopped", "PANEL BERHENTI"), args.buzzer, None, args.self_test)


if __name__ == "__main__":
    main()

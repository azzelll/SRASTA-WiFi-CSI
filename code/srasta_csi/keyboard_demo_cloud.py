"""Publish manual Pi status through the existing authenticated summary endpoint.

No CSI/model dependencies, event inserts, push jobs, or caregiver actions.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time

from .cloud_sync import CloudSync


MODEL_LABEL = "SRASTA keyboard demo (Pi)"


def demo_snapshot(fallen: bool, *, now: float, stopped: bool = False):
    return {
        "schema_version": 1, "updated_at_s": now, "observed_at_s": None,
        "source": "unavailable" if stopped else "simulator", "simulation": True,
        "state": "critical" if fallen else "normal", "state_verified": not stopped,
        "monitoring_online": False, "stream_age_s": None,
        "activity": "Jatuh terdeteksi" if fallen else "Idle",
        "motion_energy": None, "presence": "unknown", "inactivity": None,
        "stationary_duration_s": None, "breathing_condition": None,
        "fall_confidence": None, "breathing_bpm": None, "breathing_quality": 0,
        "breathing_reason": "Tidak diukur pada demo manual.", "signal_quality": None,
        "capture_rate_hz": 0, "accepted_frames": 0, "quarantined_frames": 0,
        "packet_loss_rate": None, "inference_ms": None, "serial_connected": False,
        "serial_reconnects": 0,
        "alarm": {"requested": False, "available": False, "active": False, "mode": "disabled"},
        "camera": {"available": False, "active": False, "result": "Tidak digunakan pada demo manual."},
        "blynk_connected": False, "remote": {"enabled": True, "connected": False},
        "model": {"label": MODEL_LABEL, "validation": "Status dipicu tombol Space pada Pi, tanpa inferensi model.",
                  "presence_available": False, "activity_classes_available": False},
        "events": [],
    }


def cloud_from_env(path: Path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('\"').strip("'")
    values.update(os.environ)
    names = ("SRASTA_SUPABASE_URL", "SRASTA_DEVICE_ID", "SRASTA_DEVICE_TOKEN")
    if any(not values.get(name) for name in names):
        raise ValueError("Konfigurasi cloud Pi belum lengkap (URL, device ID, token).")
    return KeyboardDemoCloud(*(values[name] for name in names))


class KeyboardDemoCloud(CloudSync):
    def __init__(self, url, device_id, device_token, *, post=None):
        # Reuse the existing URL/token validation, HTTPS transport and status.
        super().__init__(None, url, device_id, device_token, interval_s=1., post=post)
        self.lock = threading.Lock()
        self.wakeup = threading.Event()
        self.fallen = False

    def set_fallen(self, fallen: bool):
        with self.lock:
            self.fallen = fallen
        self.wakeup.set()

    def _send(self, *, stopped=False):
        with self.lock:
            fallen = self.fallen
        snapshot = demo_snapshot(fallen, now=time.time(), stopped=stopped)
        snapshot["remote"] = self.status()
        response = self.post({"device_id": self.device_id, "snapshot": snapshot, "events": [], "receipts": []})
        if not isinstance(response, dict) or response.get("ok") is not True or not isinstance(response.get("commands"), list):
            raise ValueError("Cloud belum mengonfirmasi status demo.")
        # Commands for real historical events remain untouched for the live service.
        self.connected = True
        self.last_success_s = time.time()
        self.last_error = None

    def _sync_once(self):
        self._send()

    def _run(self):
        while not self.stop.is_set():
            self.wakeup.clear()
            try:
                self.sync_once()
            except Exception:
                pass  # status() reports a sanitized error; local controls keep working.
            self.wakeup.wait(self.interval_s if self.connected else 2.)

    def close(self):
        self.stop.set()
        self.wakeup.set()
        if self.thread.is_alive():
            self.thread.join(timeout=6)
        if not self.thread.is_alive():
            try:
                self._send(stopped=True)
            except Exception:
                pass  # An unreachable cloud snapshot expires by its own timestamp.

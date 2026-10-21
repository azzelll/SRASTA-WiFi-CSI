"""Anomaly-only camera adapter; only bounded pose coordinates leave the edge."""
from __future__ import annotations

import threading
import time
import subprocess
import sys
from pathlib import Path

import numpy as np

from .pose import POSE_FORMAT, validate_pose


def posture_from_keypoints(keypoints: np.ndarray) -> str:
    points = np.asarray(keypoints)
    if points.shape != (17, 3) or not np.isfinite(points).all() or np.any((points < 0) | (points > 1)):
        return "Keypoint belum dapat dinilai"
    if np.max(points[:, 2]) < .3:
        return "Tubuh belum terbaca; periksa pandangan kamera"
    torso = points[[5, 6, 11, 12]]
    if np.min(torso[:, 2]) < 0.3:
        return "Keypoint tubuh kurang andal"
    # Head and both knees must be visible before interpreting torso direction.
    # Missing limbs can mean occlusion or cropping, not an absent person.
    if np.max(points[:5, 2]) < .3 or np.min(points[[13, 14], 2]) < .3:
        return "Tubuh belum terlihat utuh atau sebagian tertutup"
    if np.any((torso[:, :2] < .02) | (torso[:, :2] > .98)):
        return "Tubuh berada di tepi pandangan kamera"
    shoulder = np.mean(points[[5, 6], :2], axis=0)
    hip = np.mean(points[[11, 12], :2], axis=0)
    dy, dx = np.abs(hip - shoulder)
    if np.hypot(dy, dx) < .03:
        return "Keypoint tubuh kurang andal"
    if dx > dy * 1.5:
        return "Postur mendatar; perlu diperiksa caregiver"
    if dy > dx * 1.5:
        return "Postur belum mendukung indikasi jatuh"
    return "Arah tubuh belum jelas; periksa kondisi secara langsung"


def assess_capture(samples):
    """Vote on a bounded burst; preserve one measured pose, never average bodies.

    A legacy single-pose provider remains supported. Production uses three
    frames and requires at least two agreeing usable frames, with no opposite
    reliable posture in the burst. This rule is engineering, not calibrated
    posture accuracy.
    """
    frames = np.asarray(samples)
    if frames.shape == (17, 3):
        frames = frames[None]
    if frames.ndim != 3 or frames.shape[1:] != (17, 3) or not 1 <= len(frames) <= 3:
        return "Keypoint belum dapat dinilai", "uncertain", None
    candidates = []
    for points in frames:
        try:
            pose = validate_pose({"format": POSE_FORMAT, "keypoints": points.tolist()})
        except ValueError:
            continue
        result = posture_from_keypoints(points)
        outcome = "horizontal" if result.startswith("Postur mendatar") else "not_horizontal" if result.startswith("Postur belum") else "uncertain"
        candidates.append((outcome, result, pose, float(np.mean(points[[5, 6, 11, 12], 2]))))
    if not candidates:
        return "Keypoint belum dapat dinilai", "uncertain", None
    reliable = [row for row in candidates if row[0] != "uncertain"]
    kinds = {row[0] for row in reliable}
    required = 1 if len(frames) == 1 else 2
    if len(kinds) == 1 and len(reliable) >= required:
        chosen = max(reliable, key=lambda row: row[3])
        suffix = f" · konsisten {len(reliable)}/{len(frames)} cuplikan" if len(frames) > 1 else ""
        return chosen[1] + suffix, chosen[0], chosen[2]
    chosen = max(candidates, key=lambda row: row[3])
    reason = "Postur berubah antarcuplikan; periksa kondisi secara langsung" if len(kinds) > 1 else chosen[1] if not reliable else "Cuplikan andal belum cukup untuk memastikan postur"
    return reason, "uncertain", chosen[2]


class PiMoveNetCapture:
    def __init__(self, model_path, *, camera_python=sys.executable):
        # Keep camera construction lazy: no sensor activation outside anomaly.
        from .model import interpreter_class
        self.interpreter = interpreter_class()(model_path=str(model_path), num_threads=2)
        self.interpreter.allocate_tensors()
        self.input = self.interpreter.get_input_details()[0]
        self.output = self.interpreter.get_output_details()[0]
        self.camera_python = str(camera_python)
        if tuple(self.input["shape"]) != (1, 192, 192, 3):
            raise ValueError("MoveNet Lightning requires [1,192,192,3] input")
        if self.input["dtype"] not in {np.int32, np.uint8}:
            raise ValueError("MoveNet adapter requires int32 or uint8 pixel input")
        if tuple(self.output["shape"]) != (1, 1, 17, 3):
            raise ValueError("MoveNet output must contain 17 [y,x,score] keypoints")

    def __call__(self):
        # OS Python owns libcamera; the inference venv keeps its own NumPy/LiteRT.
        # Only the fixed RGB tensor passes through a bounded, local memory pipe.
        helper = Path(__file__).with_name("camera_capture.py")
        process = subprocess.run([self.camera_python, str(helper), "--frames", "3"], capture_output=True, timeout=10, check=True)
        if len(process.stdout) != 3 * 192 * 192 * 3:
            raise ValueError("Camera helper did not return exactly three 192x192 RGB frames")
        images = np.frombuffer(process.stdout, dtype=np.uint8).reshape(3, 192, 192, 3)
        burst = []
        for image in images:
            self.interpreter.set_tensor(self.input["index"], image[None].astype(self.input["dtype"]))
            self.interpreter.invoke()
            points = self.interpreter.get_tensor(self.output["index"]).reshape(17, 3).astype(np.float32)
            if self.output["dtype"] in {np.int8, np.uint8}:
                scale, zero = self.output["quantization"]
                points = (points - zero) * scale
            burst.append(points)
        return np.stack(burst)


class AnomalyCamera:
    def __init__(self, provider, capture=None, *, save_result=None, results_provider=None):
        self.provider, self.capture = provider, capture
        self.active = False
        self.result = "Kamera belum tersambung" if capture is None else "Siap; kamera hanya aktif saat anomali"
        self.last_event_uid = None
        self.validations = []
        self.save_result, self.results_provider = save_result, results_provider
        self.pending_result = None
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="anomaly-keypoints", daemon=True)

    def start(self):
        self.thread.start()

    def check_once(self):
        if not self._persist_pending():
            return
        status = self.provider()
        now = time.time()
        age, inferred = status.get("stream_age_s"), status.get("inferred_at_s")
        if (not self.capture or status.get("simulation_mode") or status.get("public_state") not in {"anomaly", "critical"}
                or status.get("state_source") != "model" or not (status.get("transport") or {}).get("connected")
                or age is None or not 0 <= age < 10 or inferred is None or not 0 <= now - inferred < 10):
            return
        event = status.get("last_event") or {}
        event_uid = event.get("event_uid")
        timestamp = event.get("timestamp_s")
        if (not event_uid or event.get("evidence") not in {"model", "timer"}
                or event.get("state") not in {"suspected_fall", "confirmed_fall", "anomaly", "critical"}
                or timestamp is None or not 0 <= now - timestamp < 60):
            return
        with self.lock:
            try:
                prior = self.results_provider() if self.results_provider else self.validations
            except Exception:
                self.result = "Riwayat kamera belum dapat dibaca; pemeriksaan ditunda"
                return  # Never recapture when durable deduplication is unavailable.
            if self.active or self.last_event_uid == event_uid or any(row["event_uid"] == event_uid for row in prior):
                return
            self.last_event_uid, self.active = event_uid, True
            self.result = "Validasi postur sedang berjalan"
        started = time.perf_counter()
        pose = None
        try:
            result, outcome, pose = assess_capture(self.capture())
        except Exception:
            result, outcome = "Validasi kamera gagal; periksa kondisi secara langsung", "error"
        finally:
            row = {"event_uid": event_uid, "checked_at_s": time.time(), "outcome": outcome,
                   "result": result, "latency_ms": (time.perf_counter() - started) * 1000,
                   "pose": pose}
            with self.lock:
                self.result, self.active = result, False
                self.validations = ([row] + self.validations)[:100]
                self.pending_result = row if self.save_result else None
            self._persist_pending()

    def _persist_pending(self):
        with self.lock:
            row = self.pending_result
            if row is None:
                return True
            try:
                self.save_result(row)
            except Exception:
                self.result = "Hasil kamera menunggu penyimpanan; akan dicoba ulang"
                return False
            self.pending_result = None
            self.result = row["result"]
            return True

    def _run(self):
        while not self.stop.wait(0.5):
            try:
                self.check_once()
            except Exception:
                with self.lock:
                    self.result = "Pemeriksaan kamera terhambat; akan dicoba ulang"

    def status(self):
        with self.lock:
            try:
                persisted = self.results_provider() if self.results_provider else []
            except Exception:
                persisted = []
            rows = {row["event_uid"]: row for row in persisted}
            rows.update({row["event_uid"]: row for row in self.validations})
            return {"available": self.capture is not None, "active": self.active, "result": self.result,
                    "event_uid": self.last_event_uid,
                    "validations": sorted(rows.values(), key=lambda row: row["checked_at_s"], reverse=True)[:100]}

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=12)

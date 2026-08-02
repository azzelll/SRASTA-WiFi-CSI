"""Replay-capable edge backend: bounded queue, ring buffer, state, SQLite, API."""

from __future__ import annotations

import json
import queue
import sqlite3
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from .baseline import FEATURE_NAMES, motion_features
from .contract import CSIFrame, FrameValidator
from .data import read_replay
from .decoder import FEATURE_COUNT, decode_iq_to_amplitude
from .model import TFLiteModel
from .preprocess import CausalPreprocessor, PreprocessConfig


@dataclass
class StateMachine:
    fall_threshold: float = 0.5
    motion_threshold: float = 0.02
    confirm_inactivity_s: float = 10.0
    state: str = "normal"
    last_motion_s: float | None = None

    def update(self, probability: float, motion_energy: float, now_s: float) -> tuple[str, bool]:
        if motion_energy >= self.motion_threshold:
            self.last_motion_s = now_s
        if self.state == "normal" and probability >= self.fall_threshold and motion_energy >= self.motion_threshold:
            self.state = "suspected_fall"
            return self.state, True
        if self.state == "suspected_fall" and self.last_motion_s is not None and now_s - self.last_motion_s >= self.confirm_inactivity_s:
            self.state = "confirmed_fall"
            return self.state, True
        if self.state == "confirmed_fall" and motion_energy >= self.motion_threshold:
            self.state = "normal"
            return self.state, True
        return self.state, False

    def tick(self, now_s: float) -> tuple[str, bool]:
        if self.state == "suspected_fall" and self.last_motion_s is not None and now_s - self.last_motion_s >= self.confirm_inactivity_s:
            self.state = "confirmed_fall"
            return self.state, True
        return self.state, False


class EventStore:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp_s REAL NOT NULL, state TEXT NOT NULL, confidence REAL NOT NULL, motion_energy REAL NOT NULL, evidence TEXT NOT NULL DEFAULT 'model')"
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(events)")}
        if "evidence" not in columns:
            self.connection.execute("ALTER TABLE events ADD COLUMN evidence TEXT NOT NULL DEFAULT 'model'")
        self.connection.commit()

    def append(self, timestamp_s: float, state: str, confidence: float, motion_energy: float, evidence: str = "model") -> None:
        self.connection.execute(
            "INSERT INTO events(timestamp_s,state,confidence,motion_energy,evidence) VALUES(?,?,?,?,?)",
            (timestamp_s, state, confidence, motion_energy, evidence),
        )
        self.connection.commit()

    def list(self, limit: int = 20) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT timestamp_s,state,confidence,motion_energy,evidence FROM events ORDER BY id DESC LIMIT ?",
            (min(max(limit, 1), 100),),
        ).fetchall()
        return [{"timestamp_s": row[0], "state": row[1], "confidence": row[2], "motion_energy": row[3], "evidence": row[4]} for row in rows]

    def close(self) -> None:
        self.connection.close()


class RandomForestInference:
    def __init__(self, model_path: str | Path):
        artifact = joblib.load(model_path)
        required = {"artifact_type", "model", "window_length", "feature_names", "capture_profile_hash", "preprocess_config_hash"}
        if not isinstance(artifact, dict) or not required.issubset(artifact) or artifact["artifact_type"] != "srasta_rf_baseline_v1":
            raise ValueError("invalid Random Forest artifact")
        if tuple(artifact["feature_names"]) != tuple(FEATURE_NAMES):
            raise ValueError("Random Forest feature contract mismatch")
        if list(artifact["model"].classes_) != [0, 1]:
            raise ValueError("Random Forest class order must be [nonfall, fall]")
        self.model = artifact["model"]
        self.window_length = int(artifact["window_length"])
        self.capture_profile_hash = str(artifact["capture_profile_hash"])
        self.preprocess_config_hash = str(artifact["preprocess_config_hash"])

    def probability(self, window: np.ndarray) -> float:
        return float(self.model.predict_proba(motion_features(window)[None, :])[0, 1])


class TFLiteInference:
    def __init__(self, model_path: str | Path):
        model_path = Path(model_path)
        training_path = model_path.parent / "training_config.json"
        if not training_path.is_file():
            raise ValueError("TFLite artifact is missing training provenance")
        training = json.loads(training_path.read_text())
        if training.get("representative_dataset") != "curated ESP32-S3 train split only" or not isinstance(training.get("manifest_sha256"), str):
            raise ValueError("TFLite artifact representative-data provenance is invalid")
        self.model = TFLiteModel(model_path)
        self.window_length = self.model.window_length
        if training.get("window_length") != self.window_length:
            raise ValueError("TFLite model and training window lengths differ")
        self.capture_profile_hash = ""
        self.preprocess_config_hash = ""

    def probability(self, window: np.ndarray) -> float:
        return self.model.probability(window)


def _load_config(model_path: Path, inference: RandomForestInference | TFLiteInference) -> PreprocessConfig:
    config_path = model_path.parent / "preprocess_config.json"
    capture_path = model_path.parent / "capture_profile.json"
    if not config_path.is_file() or not capture_path.is_file():
        raise ValueError("model artifact must include preprocessing and capture profile configurations")
    config = PreprocessConfig.from_json(json.loads(config_path.read_text()))
    capture = json.loads(capture_path.read_text())
    capture_hash = capture.get("hash")
    if not isinstance(capture_hash, str) or capture_hash != FrameValidator().profile.hash:
        raise ValueError("artifact capture profile differs from the active runtime profile")
    if config.capture_profile_hash != capture_hash:
        raise ValueError("preprocessing and capture profile hashes differ")
    expected = inference.preprocess_config_hash
    if expected and expected != config.hash:
        raise ValueError("model and preprocessing configuration hashes differ")
    if inference.capture_profile_hash and inference.capture_profile_hash != capture_hash:
        raise ValueError("model and capture profile hashes differ")
    return config


class EdgeRuntime:
    def __init__(self, model_path: str | Path, db_path: str | Path, *, queue_size: int = 64, ring_size: int = 512):
        model_path = Path(model_path)
        if model_path.suffix.lower() not in {".tflite", ".joblib"}:
            raise ValueError("edge model must be a .tflite candidate or .joblib RF baseline")
        self.inference = TFLiteInference(model_path) if model_path.suffix.lower() == ".tflite" else RandomForestInference(model_path)
        self.preprocessor = CausalPreprocessor(_load_config(model_path, self.inference))
        self.validator = FrameValidator()
        if self.preprocessor.config.capture_profile_hash and self.preprocessor.config.capture_profile_hash != self.validator.profile.hash:
            raise ValueError("runtime capture profile differs from preprocessing configuration")
        if queue_size <= 0 or ring_size < self.inference.window_length:
            raise ValueError("queue must be positive and ring must fit one inference window")
        self.frame_queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=queue_size)
        self.frames: deque[np.ndarray] = deque(maxlen=ring_size)
        self.frame_times: deque[float] = deque(maxlen=ring_size)
        self.machine = StateMachine(motion_threshold=self.preprocessor.config.motion_energy_threshold)
        self.store = EventStore(db_path)
        self.last_probability = 0.0
        self.last_motion_energy = 0.0
        self.last_inference_ms: float | None = None
        self.accepted_frames = 0
        self.dropped_frames = 0
        self.quarantine_count = 0
        self.packet_metrics_available = False
        self.last_replay_source: str | None = None

    def submit_amplitude(self, amplitude: np.ndarray, timestamp_s: float) -> bool:
        values = np.asarray(amplitude, dtype=np.float32)
        if values.shape != (FEATURE_COUNT,) or not np.isfinite(values).all() or not np.isfinite(timestamp_s):
            raise ValueError("queued amplitude frame must be finite [52] with a finite timestamp")
        try:
            self.frame_queue.put_nowait((values, float(timestamp_s)))
        except queue.Full:
            self.dropped_frames += 1
            return False
        self.accepted_frames += 1
        return True

    def process_queue(self) -> dict[str, object] | None:
        result = None
        while True:
            try:
                values, timestamp_s = self.frame_queue.get_nowait()
            except queue.Empty:
                break
            previous_time = self.frame_times[-1] if self.frame_times else None
            self.frame_queue.task_done()
            if previous_time is not None:
                gap = timestamp_s - previous_time
                if gap <= 0 or gap > self.preprocessor.config.max_gap_s:
                    self.quarantine_count += 1
                    result = FrameValidator.quarantine("queued timestamps are non-monotonic or exceed the maximum packet gap")
                    continue
            self.frames.append(values)
            self.frame_times.append(timestamp_s)
            resampled_count = int(np.floor((self.frame_times[-1] - self.frame_times[0]) * self.preprocessor.config.target_rate_hz + 1e-7)) + 1
            if resampled_count < self.inference.window_length:
                continue
            window, grid = self.preprocessor.window(
                np.stack(self.frames), np.asarray(self.frame_times, dtype=np.float64),
                self.inference.window_length, centered=False,
            )
            result = self._infer(window, float(grid[-1]))
        return result

    def replay(self, path: str | Path) -> dict[str, object]:
        if self.frames or not self.frame_queue.empty():
            raise RuntimeError("replay requires a fresh EdgeRuntime")
        replay = Path(path)
        if replay.suffix.lower() == ".jsonl":
            return self.replay_jsonl(replay)
        values, times = read_replay(replay, self.preprocessor.config.target_rate_hz)
        window, grid = self.preprocessor.window(values, times, self.inference.window_length, centered=True)
        self.packet_metrics_available = False
        self.last_replay_source = replay.suffix.lower().lstrip(".")
        # Replay uses the same preprocessor/window API as training; JSONL live
        # input uses the queue/ring path below with identical trailing windows.
        self.accepted_frames += len(values)
        self.frames.extend(window)
        self.frame_times.extend(grid)
        return self._infer(window, float(grid[-1]))

    def replay_jsonl(self, path: str | Path) -> dict[str, object]:
        if self.frames or not self.frame_queue.empty():
            raise RuntimeError("JSONL replay requires a fresh EdgeRuntime")
        self.packet_metrics_available = True
        self.last_replay_source = "jsonl"
        result = None
        for line in Path(path).read_text().splitlines():
            result = self.ingest_json_line(line) or result
        if result is None:
            raise RuntimeError("JSONL replay did not reach inference")
        return result

    def ingest_json_line(self, line: str) -> dict[str, object] | None:
        try:
            frame = self.validator.parse_json_line(line)
        except Exception as exc:
            self.quarantine_count += 1
            return FrameValidator.quarantine(exc)
        self.packet_metrics_available = True
        return self.ingest_frame(frame)

    def ingest_frame(self, frame: CSIFrame) -> dict[str, object] | None:
        try:
            if frame.length != self.validator.profile.raw_len or frame.bandwidth != self.validator.profile.bandwidth or frame.sig_mode != self.validator.profile.sig_mode or frame.channel != self.validator.profile.channel or frame.rx_state != 0:
                raise ValueError("CSIFrame differs from the active capture profile")
            amplitude = decode_iq_to_amplitude(frame.iq_bytes, first_word_invalid=frame.first_word_invalid)
            if not self.submit_amplitude(amplitude, frame.local_timestamp_us / 1_000_000.0):
                return {"status": "dropped", "reason": "bounded producer queue is full"}
            return self.process_queue()
        except ValueError as exc:
            self.quarantine_count += 1
            return FrameValidator.quarantine(exc)

    def observe(self, probability: float, motion_energy: float, now_s: float, *, evidence: str = "model") -> dict[str, object]:
        state, changed = self.machine.update(probability, motion_energy, now_s)
        self.last_probability, self.last_motion_energy = float(probability), float(motion_energy)
        if changed:
            self.store.append(now_s, state, probability, motion_energy, evidence)
        return self.status()

    def tick(self, now_s: float, *, evidence: str = "timer") -> dict[str, object]:
        state, changed = self.machine.tick(now_s)
        if changed:
            self.store.append(now_s, state, self.last_probability, self.last_motion_energy, evidence)
        return self.status()

    def _infer(self, window: np.ndarray, now_s: float) -> dict[str, object]:
        started = time.perf_counter()
        probability = self.inference.probability(window)
        self.last_inference_ms = (time.perf_counter() - started) * 1000
        motion = self.preprocessor.motion_energy(window)
        return self.observe(probability, motion, now_s)

    def status(self) -> dict[str, object]:
        validator = self.validator.stats()
        packet_drop_rate = None
        if self.packet_metrics_available:
            denominator = validator["accepted_frames"] + validator["missing_packets"]
            packet_drop_rate = float(validator["missing_packets"] / denominator) if denominator else 0.0
        return {
            "state": self.machine.state,
            "fall_probability": self.last_probability,
            "motion_energy": self.last_motion_energy,
            "inference_latency_ms": self.last_inference_ms,
            "queue_depth": self.frame_queue.qsize(),
            "queue_capacity": self.frame_queue.maxsize,
            "ring_depth": len(self.frames),
            "accepted_frames": self.accepted_frames,
            "dropped_frames": self.dropped_frames,
            "quarantine_count": self.quarantine_count,
            "packet_quality": {**validator, "available": self.packet_metrics_available, "packet_drop_rate": packet_drop_rate},
            "replay_source": self.last_replay_source,
        }

    def close(self) -> None:
        self.store.close()


def create_app(runtime: EdgeRuntime):
    from fastapi import FastAPI

    app = FastAPI(title="SRASTA BE + AI milestone")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "srasta-edge"}

    @app.get("/status")
    def status() -> dict[str, object]:
        return runtime.status()

    @app.get("/events")
    def events(limit: int = 20) -> dict[str, object]:
        return {"events": runtime.store.list(limit)}

    return app

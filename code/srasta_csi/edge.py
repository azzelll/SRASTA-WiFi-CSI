"""Replay-capable edge backend: bounded queue, ring buffer, state, SQLite, API."""

from __future__ import annotations

import asyncio
import json
import hashlib
import queue
import sqlite3
import threading
import time
import uuid
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from starlette.requests import Request

import joblib
import numpy as np

from .baseline import FEATURE_NAMES, motion_features
from .contract import CSIFrame, FrameValidator
from .data import read_replay
from .decoder import FEATURE_COUNT, USABLE_SUBCARRIER_INDICES, decode_iq_to_amplitude
from .model import TFLiteModel
from .preprocess import CausalPreprocessor, PreprocessConfig
from .monitoring import InactivityMonitor
from .presence import PresenceInference
from .pose import validate_pose


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
        self.lock = threading.RLock()
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp_s REAL NOT NULL, state TEXT NOT NULL, confidence REAL NOT NULL, motion_energy REAL NOT NULL, evidence TEXT NOT NULL DEFAULT 'model')"
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(events)")}
        if "evidence" not in columns:
            self.connection.execute("ALTER TABLE events ADD COLUMN evidence TEXT NOT NULL DEFAULT 'model'")
        if "acknowledged_at_s" not in columns:
            self.connection.execute("ALTER TABLE events ADD COLUMN acknowledged_at_s REAL")
        if "ack_source" not in columns:
            self.connection.execute("ALTER TABLE events ADD COLUMN ack_source TEXT")
        if "event_uid" not in columns:
            self.connection.execute("ALTER TABLE events ADD COLUMN event_uid TEXT")
        for (event_id,) in self.connection.execute("SELECT id FROM events WHERE event_uid IS NULL").fetchall():
            self.connection.execute("UPDATE events SET event_uid=? WHERE id=?", (str(uuid.uuid4()), event_id))
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS events_uid ON events(event_uid)")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, timestamp_s REAL NOT NULL, action TEXT NOT NULL, source TEXT NOT NULL)"
        )
        self.connection.execute("CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, event_uid TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL, timestamp_s REAL NOT NULL, synced INTEGER NOT NULL DEFAULT 0)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS cloud_events (event_id INTEGER PRIMARY KEY)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS camera_validations (event_uid TEXT PRIMARY KEY, checked_at_s REAL NOT NULL, outcome TEXT NOT NULL, result TEXT NOT NULL, latency_ms REAL NOT NULL)")
        camera_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(camera_validations)")}
        if "pose_json" not in camera_columns:
            self.connection.execute("ALTER TABLE camera_validations ADD COLUMN pose_json TEXT")
        self.connection.execute("INSERT OR IGNORE INTO cloud_events SELECT id FROM events")
        self.connection.commit()

    def append(self, timestamp_s: float, state: str, confidence: float, motion_energy: float, evidence: str = "model") -> None:
        with self.lock:
            self.connection.execute(
                "INSERT INTO events(timestamp_s,state,confidence,motion_energy,evidence,event_uid) VALUES(?,?,?,?,?,?)",
                (timestamp_s, state, confidence, motion_energy, evidence, str(uuid.uuid4())),
            )
            self.connection.execute("INSERT OR IGNORE INTO cloud_events VALUES(last_insert_rowid())")
            self.connection.commit()

    def list(self, limit: int = 20) -> list[dict[str, object]]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT id,timestamp_s,state,confidence,motion_energy,evidence,acknowledged_at_s,ack_source,event_uid FROM events ORDER BY id DESC LIMIT ?",
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [{"id": row[0], "timestamp_s": row[1], "state": row[2], "confidence": row[3], "motion_energy": row[4], "evidence": row[5], "acknowledged_at_s": row[6], "ack_source": row[7], "event_uid": row[8]} for row in rows]

    def save_camera_validation(self, result: dict[str, object]) -> None:
        pose = validate_pose(result.get("pose"))
        with self.lock:
            self.connection.execute("INSERT OR IGNORE INTO camera_validations(event_uid,checked_at_s,outcome,result,latency_ms,pose_json) VALUES(?,?,?,?,?,?)",
                                    tuple(result[name] for name in ("event_uid", "checked_at_s", "outcome", "result", "latency_ms")) +
                                    (json.dumps(pose, allow_nan=False) if pose is not None else None,))
            self.connection.commit()

    def camera_validations(self) -> list[dict[str, object]]:
        with self.lock:
            rows = self.connection.execute("SELECT event_uid,checked_at_s,outcome,result,latency_ms,pose_json FROM camera_validations ORDER BY checked_at_s DESC LIMIT 100").fetchall()
        return [dict(zip(("event_uid", "checked_at_s", "outcome", "result", "latency_ms"), row[:5]),
                     pose=validate_pose(json.loads(row[5])) if row[5] else None) for row in rows]

    def acknowledge_latest(self, source: str) -> int | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT id FROM events WHERE state IN ('suspected_fall','confirmed_fall','inactive','anomaly','critical') AND acknowledged_at_s IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self.connection.execute(
                "UPDATE events SET acknowledged_at_s=?,ack_source=? WHERE id=?",
                (time.time(), source, row[0]),
            )
            self.connection.execute("INSERT OR IGNORE INTO cloud_events VALUES(?)", (row[0],))
            self.connection.commit()
            return int(row[0])

    def add_action(self, action: str, source: str) -> None:
        if action != "assistance_requested":
            raise ValueError("unsupported caregiver action")
        with self.lock:
            self.connection.execute(
                "INSERT INTO actions(timestamp_s,action,source) VALUES(?,?,?)", (time.time(), action, source)
            )
            self.connection.commit()

    def actions(self, limit: int = 20) -> list[dict[str, object]]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT id,timestamp_s,action,source FROM actions ORDER BY id DESC LIMIT ?",
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [{"id": row[0], "timestamp_s": row[1], "action": row[2], "source": row[3]} for row in rows]

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def apply_command(self, command_id: str, event_uid: str, action: str, source: str, expires_at_s: float) -> dict[str, object]:
        """Atomically record a targeted action and its durable, idempotent receipt."""
        uuid.UUID(command_id)
        uuid.UUID(event_uid)
        if action not in {"acknowledge", "assistance"}:
            raise ValueError("unsupported caregiver command")
        with self.lock, self.connection:
            prior = self.connection.execute("SELECT event_uid,action,result FROM commands WHERE id=?", (command_id,)).fetchone()
            if prior:
                if prior[:2] != (event_uid, action):
                    raise ValueError("command ID already belongs to a different action")
                return json.loads(prior[2])
            event = self.connection.execute("SELECT id,state FROM events WHERE event_uid=?", (event_uid,)).fetchone()
            status = "expired" if expires_at_s <= time.time() else "rejected" if event is None or event[1] not in {"suspected_fall", "confirmed_fall", "inactive", "anomaly", "critical"} else "applied"
            result = {"id": command_id, "event_uid": event_uid, "action": action, "status": status, "applied_at_s": time.time() if status == "applied" else None, "auto_call": False}
            if status == "applied" and action == "acknowledge":
                self.connection.execute("UPDATE events SET acknowledged_at_s=COALESCE(acknowledged_at_s,?),ack_source=COALESCE(ack_source,?) WHERE id=?", (time.time(), source, event[0]))
                self.connection.execute("INSERT OR IGNORE INTO cloud_events VALUES(?)", (event[0],))
            elif status == "applied":
                self.connection.execute("INSERT INTO actions(timestamp_s,action,source) VALUES(?,?,?)", (time.time(), "assistance_requested", source))
            self.connection.execute("INSERT INTO commands(id,event_uid,action,status,result,timestamp_s) VALUES(?,?,?,?,?,?)", (command_id, event_uid, action, status, json.dumps(result), time.time()))
            return result

    def cloud_batch(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        with self.lock:
            ids = {row[0] for row in self.connection.execute("SELECT event_id FROM cloud_events LIMIT 100")}
            # Use the same explicit event allowlist as the local caregiver API.
            rows = self.connection.execute("SELECT id,timestamp_s,state,confidence,motion_energy,evidence,acknowledged_at_s,ack_source,event_uid FROM events WHERE id IN (SELECT event_id FROM cloud_events LIMIT 100)").fetchall()
            events = [{"id": r[0], "timestamp_s": r[1], "state": r[2], "confidence": r[3], "motion_energy": r[4], "evidence": r[5], "acknowledged_at_s": r[6], "ack_source": r[7], "event_uid": r[8]} for r in rows if r[0] in ids]
            receipts = [json.loads(r[0]) for r in self.connection.execute("SELECT result FROM commands WHERE synced=0 LIMIT 100")]
            return events, receipts

    def mark_cloud_batch(self, events: list[dict[str, object]], receipts: list[dict[str, object]]) -> None:
        with self.lock, self.connection:
            for event in events:
                # An ACK arriving while the request was in flight must stay pending.
                self.connection.execute("DELETE FROM cloud_events WHERE event_id=? AND EXISTS(SELECT 1 FROM events WHERE id=? AND acknowledged_at_s IS ?)", (event["id"], event["id"], event["acknowledged_at_s"]))
            self.connection.executemany("UPDATE commands SET synced=1 WHERE id=?", [(r["id"],) for r in receipts])


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
        if training.get("research_only") or training.get("classes", ["nonfall", "fall"]) != ["nonfall", "fall"]:
            raise ValueError("fall runtime requires a binary nonfall/fall artifact; research activity heads are separate")
        if training.get("representative_dataset") != "curated ESP32-S3 train split only" or not isinstance(training.get("manifest_sha256"), str):
            raise ValueError("TFLite artifact representative-data provenance is invalid")
        self.model = TFLiteModel(model_path)
        self.window_length = self.model.window_length
        if int(self.model.output_detail["shape"][-1]) != 2:
            raise ValueError("fall runtime requires a binary nonfall/fall artifact; research activity heads are separate")
        if training.get("window_length") != self.window_length:
            raise ValueError("TFLite model and training window lengths differ")
        self.fall_threshold = float(training.get("threshold", 0.5))
        self.capture_profile_hash = ""
        self.preprocess_config_hash = ""
        if not np.isfinite(self.fall_threshold) or not 0 < self.fall_threshold < 1:
            raise ValueError("artifact fall threshold must be between zero and one")
        frozen_path = model_path.parent / "frozen.json"
        if frozen_path.is_file():
            frozen = json.loads(frozen_path.read_text())
            if frozen.get("model_sha256") != hashlib.sha256(model_path.read_bytes()).hexdigest():
                raise ValueError("frozen model SHA-256 mismatch")
            if frozen.get("threshold") != self.fall_threshold or frozen.get("window_length") != self.window_length:
                raise ValueError("frozen model threshold/window differs from training provenance")
            if not frozen.get("software_ready"):
                raise ValueError("frozen artifact did not pass software readiness gates")
            self.capture_profile_hash = str(frozen.get("capture_profile_hash", ""))
            self.preprocess_config_hash = str(frozen.get("preprocess_config_hash", ""))

    def probability(self, window: np.ndarray) -> float:
        return self.model.probability(window)


def _load_config(model_path: Path, inference: RandomForestInference | TFLiteInference, validator: FrameValidator, allow_capture_profile_override: bool) -> PreprocessConfig:
    config_path = model_path.parent / "preprocess_config.json"
    capture_path = model_path.parent / "capture_profile.json"
    if not config_path.is_file() or not capture_path.is_file():
        raise ValueError("model artifact must include preprocessing and capture profile configurations")
    config = PreprocessConfig.from_json(json.loads(config_path.read_text()))
    capture = json.loads(capture_path.read_text())
    capture_hash = capture.get("hash")
    if not isinstance(capture_hash, str):
        raise ValueError("artifact capture profile hash is invalid")
    if config.capture_profile_hash != capture_hash:
        raise ValueError("preprocessing and capture profile hashes differ")
    expected = inference.preprocess_config_hash
    if expected and expected != config.hash:
        raise ValueError("model and preprocessing configuration hashes differ")
    if inference.capture_profile_hash and inference.capture_profile_hash != capture_hash:
        raise ValueError("model and capture profile hashes differ")
    if capture_hash != validator.profile.hash:
        if not allow_capture_profile_override or not isinstance(inference, TFLiteInference):
            raise ValueError("artifact capture profile differs from the active runtime profile")
        config = replace(config, capture_profile_hash=validator.profile.hash)
    return config


class EdgeRuntime:
    def __init__(self, model_path: str | Path, db_path: str | Path, *, queue_size: int = 64, ring_size: int = 512, validator: FrameValidator | None = None, max_gap_s: float | None = None, demo_mode: bool = False, allow_capture_profile_override: bool = False, auto_process_frames: bool = True, presence_model: str | Path | None = None, inactivity_s: float = 60.):
        model_path = Path(model_path)
        if model_path.suffix.lower() not in {".tflite", ".joblib"}:
            raise ValueError("edge model must be a .tflite candidate or .joblib RF baseline")
        self.inference = TFLiteInference(model_path) if model_path.suffix.lower() == ".tflite" else RandomForestInference(model_path)
        self.validator = validator or FrameValidator()
        config = _load_config(model_path, self.inference, self.validator, allow_capture_profile_override)
        if max_gap_s is not None:
            if not isinstance(self.inference, TFLiteInference):
                raise ValueError("live max-gap override is only allowed for a TFLite engineering candidate")
            config = replace(config, max_gap_s=max_gap_s)
        self.preprocessor = CausalPreprocessor(config)
        if self.preprocessor.config.capture_profile_hash and self.preprocessor.config.capture_profile_hash != self.validator.profile.hash:
            raise ValueError("runtime capture profile differs from preprocessing configuration")
        if queue_size <= 0 or ring_size < self.inference.window_length:
            raise ValueError("queue must be positive and ring must fit one inference window")
        self.frame_queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue(maxsize=queue_size)
        self.auto_process_frames = auto_process_frames
        self.processing_lock = threading.RLock()
        self.frames: deque[np.ndarray] = deque(maxlen=ring_size)
        self.frame_times: deque[float] = deque(maxlen=ring_size)
        self.presence_frames: deque[tuple[float, np.ndarray]] = deque(maxlen=4000)
        self.monitoring = InactivityMonitor(threshold_s=inactivity_s, max_gap_s=2.)
        self.presence_inference = PresenceInference(presence_model) if presence_model else None
        self.last_monitoring_event_state: str | None = None
        if self.presence_inference and self.presence_inference.capture_profile_hash != self.validator.profile.hash:
            raise ValueError("presence artifact differs from active capture profile")
        self.machine = StateMachine(fall_threshold=getattr(self.inference, "fall_threshold", 0.5), motion_threshold=self.preprocessor.config.motion_energy_threshold)
        self.store = EventStore(db_path)
        self.last_probability = 0.0
        self.last_motion_energy = 0.0
        self.last_inference_ms: float | None = None
        self.accepted_frames = 0
        self.dropped_frames = 0
        self.quarantine_count = 0
        self.packet_metrics_available = False
        self.last_replay_source: str | None = None
        self.transport_status: Callable[[], dict[str, object]] | None = None
        self.cloud_status: Callable[[], dict[str, object]] | None = None
        self.csi_history: deque[dict[str, object]] = deque(maxlen=100)
        self.csi_lock = threading.Lock()
        self.demo_mode = demo_mode
        self.demo_override = False
        self.demo_state: str | None = None
        self.demo_lock = threading.Lock()
        self.capture_profile_override = allow_capture_profile_override
        self.last_ingest_monotonic: float | None = None
        self.last_ingest_wall_s: float | None = None
        self.last_inference_wall_s: float | None = None
        self.last_inference_sample_s: float | None = None
        self.accepted_clock: deque[float] = deque(maxlen=500)
        self.started_wall_s = time.time()
        self.remote_status: Callable[[], dict[str, object]] | None = None
        self.alarm_status: Callable[[], dict[str, object]] | None = None
        self.camera_status: Callable[[], dict[str, object]] | None = None
        from .breathing import BreathingMonitor
        self.breathing = BreathingMonitor()
        self.assistance_requested = False

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
        with self.processing_lock:
            return self._process_queue()

    def _process_queue(self) -> dict[str, object] | None:
        result = None
        consumed = False
        while True:
            try:
                values, timestamp_s = self.frame_queue.get_nowait()
            except queue.Empty:
                break
            previous_time = self.frame_times[-1] if self.frame_times else None
            self.frame_queue.task_done()
            consumed = True
            if previous_time is not None:
                gap = timestamp_s - previous_time
                if gap <= 0 or gap > self.preprocessor.config.max_gap_s:
                    self.quarantine_count += 1
                    result = FrameValidator.quarantine("queued timestamps are non-monotonic or exceed the maximum packet gap")
                    self.frames.clear()
                    self.frame_times.clear()
                    self.presence_frames.clear()
                    self.monitoring.reset()
            self.frames.append(values)
            self.frame_times.append(timestamp_s)
            self.presence_frames.append((timestamp_s, values))
            while self.presence_frames and timestamp_s - self.presence_frames[0][0] > 11.:
                self.presence_frames.popleft()
        # Preserve every measured frame, then classify the latest trailing
        # window once. USB reading is independent of this expensive work.
        if not consumed:
            return None
        resampled_count = int(np.floor((self.frame_times[-1] - self.frame_times[0]) * self.preprocessor.config.target_rate_hz + 1e-7)) + 1
        if resampled_count < self.inference.window_length:
            return result
        window, grid = self.preprocessor.window(
            np.stack(self.frames), np.asarray(self.frame_times, dtype=np.float64),
            self.inference.window_length, centered=False,
        )
        return self._infer(window, float(grid[-1]))

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
        self.presence_frames.extend((float(t), v) for t, v in zip(times, values) if t <= grid[-1] and t >= grid[-1] - 11.)
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
            amplitude = decode_iq_to_amplitude(frame.iq_bytes, first_word_invalid=frame.first_word_invalid, subcarrier_order=self.validator.profile.subcarrier_order)
            self.last_ingest_monotonic = time.monotonic()
            self.last_ingest_wall_s = time.time()
            self.accepted_clock.append(self.last_ingest_monotonic)
            self.breathing.add(amplitude, frame.local_timestamp_us / 1_000_000.0)
            if not self.submit_amplitude(amplitude, frame.local_timestamp_us / 1_000_000.0):
                return {"status": "dropped", "reason": "bounded producer queue is full"}
            with self.csi_lock:
                self.csi_history.append({
                    "sequence": frame.sequence,
                    "timestamp_us": frame.local_timestamp_us,
                    "rssi_dbm": frame.rssi,
                    "noise_floor_dbm": frame.noise_floor,
                    "channel": frame.channel,
                    "first_word_invalid": frame.first_word_invalid,
                    "amplitude": amplitude.astype(float).tolist(),
                })
            return self.process_queue() if self.auto_process_frames else None
        except ValueError as exc:
            self.quarantine_count += 1
            return FrameValidator.quarantine(exc)

    def observe(self, probability: float, motion_energy: float, now_s: float, *, evidence: str = "model") -> dict[str, object]:
        self.last_probability, self.last_motion_energy = float(probability), float(motion_energy)
        if self.demo_mode:
            return self.status()
        state, changed = self.machine.update(probability, motion_energy, now_s)
        if changed:
            self.store.append(time.time(), state, probability, motion_energy, "replay_" + evidence if self.last_replay_source else evidence)
        return self.status()

    def tick(self, now_s: float, *, evidence: str = "timer") -> dict[str, object]:
        if self.demo_mode:
            return self.status()
        state, changed = self.machine.tick(now_s)
        if changed:
            self.store.append(time.time(), state, self.last_probability, self.last_motion_energy, "replay_" + evidence if self.last_replay_source else evidence)
        return self.status()

    def _infer(self, window: np.ndarray, now_s: float) -> dict[str, object]:
        started = time.perf_counter()
        probability = self.inference.probability(window)
        self.last_inference_ms = (time.perf_counter() - started) * 1000
        self.last_inference_wall_s = time.time()
        self.last_inference_sample_s = now_s
        motion = self.preprocessor.motion_energy(window)
        self.breathing.update(motion, self.preprocessor.config.motion_energy_threshold)
        present = None
        if self.presence_inference and self.presence_frames:
            samples = [(t, v) for t, v in self.presence_frames if t <= now_s]
            try:
                present = self.presence_inference.present(np.stack([v for _, v in samples]), np.asarray([t for t, _ in samples]))
            except ValueError:
                # Warm-up / packet gap gives unknown occupancy, never absence.
                present = None
        self.monitoring.observe(present=present, moving=motion >= self.machine.motion_threshold, timestamp_s=now_s)
        result = self.observe(probability, motion, now_s)
        if self.presence_inference and self.machine.state == "normal":
            monitor_state = "standby" if present is False else "inactive" if self.monitoring.inactive is True else "normal" if present is True else None
            if monitor_state and monitor_state != self.last_monitoring_event_state:
                self.store.append(time.time(), monitor_state, probability, motion, "replay_presence_timer" if self.last_replay_source else "presence_timer")
            self.last_monitoring_event_state = monitor_state
            result = self.status()
        return result

    def status(self) -> dict[str, object]:
        validator = self.validator.stats()
        packet_drop_rate = None
        if self.packet_metrics_available:
            denominator = validator["accepted_frames"] + validator["missing_packets"]
            packet_drop_rate = float(validator["missing_packets"] / denominator) if denominator else 0.0
        with self.demo_lock:
            demo_override = self.demo_override
            demo_state = self.demo_state
        with self.csi_lock:
            latest = self.csi_history[-1] if self.csi_history else None
        amplitude = latest.get("amplitude") if isinstance(latest, dict) else None
        csi_summary = None
        if isinstance(amplitude, list) and amplitude:
            csi_summary = {
                "sequence": latest["sequence"],
                "rssi_dbm": latest["rssi_dbm"],
                "minimum": min(amplitude),
                "mean": sum(amplitude) / len(amplitude),
                "maximum": max(amplitude),
            }
        model_state = "normal" if self.demo_mode else self.machine.state
        visible_state = demo_state if demo_state is not None else (
            "critical" if demo_override or model_state == "confirmed_fall" else
            "anomaly" if model_state == "suspected_fall" else
            "inactive" if self.monitoring.inactive is True else
            "standby" if self.monitoring.presence is False else "normal"
        )
        stream_age_s = None if self.last_ingest_monotonic is None else max(0.0, time.monotonic() - self.last_ingest_monotonic)
        feature_status = self.monitoring.status()
        if not self.last_replay_source and (self.last_inference_wall_s is None or time.time() - self.last_inference_wall_s > 2.):
            feature_status = {**feature_status, "presence": "unknown", "motion": "unknown", "inactive": None, "stationary_duration_s": None}
            if not self.demo_mode and visible_state in {"standby", "inactive"}:
                visible_state = "normal"
        transport = self.transport_status() if self.transport_status else None
        recent_events = self.store.list(1)
        return {
            "state": "confirmed_fall" if demo_override else "normal" if self.demo_mode else self.machine.state,
            "public_state": visible_state,
            "state_source": "demo_spacebar_mock" if demo_override else "demo_state_mock" if demo_state else "demo_reset" if self.demo_mode else "model",
            "model_state": model_state,
            "demo_mode": self.demo_mode,
            "demo_override": demo_override,
            "simulation_mode": bool(self.demo_mode or self.last_replay_source),
            "features": feature_status,
            "breathing_estimate_bpm": self.breathing.bpm if stream_age_s is not None and stream_age_s < 10 else None,
            "breathing_quality": self.breathing.quality if stream_age_s is not None and stream_age_s < 10 else 0,
            "local_alarm_on": visible_state == "critical",
            "assistance_requested": self.assistance_requested,
            "last_event": recent_events[0] if recent_events else None,
            "stream_age_s": stream_age_s,
            "observed_at_s": self.last_ingest_wall_s,
            "inferred_at_s": self.last_inference_wall_s,
            "started_at_s": self.started_wall_s,
            "capture_rate_hz": self.capture_rate_hz(),
            "fall_probability": self.last_probability,
            "motion_energy": self.last_motion_energy,
            "motion_threshold": self.machine.motion_threshold,
            "inference_latency_ms": self.last_inference_ms,
            "queue_depth": self.frame_queue.qsize(),
            "queue_capacity": self.frame_queue.maxsize,
            "ring_depth": len(self.frames),
            "accepted_frames": self.accepted_frames,
            "dropped_frames": self.dropped_frames,
            "quarantine_count": self.quarantine_count,
            "packet_quality": {**validator, "available": self.packet_metrics_available, "packet_drop_rate": packet_drop_rate},
            "replay_source": self.last_replay_source,
            "max_gap_s": self.preprocessor.config.max_gap_s,
            "capture_channel": self.validator.profile.channel,
            "subcarrier_order": self.validator.profile.subcarrier_order,
            "capture_profile_override": self.capture_profile_override,
            "latest_csi": csi_summary,
            "transport": transport,
            "blynk": self.cloud_status() if self.cloud_status else {"enabled": False, "connected": False},
        }

    def trigger_demo_fall(self) -> dict[str, object]:
        if not self.demo_mode:
            raise RuntimeError("demo mode is disabled")
        with self.demo_lock:
            changed = not self.demo_override
            self.demo_override = True
            self.demo_state = None
        if changed:
            now_s = time.time()
            self.store.append(now_s, "confirmed_fall", self.last_probability, self.last_motion_energy, "demo_spacebar_mock")
        return self.status()

    def reset_demo(self) -> dict[str, object]:
        if not self.demo_mode:
            raise RuntimeError("demo mode is disabled")
        with self.demo_lock:
            changed = self.demo_override
            self.demo_override = False
            self.demo_state = None
        self.machine.state = "normal"
        self.machine.last_motion_s = None
        if changed:
            now_s = time.time()
            self.store.append(now_s, "normal", self.last_probability, self.last_motion_energy, "demo_reset")
        return self.status()

    def set_demo_state(self, state: str) -> dict[str, object]:
        if not self.demo_mode or state not in {"standby", "normal", "inactive", "anomaly", "critical"}:
            raise ValueError("demo mode or requested state is invalid")
        with self.demo_lock:
            changed = self.demo_state != state or self.demo_override
            self.demo_state = state
            self.demo_override = False
        if changed:
            self.store.append(time.time(), state, self.last_probability, self.last_motion_energy, "demo_state_mock")
        return self.status()

    def acknowledge_alert(self, source: str = "local") -> dict[str, object]:
        event_id = self.store.acknowledge_latest(source)
        return {"acknowledged": event_id is not None, "event_id": event_id}

    def request_assistance(self, source: str = "local") -> dict[str, object]:
        self.store.add_action("assistance_requested", source)
        self.assistance_requested = True
        return {"assistance_requested": True, "auto_call": False}

    def health(self) -> dict[str, object]:
        transport = self.transport_status() if self.transport_status else None
        connected = bool(transport.get("connected")) if isinstance(transport, dict) else False
        age = None if self.last_ingest_monotonic is None else max(0.0, time.monotonic() - self.last_ingest_monotonic)
        recent = connected and age is not None and age < 10.0
        return {"ok": transport is None or recent, "service": "srasta-edge", "serial_connected": connected,
                "stream_recent": recent,
                "stream_age_s": age, "accepted_frames": self.accepted_frames,
                "quarantine_count": self.quarantine_count}

    def capture_rate_hz(self) -> float:
        recent = [t for t in list(self.accepted_clock) if t >= time.monotonic() - 5]
        if len(recent) < 2:
            return 0.0
        return round((len(recent) - 1) / max(recent[-1] - recent[0], 0.001), 1)

    def reset_capture_session(self) -> None:
        with self.processing_lock:
            self._reset_capture_session()

    def _reset_capture_session(self) -> None:
        self.validator.reset_stream()
        while not self.frame_queue.empty():
            self.frame_queue.get_nowait()
            self.frame_queue.task_done()
        self.frames.clear()
        self.frame_times.clear()
        self.presence_frames.clear()
        self.monitoring.reset()
        self.last_monitoring_event_state = None
        self.breathing.reset()
        self.accepted_clock.clear()
        self.machine.last_motion_s = None
        # A disconnect is not evidence that a person is inactive after a fall.
        if self.machine.state == "suspected_fall":
            self.machine.state = "normal"
        self.last_ingest_monotonic = None
        self.last_ingest_wall_s = None
        self.last_inference_wall_s = None
        self.last_inference_sample_s = None

    def apply_caregiver_command(self, **command) -> dict[str, object]:
        result = self.store.apply_command(**command)
        if result["status"] == "applied" and result["action"] == "assistance":
            self.assistance_requested = True
        return result

    def csi(self, limit: int = 1) -> dict[str, object]:
        limit = min(max(limit, 1), self.csi_history.maxlen or 100)
        with self.csi_lock:
            frames = list(self.csi_history)[-limit:]
        return {
            "representation": "decoded_amplitude",
            "feature_count": FEATURE_COUNT,
            "usable_subcarrier_indices": USABLE_SUBCARRIER_INDICES.tolist(),
            "buffer_capacity": self.csi_history.maxlen,
            "frame_count": len(frames),
            "frames": frames,
        }

    def close(self) -> None:
        self.store.close()


async def stream_csi(runtime: EdgeRuntime, interval_s: float = 0.05) -> AsyncGenerator[str, None]:
    last_sequence = None
    while True:
        payload = runtime.csi(1)
        frames = payload["frames"]
        frame = frames[-1] if isinstance(frames, list) and frames else None
        if isinstance(frame, dict) and frame.get("sequence") != last_sequence:
            last_sequence = frame["sequence"]
            yield f"id: {last_sequence}\nevent: csi\ndata: {json.dumps(frame, separators=(',', ':'))}\n\n"
        await asyncio.sleep(interval_s)


def create_app(runtime: EdgeRuntime):
    from pathlib import Path as _Path

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from .caregiver import caregiver_snapshot

    app = FastAPI(title="SRASTA Edge & Caregiver")

    @app.middleware("http")
    async def loopback_origin_guard(request: Request, call_next):
        from urllib.parse import urlparse
        from fastapi.responses import JSONResponse
        host = request.url.hostname
        test_client = request.client is not None and request.client.host == "testclient"
        if host not in {"127.0.0.1", "localhost", "::1"} and not (host == "testserver" and test_client):
            return JSONResponse({"error": "invalid_local_host"}, status_code=403)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                return JSONResponse({"error": "invalid_local_origin"}, status_code=403)
        return await call_next(request)

    _DASHBOARD_HTML = (_Path(__file__).resolve().parent.parent / "dashboard.html").read_text()

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        build = _Path(__file__).resolve().parents[2] / "web/dist/index.html"
        if build.is_file():
            return HTMLResponse(build.read_text())
        return _DASHBOARD_HTML

    @app.get("/technical", response_class=HTMLResponse)
    def technical_dashboard():
        return _DASHBOARD_HTML

    @app.get("/api/caregiver")
    def caregiver():
        return caregiver_snapshot(runtime)

    @app.get("/api/caregiver/stream")
    def caregiver_stream():
        async def snapshots():
            while True:
                yield f"event: snapshot\ndata: {json.dumps(caregiver_snapshot(runtime), separators=(',', ':'), allow_nan=False)}\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(snapshots(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/commands")
    async def caregiver_command(request: Request):
        from pydantic import BaseModel, ConfigDict, Field
        from typing import Literal
        from uuid import UUID
        class Command(BaseModel):
            model_config = ConfigDict(extra="forbid")
            id: UUID
            event_uid: UUID
            action: Literal["acknowledge", "assistance"]
            expires_at_s: float = Field(gt=0, allow_inf_nan=False)
        try:
            command = Command.model_validate(await request.json())
            if command.expires_at_s > time.time() + 600:
                raise ValueError("command expiry must be within ten minutes")
            return runtime.apply_caregiver_command(command_id=str(command.id), event_uid=str(command.event_uid), action=command.action, source="local_caregiver", expires_at_s=command.expires_at_s)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "Invalid caregiver command") from exc

    @app.get("/health")
    def health() -> dict[str, object]:
        return runtime.health()

    @app.get("/status")
    def status() -> dict[str, object]:
        return runtime.status()

    @app.get("/events")
    def events(limit: int = 20) -> dict[str, object]:
        return {"events": runtime.store.list(limit)}

    @app.get("/actions")
    def actions(limit: int = 20) -> dict[str, object]:
        return {"actions": runtime.store.actions(limit)}

    @app.post("/acknowledge")
    def acknowledge() -> dict[str, object]:
        return runtime.acknowledge_alert("local_dashboard")

    @app.post("/assistance")
    def assistance() -> dict[str, object]:
        return runtime.request_assistance("local_dashboard")

    @app.get("/csi")
    def csi(limit: int = 1) -> dict[str, object]:
        return runtime.csi(limit)

    @app.get("/csi/stream")
    def csi_stream():
        return StreamingResponse(
            stream_csi(runtime),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if runtime.demo_mode:
        @app.post("/demo/state/{state}")
        def demo_state(state: str) -> dict[str, object]:
            from fastapi import HTTPException
            try:
                return runtime.set_demo_state(state)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

        @app.post("/demo/fall")
        def demo_fall() -> dict[str, object]:
            return runtime.trigger_demo_fall()

        @app.post("/demo/reset")
        def demo_reset() -> dict[str, object]:
            return runtime.reset_demo()

    build_dir = _Path(__file__).resolve().parents[2] / "web/dist"
    if build_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=build_dir / "assets"), name="assets")
        for name in ("manifest.webmanifest", "sw.js", "icon.svg", "icon-192.png", "icon-512.png"):
            if (build_dir / name).is_file():
                def serve_file(filename=name):
                    return FileResponse(build_dir / filename, headers={"Cache-Control": "no-cache"})
                app.add_api_route(f"/{name}", serve_file, methods=["GET"])
    return app

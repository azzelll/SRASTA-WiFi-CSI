"""Local presence artifact and capture reader; unreviewed CSI is never fitted."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path

import joblib
import numpy as np

from .capture_archive import iter_jsonl, qa_capture, reviewed_events
from .decoder import decode_iq_to_amplitude
from .native_features import FEATURE_NAMES, native_motion_features

ARTIFACT_TYPE = "srasta_local_presence_52_v1"


def presence_features(values, times):
    values, times = np.asarray(values), np.asarray(times, dtype=float)
    if values.ndim != 2 or values.shape[1] != 52 or times.shape != (len(values),) or len(times) < 2:
        raise ValueError("presence requires measured [time,52] amplitudes")
    gaps = np.diff(times)
    if not np.isfinite(times).all() or np.any(gaps <= 0) or np.max(gaps) > .15:
        raise ValueError("presence packet clock must be continuous")
    grid = np.arange(times[0], times[-1], .1)
    if len(grid) < 100:
        raise ValueError("presence needs at least 10 seconds of continuous CSI")
    measured = np.column_stack([np.interp(grid, times, values[:, c]) for c in range(52)])
    return native_motion_features(measured, 10.)


class PresenceInference:
    def __init__(self, path):
        payload = joblib.load(path)
        if payload.get("artifact_type") != ARTIFACT_TYPE or payload.get("feature_names") != FEATURE_NAMES or payload.get("classes") != ["empty", "present"]:
            raise ValueError("presence requires a reviewed local 52-channel artifact")
        self.model = payload["model"]
        self.capture_profile_hash = payload["capture_profile_hash"]
        self.threshold = float(payload["threshold"])
        if not 0 < self.threshold < 1 or list(self.model.classes_) != [0, 1]:
            raise ValueError("invalid presence classes/threshold")

    def present(self, values, times):
        features = presence_features(values, times)
        probability = float(self.model.predict_proba(features[None])[0, 1])
        return probability >= self.threshold


def collect_presence_windows(root: Path):
    """Read accepted train/validation only. Preserve gap and interval boundaries."""
    rows, rejected = [], []
    for session in sorted((root / "sessions").glob("SES_*")):
        config = json.loads((session / "capture_config.json").read_text())
        if config["split"] not in {"train", "validation"}:
            continue  # never read local test/pilot payloads to fit/select
        qa = qa_capture(session)
        if not qa["labels_ready_for_training"]:
            rejected.append({"session_id": config["session_id"], "qa_status": qa["status"], "reasons": qa["pending_reasons"] + qa["issues"]})
            continue
        events = [e for e in reviewed_events(session, config) if e["review_status"] == "reconciled" and e["event_type"] in {"no_person", "nonfall_activity", "inactivity_without_fall"}]
        ordered = sorted(events, key=lambda e: e["onset_monotonic_us"])
        if any(a["event_end_monotonic_us"] > b["onset_monotonic_us"] for a, b in zip(ordered, ordered[1:])):
            rejected.append({"session_id": config["session_id"], "qa_status": "rejected", "reasons": ["overlapping presence annotation intervals"]})
            continue
        buffer = deque()
        active_id = None
        last = None
        last_window = None
        for frame in iter_jsonl(session / "frames.jsonl"):
            stamp = frame["timestamp_monotonic_us"] / 1e6
            event = next((e for e in events if e["onset_monotonic_us"] <= stamp * 1e6 < e["event_end_monotonic_us"]), None)
            identity = event["event_id"] if event else None
            if identity != active_id or last is not None and (stamp <= last or stamp - last > .15):
                buffer.clear()
                last_window = None
            active_id, last = identity, stamp
            if event is None:
                continue
            amp = decode_iq_to_amplitude(frame["iq_bytes"], first_word_invalid=frame["first_word_invalid"], subcarrier_order=config.get("subcarrier_order", "centered"))
            buffer.append((stamp, amp))
            while buffer and stamp - buffer[0][0] > 11.:
                buffer.popleft()
            if stamp - buffer[0][0] >= 10. and (last_window is None or stamp - last_window >= 10.):
                rows.append({"features": presence_features(np.stack([r[1] for r in buffer]), np.asarray([r[0] for r in buffer])), "label": int(event["event_type"] != "no_person"), "subject_id": config["subject_id"], "split": config["split"], "session_id": config["session_id"], "capture_profile_hash": config["capture_profile"]["hash"]})
                last_window = stamp
    return rows, rejected

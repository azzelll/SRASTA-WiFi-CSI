"""Protected continuous raw CSI archive with separate human annotations.

The runtime schema remains unchanged. Archive projection never pads, repairs,
or reorders a frame. Labels are pending until independently reviewed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

from .contract import CaptureProfile, FrameValidator
from .decoder import USABLE_SUBCARRIER_INDICES

CLASS_LABELS = ("no_person", "normal", "inactive", "fall_anomaly")
EVENT_CLASSES = {"no_person": "no_person", "nonfall_activity": "normal", "inactivity_without_fall": "inactive", "fall": "fall_anomaly"}
FRAME_SCHEMA = "srasta.csi.frame.v1"
ARCHIVE_FILES = {"capture_config.json", "frames.jsonl", "events.jsonl", "predictions.jsonl", "quarantine.jsonl", "capture_summary.json"}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            h.update(block)
    return h.hexdigest()


def private_write(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def validate_ids(config):
    for name in ("session_id", "subject_id", "site_id", "room_id"):
        value = config[name]
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9_]{3,80}", value):
            raise ValueError(f"{name} must be a pseudonymous uppercase code")
    if not config["subject_id"].startswith("LOC_"):
        raise ValueError("local subject IDs must start with LOC_")
    if config["split"] not in {"train", "validation", "test", "pilot"}:
        raise ValueError("invalid frozen subject split")


def protected_root(path):
    root = Path(path).expanduser().resolve()
    if any((parent / ".git").exists() for parent in [root, *root.parents]):
        raise ValueError("raw capture must be outside every Git working tree")
    if "data" in root.parts:
        raise ValueError("do not write captures into the source data tree")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root


def register_subject(root, subject_id, split):
    """Exclusive append-only split registry; never move a subject out of test."""
    import fcntl
    path = root / "subjects.jsonl"
    with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), "r+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        records = [json.loads(line) for line in stream if line.strip()]
        existing = [r for r in records if r["subject_id"] == subject_id]
        if existing and any(r["split"] != split for r in existing):
            raise ValueError("subject split is frozen; use the same split for every session")
        if not existing:
            stream.seek(0, os.SEEK_END)
            stream.write(canonical({"subject_id": subject_id, "split": split, "registered_at_utc": utc_now()}) + "\n")
            stream.flush(); os.fsync(stream.fileno())


def archive_projection(row):
    """Explicit full archive -> strict runtime schema, without feature repair."""
    if row.get("schema_version") != FRAME_SCHEMA or row.get("record_type") != "frame":
        raise ValueError("invalid archive frame schema")
    return {
        "version": 1, "sequence": row["sequence"], "local_timestamp_us": row["timestamp_monotonic_us"],
        "sender_mac": row["sender_mac"], "rssi": row["rssi_dbm"], "noise_floor": row["noise_floor_dbm"],
        "channel": row["channel"], "bandwidth": row["bandwidth"], "sig_mode": row["sig_mode"],
        "mcs": row["mcs"], "rx_state": row["rx_state"], "len": row["len"],
        "first_word_invalid": row["first_word_invalid"], "iq_bytes": row["iq_bytes"],
    }


class CaptureArchive:
    def __init__(self, root, config):
        self.root = protected_root(root)
        validate_ids(config)
        self.config = {**config, "protocol": "srasta-esp32-s3-capture-v1", "receiver_model": "ESP32-S3", "ltf": "LLTF", "bandwidth": "HT20", "raw_len": 128, "iq_order": "imag_real", "usable_indices": USABLE_SUBCARRIER_INDICES.tolist(), "source_corpus": "local_capture_v1"}
        profile = CaptureProfile(channel=config["channel"], subcarrier_order=config.get("subcarrier_order", "centered"))
        self.config["capture_profile"] = profile.to_json()
        self.config["acceptance"] = {"max_quarantine_fraction": .01, "max_sequence_gap_fraction": .01, "minimum_nonfall_observation_s": 60.0}
        self.config_hash = hashlib.sha256(canonical(self.config).encode()).hexdigest()
        self.path = self.root / "sessions" / config["session_id"]
        self.path.parent.mkdir(exist_ok=True, mode=0o700)
        self.path.mkdir(mode=0o700)  # existing recordings are never overwritten
        register_subject(self.root, config["subject_id"], config["split"])
        private_write(self.path / "capture_config.json", {**self.config, "capture_config_sha256": self.config_hash})
        self.streams = {name: os.fdopen(os.open(self.path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", buffering=1) for name in ("frames.jsonl", "events.jsonl", "predictions.jsonl", "quarantine.jsonl")}
        self.validator = FrameValidator(profile)
        self.lock = threading.RLock()
        self.last_frame = None
        self.last_frame_host_s = None
        self.sender_mac = config.get("sender_mac")
        self.first_timestamp_us = None
        self.last_predicted_state = "normal"
        self.alert_id = None
        self.prediction_count = 0
        self.last_prediction_us = None
        self.quarantine_count = 0
        self.duplicate_sequences = 0
        self.timestamp_reversals = 0
        self.closed = False
        self.failure = None
        self.started_utc = utc_now()

    def _append(self, name, row):
        self.streams[name].write(canonical(row) + "\n")

    def record(self, line):
        with self.lock:
            if self.closed or self.failure:
                return {"status": "dropped"}
            quarantine_before = self.validator.quarantined_frames
            try:
                # Validate structure/profile/sender before mutating sequence stats.
                payload = json.loads(line)
                if isinstance(payload, dict) and self.sender_mac and payload.get("sender_mac", "").lower() != self.sender_mac:
                    raise ValueError("controlled_sender_changed")
                if isinstance(payload, dict) and self.last_frame:
                    seq, stamp = payload.get("sequence"), payload.get("local_timestamp_us")
                    if isinstance(seq, int) and seq <= self.last_frame.sequence:
                        self.duplicate_sequences += 1
                    if isinstance(stamp, int) and stamp <= self.last_frame.local_timestamp_us:
                        self.timestamp_reversals += 1
                        if isinstance(seq, int) and seq < self.last_frame.sequence:
                            self.failure = "receiver_clock_reset"
                frame = self.validator.validate(payload) if isinstance(payload, dict) else self.validator.parse_json_line(line)
                self.sender_mac = frame.sender_mac
            except (ValueError, TypeError, AttributeError):
                if self.validator.quarantined_frames == quarantine_before:
                    self.validator.quarantined_frames += 1
                self.quarantine_count += 1
                self._append("quarantine.jsonl", {"reason": "contract_or_order_rejected", "captured_at_utc": utc_now(), "after_last_valid_timestamp_us": self.last_frame.local_timestamp_us if self.last_frame else None})
                return {"status": "quarantined"}
            row = {
                "schema_version": FRAME_SCHEMA, "record_type": "frame", "session_id": self.config["session_id"], "subject_id": self.config["subject_id"], "capture_config_sha256": self.config_hash,
                "sequence": frame.sequence, "sequence_epoch": 0, "timestamp_monotonic_us": frame.local_timestamp_us, "captured_at_utc": utc_now(),
                "sender_mac": frame.sender_mac, "rssi_dbm": frame.rssi, "noise_floor_dbm": frame.noise_floor, "channel": frame.channel,
                "bandwidth": frame.bandwidth, "sig_mode": frame.sig_mode, "ltf": "LLTF", "mcs": frame.mcs, "rx_state": frame.rx_state,
                "len": frame.length, "first_word_invalid": frame.first_word_invalid, "iq_order": "imag_real", "iq_bytes": list(frame.iq_bytes), "firmware_revision": self.config["firmware_revision"],
            }
            self._append("frames.jsonl", row)
            self.last_frame, self.last_frame_host_s = frame, time.monotonic()
            if self.first_timestamp_us is None:
                self.first_timestamp_us = frame.local_timestamp_us
            return frame

    def clock(self):
        with self.lock:
            if not self.last_frame or time.monotonic() - self.last_frame_host_s > 2:
                raise RuntimeError("CSI clock is stale; stop this session and reconnect RX")
            return self.last_frame.local_timestamp_us

    def stats(self):
        with self.lock:
            return {**self.validator.stats(), "duplicate_sequences": self.duplicate_sequences, "timestamp_reversals": self.timestamp_reversals, "clock_us": self.last_frame.local_timestamp_us if self.last_frame else None, "age_s": time.monotonic() - self.last_frame_host_s if self.last_frame_host_s is not None else None, "predictions": self.prediction_count, "failed": self.failure}

    def annotate(self, event_type, start_us, end_us, *, observer_id, confirmed, notes="", **extra):
        if event_type not in {*EVENT_CLASSES, "calibration", "interference", "recovery", "aborted_event"}:
            raise ValueError("unsupported observer event")
        if not isinstance(start_us, int) or not isinstance(end_us, int) or start_us >= end_us:
            raise ValueError("observer interval must have increasing receiver timestamps")
        if not re.fullmatch(r"ANN_[A-Z0-9_]{1,32}", observer_id):
            raise ValueError("observer must use an ANN_ code")
        allowed_extra = {"stationary_since_monotonic_us", "post_event_inactivity_start_monotonic_us", "post_event_inactivity_end_monotonic_us", "planned_activity"}
        if set(extra) - allowed_extra:
            raise ValueError("unsupported annotation metadata")
        event = {"schema_version": "srasta.csi.event.v1", "record_type": "event", "event_id": "EVT_" + uuid.uuid4().hex.upper(), "session_id": self.config["session_id"], "subject_id": self.config["subject_id"], "event_type": event_type if confirmed else "aborted_event", "activity_label": EVENT_CLASSES.get(event_type, event_type) if confirmed else "invalid_condition", "onset_monotonic_us": start_us, "event_end_monotonic_us": end_us, "annotation_method": "observer_confirmed_guided_interval", "annotator_ids": [observer_id], "review_status": "pending", "confirmed_by_observer": bool(confirmed), "annotated_at_utc": utc_now(), "notes": notes[:240], **extra}
        with self.lock:
            self._append("events.jsonl", event)
        return event

    def prediction(self, timestamp_us, state, probability, motion):
        with self.lock:
            if self.closed:
                return
            if state not in {"normal", "suspected_fall", "confirmed_fall"} or not isinstance(timestamp_us, int) or (self.last_prediction_us is not None and timestamp_us <= self.last_prediction_us):
                raise ValueError("prediction state/receiver clock is invalid")
            if not math.isfinite(probability) or not 0 <= probability <= 1 or not math.isfinite(motion) or motion < 0:
                raise ValueError("prediction values must be finite and in range")
            alert_start = state in {"suspected_fall", "confirmed_fall"} and self.last_predicted_state not in {"suspected_fall", "confirmed_fall"}
            if alert_start:
                self.alert_id = str(uuid.uuid4())
            if state == "normal":
                self.alert_id = None
            self._append("predictions.jsonl", {"timestamp_monotonic_us": timestamp_us, "state": state, "alert_start": alert_start, "alert_id": self.alert_id, "fall_confidence": probability, "motion_energy": motion, "source": "model"})
            self.last_predicted_state = state
            self.prediction_count += 1
            self.last_prediction_us = timestamp_us

    def close(self, *, completed, transport=None):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for stream in self.streams.values():
                stream.flush(); os.fsync(stream.fileno()); stream.close()
            private_write(self.path / "capture_summary.json", {"session_id": self.config["session_id"], "started_at_utc": self.started_utc, "ended_at_utc": utc_now(), "completed": completed, "failure": self.failure, "first_timestamp_us": self.first_timestamp_us, "last_timestamp_us": self.last_frame.local_timestamp_us if self.last_frame else None, "transport": transport, "stats": self.stats(), "prediction_count": self.prediction_count})
            private_write(self.path / "checksums.json", {name: digest(self.path / name) for name in sorted(ARCHIVE_FILES)})


def iter_jsonl(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def read_jsonl(path):
    return list(iter_jsonl(path))


def reviewed_events(path, config):
    events = read_jsonl(path / "events.jsonl")
    reviews = read_jsonl(path / "reviews.jsonl") if (path / "reviews.jsonl").exists() else []
    events_hash = digest(path / "events.jsonl")
    for event in events:
        event["review_status"] = "pending"
        for review in reviews:
            if review.get("event_id") != event["event_id"] or review.get("events_sha256") != events_hash:
                continue
            reviewer = review.get("reviewer_id")
            independent = isinstance(reviewer, str) and reviewer not in event["annotator_ids"] and re.fullmatch(r"ANN_[A-Z0-9_]{1,32}", reviewer)
            reference = review.get("reference_method") == "approved_synchronized_reference" and bool(review.get("authority_ref")) and bool(review.get("reference_id"))
            if independent or reference:
                event["review_status"] = "reconciled" if review.get("agrees") is True else "rejected"
    return events


def qa_capture(path):
    path = Path(path)
    config = json.loads((path / "capture_config.json").read_text())
    declared = config.pop("capture_config_sha256")
    issues = []
    if hashlib.sha256(canonical(config).encode()).hexdigest() != declared:
        issues.append("configuration checksum mismatch")
    checks = json.loads((path / "checksums.json").read_text())
    if set(checks) != ARCHIVE_FILES:
        issues.append("required archive checksums missing")
    for name, expected in checks.items():
        if name not in ARCHIVE_FILES or not (path / name).is_file() or digest(path / name) != expected:
            issues.append("archive checksum mismatch")
    validator = FrameValidator(CaptureProfile(channel=config["channel"], subcarrier_order=config.get("subcarrier_order", "centered")))
    if config.get("capture_profile") != validator.profile.to_json() or config.get("usable_indices") != USABLE_SUBCARRIER_INDICES.tolist() or config.get("raw_len") != 128 or config.get("iq_order") != "imag_real":
        issues.append("declared capture profile mismatch")
    registry = read_jsonl(path.parent.parent / "subjects.jsonl")
    subject_rows = [r for r in registry if r.get("subject_id") == config["subject_id"]]
    if not subject_rows or any(r.get("split") != config["split"] for r in subject_rows):
        issues.append("frozen subject registry mismatch")
    first, last, sender = None, None, None
    gaps = []
    frame_count = 0
    for row in iter_jsonl(path / "frames.jsonl"):
        if row["session_id"] != config["session_id"] or row["subject_id"] != config["subject_id"] or row["capture_config_sha256"] != declared or row["sequence_epoch"] != 0 or row["firmware_revision"] != config["firmware_revision"] or row["ltf"] != "LLTF" or row["iq_order"] != "imag_real":
            issues.append("archive identity/profile mismatch")
        try:
            previous = last
            frame = validator.validate(archive_projection(row))
            if sender and sender != frame.sender_mac:
                issues.append("controlled sender changed")
            if config.get("sender_mac") and config["sender_mac"] != frame.sender_mac:
                issues.append("configured controlled sender mismatch")
            sender = frame.sender_mac
            last = frame.local_timestamp_us
            first = last if first is None else first
            if previous is not None and last-previous > config["maximum_packet_gap_s"]*1e6:
                gaps.append((previous,last))
            frame_count += 1
        except ValueError:
            issues.append("invalid archived frame")
    quarantined = read_jsonl(path / "quarantine.jsonl")
    quarantine = len(quarantined)
    # Exclude the packet interval surrounding every quarantined item.
    quarantine_times = {q["after_last_valid_timestamp_us"] for q in quarantined if q.get("after_last_valid_timestamp_us") is not None}
    previous = None
    if quarantine_times:
        for row in iter_jsonl(path / "frames.jsonl"):
            stamp = row["timestamp_monotonic_us"]
            if previous in quarantine_times:
                gaps.append((previous, stamp))
            previous = stamp
    stats = validator.stats()
    summary = json.loads((path / "capture_summary.json").read_text())
    if not summary["completed"] or summary.get("failure"):
        issues.append("capture did not finish normally")
    if frame_count != summary["stats"]["accepted_frames"] or frame_count < 2:
        issues.append("frame summary reconciliation failed")
    if quarantine != summary["stats"]["quarantined_frames"] or first != summary["first_timestamp_us"] or last != summary["last_timestamp_us"]:
        issues.append("clock/quarantine summary reconciliation failed")
    prediction_count, previous_prediction = 0, None
    for p in iter_jsonl(path / "predictions.jsonl"):
        stamp = p.get("timestamp_monotonic_us")
        if not isinstance(stamp, int) or first is None or not first <= stamp <= last or (previous_prediction is not None and stamp <= previous_prediction):
            issues.append("prediction outside its session/clock")
        if p.get("source") != "model" or p.get("state") not in {"normal", "suspected_fall", "confirmed_fall"}:
            issues.append("invalid prediction source/state")
        previous_prediction = stamp
        prediction_count += 1
    if prediction_count != summary["prediction_count"]:
        issues.append("prediction summary reconciliation failed")
    loss = stats["missing_packets"] / max(1, frame_count+stats["missing_packets"])
    if quarantine/max(1,frame_count+quarantine) > config["acceptance"]["max_quarantine_fraction"] or loss > config["acceptance"]["max_sequence_gap_fraction"]:
        issues.append("declared packet acceptance thresholds exceeded")
    events = reviewed_events(path,config)
    previous_end = None
    for e in sorted(events,key=lambda e:e["onset_monotonic_us"]):
        start,end = e["onset_monotonic_us"],e["event_end_monotonic_us"]
        if e["session_id"] != config["session_id"] or e["subject_id"] != config["subject_id"] or first is None or not first <= start < end <= last:
            issues.append("annotation outside its session/clock")
        if previous_end is not None and start < previous_end:
            issues.append("overlapping observer intervals")
        previous_end = end
        if e["event_type"] == "fall":
            a,b = e.get("post_event_inactivity_start_monotonic_us"),e.get("post_event_inactivity_end_monotonic_us")
            if not isinstance(a,int) or not isinstance(b,int) or not end <= a < b <= last:
                issues.append("fall lacks verified post-event inactivity bounds")
        if e["event_type"] == "inactivity_without_fall" and start-e.get("stationary_since_monotonic_us",start) < config["inactivity_min_s"]*1e6:
            issues.append("inactive interval lacks the minimum prior stationary period")
        if e["review_status"] == "rejected":
            issues.append("observer disagreement")
    pending = any(e["review_status"] != "reconciled" for e in events if e["event_type"] in EVENT_CLASSES)
    reviewed_duration = sum((e["event_end_monotonic_us"]-e["onset_monotonic_us"])/1e6 for e in events if e["event_type"] in {"no_person","nonfall_activity","inactivity_without_fall"} and e["review_status"]=="reconciled")
    classified_events = [e for e in events if e["event_type"] in EVENT_CLASSES]
    minimum_duration_ok = reviewed_duration >= config["acceptance"]["minimum_nonfall_observation_s"] or any(e["event_type"] == "fall" and e["review_status"] == "reconciled" for e in events)
    firmware_pending = config.get("firmware_verification") == "not_verified_against_board"
    pending = pending or not classified_events or not minimum_duration_ok or not config.get("authority_ref") or not config.get("independent_local_cohort_attested") or firmware_pending
    status = "rejected" if issues else "pending" if pending else "accepted"
    return {"session_id":config["session_id"],"subject_id":config["subject_id"],"split":config["split"],"capture_config_sha256":declared,"status":status,"issues":sorted(set(issues)),"frame_count":frame_count,"quarantined_frames":quarantine,"packet_loss_rate":loss,"observed_duration_s":(last-first)/1e6 if first is not None and last is not None else 0,"reviewed_nonfall_duration_s":reviewed_duration,"class_counts":{label:sum(e["event_type"] in EVENT_CLASSES and EVENT_CLASSES[e["event_type"]]==label and e["review_status"]=="reconciled" for e in events) for label in CLASS_LABELS},"gap_intervals_us":gaps,"prediction_count":prediction_count,"labels_ready_for_training":status=="accepted" and config["split"] != "pilot","pending_reasons":(["independent observer review is required"] if any(e["review_status"]=="pending" for e in classified_events) else []) + (["authority reference / independent cohort provenance missing"] if not config.get("authority_ref") or not config.get("independent_local_cohort_attested") else []) + (["no eligible reviewed labelled intervals"] if not minimum_duration_ok or not classified_events else []) + (["firmware identity not attested against local build"] if firmware_pending else [])}

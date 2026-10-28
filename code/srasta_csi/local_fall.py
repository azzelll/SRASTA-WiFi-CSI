"""Measured local event windows, grouped by corrected person before any fit."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path

import numpy as np

from .capture_archive import ARCHIVE_FILES, iter_jsonl, qa_capture, reviewed_events
from .capture_governance import participant_identity
from .decoder import decode_iq_to_amplitude
from .preprocess import CausalPreprocessor


def replay_metrics(events, predictions, scopes):
    """Measured 1 Hz research replay coverage; never fill missing predictions."""
    from .capture_metrics import merge_intervals, intersect_intervals, contains

    coverage = merge_intervals([(a["timestamp_monotonic_us"], b["timestamp_monotonic_us"] + 1)
        for a,b in zip(predictions, predictions[1:])
        if 0 < b["timestamp_monotonic_us"] - a["timestamp_monotonic_us"] <= 1_500_000])
    negatives = [(e["onset_monotonic_us"], e["event_end_monotonic_us"]) for e in events
                 if e["event_type"] in {"no_person", "nonfall_activity", "inactivity_without_fall"}]
    eligible = intersect_intervals(intersect_intervals(negatives, scopes), coverage)
    exposure = sum(b-a for a,b in eligible)/1e6
    alert_ids = {p["alert_id"] for p in predictions if p.get("alert_start") and p.get("alert_id")
                 and contains(eligible, p["timestamp_monotonic_us"])}
    active_ids = {p["alert_id"] for p in predictions if p.get("alert_id")
                  and contains(eligible, p["timestamp_monotonic_us"])}
    active = [(a["timestamp_monotonic_us"], b["timestamp_monotonic_us"])
              for a,b in zip(predictions, predictions[1:]) if a["state"] != "normal"
              and b["timestamp_monotonic_us"]-a["timestamp_monotonic_us"] <= 1_500_000]
    records = []
    used = set()
    for event in events:
        if event["event_type"] != "fall":
            continue
        onset = event["onset_monotonic_us"]
        eligible_event = event["post_event_inactivity_end_monotonic_us"] >= onset+8_000_000 and any(
            a <= onset and b >= onset+8_000_000 for a,b in coverage)
        match = next((p for p in predictions if eligible_event and p.get("alert_start") and p.get("alert_id")
                      and p.get("alert_id") not in used
                      and onset <= p["timestamp_monotonic_us"] <= onset+8_000_000), None)
        if match:
            used.add(match["alert_id"])
        stationary, end = (event["post_event_inactivity_start_monotonic_us"],
                           event["post_event_inactivity_end_monotonic_us"])
        confirmation_eligible = end-stationary >= 10_000_000 and any(a <= stationary and b >= end for a,b in coverage)
        confirmation = next((p for p in predictions if match and p.get("alert_id") == match["alert_id"]
                             and p["state"] == "confirmed_fall"
                             and stationary+10_000_000 <= p["timestamp_monotonic_us"] <= end), None)
        records.append({"eligible": eligible_event, "detected": bool(match) if eligible_event else None,
                        "suspected_latency_s": (match["timestamp_monotonic_us"]-onset)/1e6 if match else None,
                        "confirmation_eligible": confirmation_eligible,
                        "confirmed_latency_s": (confirmation["timestamp_monotonic_us"]-onset)/1e6 if confirmation else None})
    eligible_falls = sum(r["eligible"] for r in records)
    hits = sum(r["detected"] is True for r in records)
    return {"eligible_nonfall_s": exposure, "false_alert_episodes": len(alert_ids),
            "left_censored_anomaly_episodes": len(active_ids-alert_ids),
            "anomaly_state_nonfall_s": sum(b-a for a,b in intersect_intervals(active, eligible))/1e6,
            "false_alerts_per_hour": len(alert_ids)/(exposure/3600) if exposure else None,
            "reviewed_falls": len(records), "eligible_falls": eligible_falls, "detected_falls": hits,
            "event_recall": hits/eligible_falls if eligible_falls else None,
            "confirmation_eligible_falls": sum(r["confirmation_eligible"] for r in records), "events": records}


def collect_local_fall_windows(root, preprocess, *, length=500, maximum_negative_windows=24):
    """Training only; one measured window per fall, bounded negative samples per session.

    Positives contain the observer-labelled fall and end at its actual end mark.
    Negatives lie entirely inside reviewed nonfall intervals. These are window
    proxies, not continuous event recall, FAR, or confirmation latency.
    """
    if length < 2 or maximum_negative_windows < 1:
        raise ValueError("positive window length and sample bound required")
    root = Path(root)
    rows = []
    report = {"sessions": [], "excluded_windows": [], "skipped_partitions": 0,
              "local_validation_payload_opened": False, "local_test_payload_opened": False,
              "window_metrics_are_event_metrics": False}
    processor = CausalPreprocessor(preprocess)
    duration_us = (length - 1) / preprocess.target_rate_hz * 1e6
    for session in sorted((root / "sessions").glob("SES_*")):
        config = json.loads((session / "capture_config.json").read_text())
        if config["split"] != "train":
            report["skipped_partitions"] += 1
            continue
        missing = [name for name in ARCHIVE_FILES | {"checksums.json"} if not (session / name).is_file()]
        if missing:
            report["sessions"].append({"session_id": session.name, "status": "rejected",
                                       "issues": ["incomplete archive"], "pending_reasons": []})
            continue
        qa = qa_capture(session)
        report["sessions"].append({key: qa[key] for key in
                                  ("session_id", "status", "issues", "pending_reasons")})
        if not qa["labels_ready_for_training"]:
            continue
        participant = participant_identity(session, config)
        events = [e for e in reviewed_events(session, config) if e["review_status"] == "reconciled"]
        targets = []
        for event in events:
            if event["event_type"] == "fall":
                targets.append((event["event_end_monotonic_us"], event, 1))
            elif event["event_type"] in {"no_person", "nonfall_activity", "inactivity_without_fall"}:
                lo = event["onset_monotonic_us"] + duration_us + 100_000
                hi = event["event_end_monotonic_us"] - 150_000
                count = min(maximum_negative_windows, int(max(0, hi - lo) // 10_000_000) + 1)
                if hi >= lo:
                    targets.extend((float(stamp), event, 0) for stamp in np.linspace(lo, hi, count))
        targets.sort(key=lambda value: value[0])
        if not targets:
            continue
        target_index = 0
        buffer = deque(maxlen=512)  # Same raw ring capacity as the edge runtime.
        previous = None
        gaps = sorted(qa["gap_intervals_us"])
        gap_index = 0
        for frame in iter_jsonl(session / "frames.jsonl"):
            stamp = frame["timestamp_monotonic_us"]
            interrupted = previous is not None and stamp - previous > preprocess.max_gap_s * 1e6
            while gap_index < len(gaps) and gaps[gap_index][1] <= stamp:
                interrupted |= previous is not None and gaps[gap_index][0] >= previous
                gap_index += 1
            if interrupted:
                buffer.clear()
            buffer.append(frame)
            previous = stamp
            while target_index < len(targets) and stamp >= targets[target_index][0]:
                _, event, label = targets[target_index]
                target_index += 1
                try:
                    selected = [r for r in buffer if r["timestamp_monotonic_us"] <= event["event_end_monotonic_us"]]
                    if not label:
                        selected = [r for r in selected if r["timestamp_monotonic_us"] >= event["onset_monotonic_us"]]
                    times = np.asarray([r["timestamp_monotonic_us"] / 1e6 for r in selected])
                    values = np.asarray([decode_iq_to_amplitude(
                        r["iq_bytes"], first_word_invalid=r["first_word_invalid"],
                        subcarrier_order=config.get("subcarrier_order", "centered")) for r in selected])
                    window, grid = processor.window(values, times, length, centered=False)
                    if label and grid[-1] * 1e6 < event["onset_monotonic_us"]:
                        raise ValueError("window does not overlap labelled fall")
                    rows.append({"window": window, "label": label, "subject_id": participant["subject_id"],
                                 "original_subject_id": config["subject_id"], "split": "train",
                                 "session_id": session.name, "event_id": event["event_id"],
                                 "start_us": float(grid[0] * 1e6), "end_us": float(grid[-1] * 1e6),
                                 "capture_profile_hash": config["capture_profile"]["hash"],
                                 "motion_energy": float(processor.motion_energy(window))})
                except ValueError as exc:
                    report["excluded_windows"].append({"session_id": session.name,
                        "event_id": event["event_id"], "label": label, "reason": str(exc)})
            if target_index == len(targets):
                break
    return rows, report

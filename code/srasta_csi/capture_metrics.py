"""Event false alerts on reviewed negatives with measured inference coverage.

This is separate from binary window specificity and from four-class validation.
Unreviewed labels, capture gaps and missing predictions never count as exposure.
"""
from __future__ import annotations

import json
from pathlib import Path

from .capture_archive import qa_capture, read_jsonl, reviewed_events


def merge_intervals(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def subtract_intervals(intervals, excluded):
    result = merge_intervals(intervals)
    for a, b in merge_intervals(excluded):
        next_result = []
        for start, end in result:
            if b <= start or a >= end:
                next_result.append((start, end))
            else:
                if start < a:
                    next_result.append((start, a))
                if b < end:
                    next_result.append((b, end))
        result = next_result
    return result


def intersect_intervals(left, right):
    a, b = merge_intervals(left), merge_intervals(right)
    i = j = 0
    result = []
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if end > start:
            result.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return result


def contains(intervals, stamp):
    return any(start <= stamp < end for start, end in intervals)


def false_alert_report(path):
    """Count one episode once; suspicion -> confirmation isn't another alert."""
    path = Path(path)
    qa = qa_capture(path)
    config = json.loads((path / "capture_config.json").read_text())
    events = reviewed_events(path, config)
    predictions = read_jsonl(path / "predictions.jsonl")
    base = {"session_id": config["session_id"], "split": config["split"], "model_sha256": config.get("model_sha256"), "qa_status": qa["status"], "final_model_target_proven": False, "four_class_target_proven": False}
    if qa["status"] != "accepted" or config["split"] == "pilot":
        return {**base, "available": False, "reason": "accepted independent annotations and non-pilot session required", "false_alerts_per_hour": None}
    negatives = [(e["onset_monotonic_us"], e["event_end_monotonic_us"]) for e in events if e["review_status"] == "reconciled" and e["event_type"] in {"no_person", "nonfall_activity", "inactivity_without_fall"}]
    negatives = subtract_intervals(negatives, qa["gap_intervals_us"])
    # Two neighbouring predictions prove coverage only when the recorded worker
    # cadence was maintained; warm-up and every inference outage are excluded.
    max_prediction_gap_us = max(.5, config.get("prediction_interval_s", .2)*3)*1e6
    coverage = [(a["timestamp_monotonic_us"], b["timestamp_monotonic_us"]+1) for a, b in zip(predictions, predictions[1:]) if 0 < b["timestamp_monotonic_us"]-a["timestamp_monotonic_us"] <= max_prediction_gap_us]
    eligible = intersect_intervals(negatives, coverage)
    duration_s = sum(end-start for start, end in eligible)/1e6
    if not duration_s:
        return {**base, "available": False, "reason": "no reviewed nonfall interval with measured inference coverage", "false_alerts_per_hour": None}
    ids = set()
    confirmed_ids = set()
    for p in predictions:
        if p.get("alert_start") and p.get("alert_id") and contains(eligible, p["timestamp_monotonic_us"]):
            ids.add(p["alert_id"])
        if p.get("state") == "confirmed_fall" and p.get("alert_id") in ids and contains(eligible, p["timestamp_monotonic_us"]):
            confirmed_ids.add(p["alert_id"])
    count = len(ids)
    hours = duration_s/3600
    from scipy.stats import chi2
    upper95 = float(chi2.ppf(.95, 2*(count+1))/2/hours)
    negative_s = sum(end-start for start, end in negatives)/1e6
    active_ids = {p["alert_id"] for p in predictions if p.get("alert_id") and contains(eligible, p["timestamp_monotonic_us"])}
    censored = active_ids-ids
    active_intervals = [(a["timestamp_monotonic_us"], b["timestamp_monotonic_us"]) for a,b in zip(predictions,predictions[1:]) if a["state"] != "normal"]
    active_s = sum(b-a for a,b in intersect_intervals(eligible,active_intervals))/1e6
    return {**base, "available": True, "reviewed_nonfall_s": negative_s, "eligible_nonfall_s": duration_s, "excluded_prediction_outage_s": max(0, negative_s-duration_s), "false_alert_episodes": count, "confirmed_false_alert_episodes": len(confirmed_ids), "left_censored_anomaly_episodes": len(censored), "anomaly_state_nonfall_s": active_s, "false_alerts_per_hour": count/hours, "poisson_one_sided_95_upper_per_hour": upper95, "two_per_day_supported_at_95_percent": upper95 <= 2/24 and not censored, "eligible_intervals_us": eligible, "missing_classes": [key for key, count in qa["class_counts"].items() if count == 0]}

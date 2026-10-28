#!/usr/bin/env python3
"""Bounded, paired research replay on existing train data; no live events."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from srasta_csi.capture_archive import digest, iter_jsonl, private_write, reviewed_events, utc_now
from srasta_csi.decoder import decode_iq_to_amplitude
from srasta_csi.edge import StateMachine
from srasta_csi.local_fall import replay_metrics
from srasta_csi.model import TFLiteModel
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--base", type=Path, default=Path("artifacts/releases/20261001-tcn-v8-motion-calibrated/selected"))
    args = p.parse_args()
    os.umask(0o077)
    candidate = json.loads((args.run / "candidate.json").read_text())
    protocol = json.loads((args.run / "protocol.json").read_text())
    inventory = json.loads((args.run / "inventory.json").read_text())
    accepted = {r["session_id"] for r in inventory["sessions"] if r["status"] == "accepted"}
    snapshot = json.loads((args.run / "archive_snapshot_before.json").read_text())
    if digest(args.run / "candidate.tflite") != candidate["model_sha256"]:
        raise ValueError("candidate hash changed")
    if digest(args.base / "model.tflite") != protocol["base_model_sha256"]:
        raise ValueError("base hash changed")
    config = PreprocessConfig.from_json(protocol["preprocessing"])
    processor = CausalPreprocessor(config)
    models = {"v8": TFLiteModel(args.base / "model.tflite"),
              "candidate": TFLiteModel(args.run / "candidate.tflite")}
    cuts = {"v8": (.45, config.motion_energy_threshold),
            "candidate": (candidate["threshold"], candidate["motion_threshold"])}
    scopes = {}
    for sid in sorted(accepted & snapshot.keys()):
        path = args.root / "sessions" / sid
        c = json.loads((path / "capture_config.json").read_text())
        if c["split"] != "train":
            raise ValueError("replay is train-only")
        for filename, expected in snapshot[sid].items():
            if digest(path / filename) != expected:
                raise ValueError("archive/review changed")
        events = reviewed_events(path,c)
        intervals = []
        for e in events:
            if e["review_status"] != "reconciled":
                raise ValueError("review changed")
            a,b = e["onset_monotonic_us"], e["event_end_monotonic_us"]
            if e["event_type"] == "fall":
                intervals.append((a, e["post_event_inactivity_end_monotonic_us"]))
            elif e["event_type"] in {"no_person", "nonfall_activity", "inactivity_without_fall"}:
                intervals.extend((int(start), int(start+60_000_000)) for start in
                                 np.linspace(a, b-60_000_000, 3) if b-a >= 60_000_000)
        scopes[sid] = {"intervals_us": intervals, "events": events}
    private_write(args.run / "replay_protocol.json", {
        "recorded_at_utc": utc_now(), "scope": "paired train replay of final refitted candidate; in-sample diagnostic",
        "inference_step_s": 1., "edge_cadence_reproduced": False,
        "warmup_per_chunk_s": 30., "negative_selection": "first/middle/last 60s of reviewed interval",
        "state_machine": "existing StateMachine; reset per chunk and packet outage",
        "preprocessing": config.to_json(), "cuts": cuts,
        "models": {"v8": protocol["base_model_sha256"], "candidate": candidate["model_sha256"]},
        "scopes_us": {sid:v["intervals_us"] for sid,v in scopes.items()},
        "source_sha256": digest(Path(__file__)), "test_payload_opened": False,
        "promotion_decision_uses_this_replay": False})
    results = []
    for sid, scope in scopes.items():
        path = args.root / "sessions" / sid
        c = json.loads((path / "capture_config.json").read_text())
        quarantine = {r["after_last_valid_timestamp_us"] for r in iter_jsonl(path / "quarantine.jsonl")
                      if r.get("after_last_valid_timestamp_us") is not None}
        intervals = scope["intervals_us"]
        predictions = {name: [] for name in models}
        machines = None
        buffer = deque(maxlen=512)
        previous = None
        segment = None
        next_prediction = None
        counters = {name: 0 for name in models}
        alert_ids = {name: None for name in models}
        timing = {name: [] for name in models}
        preprocess_timing = []
        for frame in iter_jsonl(path / "frames.jsonl"):
            stamp = frame["timestamp_monotonic_us"]
            selected_segment = next((i for i,(a,b) in enumerate(intervals)
                                     if a-30_000_000 <= stamp <= b+1_000_000), None)
            if selected_segment is None:
                if intervals and stamp > intervals[-1][1]+1_000_000:
                    break
                continue
            reset = selected_segment != segment or previous is not None and (
                stamp-previous > config.max_gap_s*1e6 or previous in quarantine)
            if reset:
                buffer.clear()
                machines = {name: StateMachine(fall_threshold=cut[0], motion_threshold=cut[1]) for name,cut in cuts.items()}
                alert_ids = {name: None for name in models}
                next_prediction = stamp
            segment = selected_segment
            previous = stamp
            buffer.append(frame)
            if stamp < next_prediction:
                continue
            next_prediction = stamp+1_000_000
            started = time.perf_counter()
            times = np.asarray([r["timestamp_monotonic_us"]/1e6 for r in buffer])
            values = np.asarray([decode_iq_to_amplitude(r["iq_bytes"], first_word_invalid=r["first_word_invalid"],
                                subcarrier_order=c.get("subcarrier_order", "centered")) for r in buffer])
            try:
                window, grid = processor.window(values, times, 500, centered=False)
            except ValueError:
                continue
            preprocess_timing.append((time.perf_counter()-started)*1000)
            now = float(grid[-1])
            energy = processor.motion_energy(window)
            for name, model in models.items():
                started = time.perf_counter()
                probability = model.probability(window)
                timing[name].append((time.perf_counter()-started)*1000)
                old = machines[name].state
                state,_ = machines[name].update(probability, energy, now)
                alert_start = old == "normal" and state == "suspected_fall"
                if alert_start:
                    counters[name] += 1
                    alert_ids[name] = f"{sid}_{segment}_{counters[name]}"
                if state == "normal":
                    alert_ids[name] = None
                predictions[name].append({"timestamp_monotonic_us": int(round(now*1e6)),
                    "state": state, "alert_id": alert_ids[name], "alert_start": alert_start,
                    "probability": probability, "motion_energy": float(energy)})
        report = {"session_id":sid, "models": {name: replay_metrics(scope["events"],rows,intervals)
                                                   for name,rows in predictions.items()},
                  "inference_ms": {name:{"median":float(np.median(v)), "p95":float(np.quantile(v,.95))}
                                   for name,v in timing.items() if v},
                  "preprocess_ms_median": float(np.median(preprocess_timing)) if preprocess_timing else None}
        private_write(args.run / ("replay_" + sid + ".json"), report)
        results.append(report)
        print(json.dumps({"session":sid,"predictions":{k:len(v) for k,v in predictions.items()}}),flush=True)
    summary = {}
    for name in models:
        values = [r["models"][name] for r in results]
        eligible = sum(r["eligible_falls"] for r in values)
        hits = sum(r["detected_falls"] for r in values)
        exposure = sum(r["eligible_nonfall_s"] for r in values)
        false = sum(r["false_alert_episodes"] for r in values)
        latencies = [e["suspected_latency_s"] for r in values for e in r["events"] if e["suspected_latency_s"] is not None]
        summary[name] = {"eligible_falls":eligible,"detected_falls":hits,
            "event_recall":hits/eligible if eligible else None,
            "nonfall_exposure_hours":exposure/3600,"false_alert_episodes":false,
            "false_alerts_per_hour":false/(exposure/3600) if exposure else None,
            "left_censored_anomaly_episodes":sum(r["left_censored_anomaly_episodes"] for r in values),
            "anomaly_state_nonfall_s":sum(r["anomaly_state_nonfall_s"] for r in values),
            "suspected_latency_s":latencies,
            "confirmation_eligible_falls":sum(r["confirmation_eligible_falls"] for r in values)}
    private_write(args.run / "replay_summary.json", {"scope":"paired 1Hz segmented train replay; in-sample candidate, not independent performance", "models":summary,"promoted_to_live":False})
    print(json.dumps(summary),flush=True)


if __name__ == "__main__":
    main()

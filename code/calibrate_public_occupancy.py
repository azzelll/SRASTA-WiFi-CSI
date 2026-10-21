#!/usr/bin/env python3
"""Disclosed validation calibration of already fitted public-source classifiers.

Original fixed-cutoff artifacts/reports are preserved. No payloads or test IDs
are opened here. This is post hoc development selection, not an independent
evaluation or an ESP32 transfer proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix


def choose_threshold(y, probabilities):
    y, scores = np.asarray(y), np.asarray(probabilities, dtype=float)
    if y.shape != scores.shape or y.ndim != 1 or set(y.tolist()) != {0, 1}:
        raise ValueError("both binary labels with matching probability vector required")
    if not np.isfinite(scores).all() or np.any(scores < 0) or np.any(scores > 1):
        raise ValueError("invalid probability")
    cuts = np.unique(np.r_[.5, scores[scores > 0]])
    best = None
    for cut in cuts:
        recall, specificity = float((scores[y == 1] >= cut).mean()), float((scores[y == 0] < cut).mean())
        rank = min(recall, specificity), (recall + specificity) / 2, -abs(float(cut) - .5)
        if best is None or rank > best[0]:
            best = rank, float(cut), recall, specificity
    return {"threshold": best[1], "positive_recall": best[2], "empty_recall_specificity": best[3],
            "balanced_accuracy": (best[2] + best[3]) / 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    reports = json.loads((args.run / "metrics.json").read_text())
    args.out_dir.mkdir(parents=True, exist_ok=False)
    results = {"evaluation": "post hoc candidate and cutoff selection on previously inspected development validation",
               "independent_test": False, "local_deployment_ready": False,
               "weights_refitted": False, "tasks": {}}
    for task, report in reports.items():
        candidates = []
        for trial in report["candidates"]:
            with np.load(args.run / task / trial["predictions_file"]) as saved:
                y, probability = saved["y"], saved["positive_probability"]
            result = dict(choose_threshold(y, probability), candidate=trial["candidate"])
            candidates.append(result)
        best = max(candidates, key=lambda r: (min(r["positive_recall"], r["empty_recall_specificity"]), r["balanced_accuracy"]))
        original_path = args.run / task / (best["candidate"] + ".joblib")
        payload = joblib.load(original_path)
        payload["threshold"] = best["threshold"]
        payload["calibration"] = {"source": "development validation", "post_hoc": True, "independent_test": False,
                                  "source_model_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest()}
        task_out = args.out_dir / task
        task_out.mkdir()
        joblib.dump(payload, task_out / "model.joblib", compress=3)
        trial = next(t for t in report["candidates"] if t["candidate"] == best["candidate"])
        with np.load(args.run / task / trial["predictions_file"]) as saved:
            y, probability = saved["y"], saved["positive_probability"]
        predictions = probability >= best["threshold"]
        best["classification"] = classification_report(y, predictions, labels=[0, 1], target_names=payload["classes"], output_dict=True, zero_division=0)
        best["confusion_matrix"] = confusion_matrix(y, predictions, labels=[0, 1]).tolist()
        strata = ["empty", "sleep"] + (["awake"] if task == "presence" else [])
        offset = 0
        best["stratum_positive_prediction_rate"] = {}
        for stratum in strata:
            count = report["counts"]["validation"][stratum]
            best["stratum_positive_prediction_rate"][stratum] = float(predictions[offset:offset + count].mean())
            offset += count
        best["model_sha256"] = hashlib.sha256((task_out / "model.joblib").read_bytes()).hexdigest()
        results["tasks"][task] = {"selected": best, "candidates": candidates}
    (args.out_dir / "metrics.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

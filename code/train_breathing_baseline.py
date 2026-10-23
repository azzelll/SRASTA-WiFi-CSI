#!/usr/bin/env python3
"""Grouped public sleep/empty baseline; no ESP32 deployment claim or BPM labels."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import time

import h5py
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

from srasta_csi.native_features import FEATURE_NAMES, native_motion_features


def select_rows(root: Path, cap: int):
    """Freeze disjoint users before selection; avoid devices with only one label."""
    with (root / "metadata/sample_metadata.csv").open() as f:
        rows = list(csv.DictReader(f))
    # The supplied random split mixes subjects. Retain only source-train
    # payloads, then split those by user for this development experiment.
    allowed = set(json.loads((root / "splits/train_id.json").read_text()))
    rows = [r for r in rows if r["id"] in allowed]
    labels = defaultdict(set)
    for row in rows:
        labels[(row["user"], row["device"], row["num_sub"])].add(row["label"])
    partitions = {"train": "U06", "validation": "U23"}
    selected = {}
    for split, user in partitions.items():
        result = []
        for label in ("empty", "sleep"):
            candidates = [r for r in rows if r["user"] == user and r["label"] == label and labels[(user, r["device"], r["num_sub"])] == {"empty", "sleep"}]
            candidates.sort(key=lambda r: hashlib.sha256(("srasta-breathing-v1:" + r["id"]).encode()).hexdigest())
            result.extend(candidates[:cap])
        if len({r["label"] for r in result}) != 2:
            raise ValueError("each subject partition must contain both observed labels")
        selected[split] = result
    ids = [{r["id"] for r in value} for value in selected.values()]
    if ids[0] & ids[1]:
        raise ValueError("sample overlap")
    return selected, {"users": partitions, "cap_per_class": cap, "excluded_user": "U24: no empty class", "rule": "source-train payloads only; user split before sampling; native device/shape groups must contain both labels", "source_test_policy": "official validation/test payloads excluded; custom grouped development split; no official benchmark or SRASTA test score", "source_train_ids_sha256": hashlib.sha256((root / "splits/train_id.json").read_bytes()).hexdigest()}


def load_native(root: Path, rows):
    values = []
    for index, row in enumerate(rows):
        path = (root / row["file_path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("metadata escaped source corpus")
        with h5py.File(path) as f:
            amplitude = np.asarray(f["CSI_amps"], dtype=np.float32)
        if amplitude.shape != (int(row["num_sub"]), 300, 1):
            raise ValueError(f"unexpected native breathing shape: {amplitude.shape}")
        values.append(native_motion_features(amplitude[:, :, 0].T, 30))
        if (index + 1) % 500 == 0:
            print(f"Loaded {index + 1}/{len(rows)} native recordings", flush=True)
    return np.stack(values), np.asarray([int(r["label"] == "sleep") for r in rows])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("data/csi-bench/BreathingDetection"))
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--cap-per-class", type=int, default=2000)
    args = p.parse_args()
    if args.cap_per_class < 1:
        p.error("positive cap required")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    selected, protocol = select_rows(args.source, args.cap_per_class)
    protocol.update({"classes": ["empty", "sleep"], "missing_class": "normal/awake", "hardware": "public 5 GHz IoT; not ESP32-S3", "features": FEATURE_NAMES, "source_metadata_sha256": hashlib.sha256((args.source / "metadata/sample_metadata.csv").read_bytes()).hexdigest(), "sampling_rate": "nominal 30 Hz per source paper; no packet-clock or respiratory-reference validation", "model": "RandomForest 300 trees, min leaf 5, balanced classes, seed 42; no validation fitting", "local_deployment_ready": False})
    save = lambda name, data: (args.out_dir / name).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    save("protocol.json", protocol)
    save("selected_metadata.json", selected)
    arrays = {split: load_native(args.source, rows) for split, rows in selected.items()}
    model = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced", random_state=42, n_jobs=2)
    model.fit(*arrays["train"])
    x, y = arrays["validation"]
    started = time.perf_counter()
    predictions = model.predict(x)
    report = {"evaluation": "public cross-user/cross-device binary classification development proxy", "classes": ["empty", "sleep"], "classification": classification_report(y, predictions, labels=[0, 1], target_names=["empty", "sleep"], output_dict=True, zero_division=0), "confusion_matrix": confusion_matrix(y, predictions, labels=[0, 1]).tolist(), "rows": {s: dict(Counter(r["label"] for r in rs)) for s, rs in selected.items()}, "prediction_ms_per_recording": (time.perf_counter() - started) * 1000 / len(y), "normal_class_ready": False, "ESP32_validated": False, "respiratory_rate_validated": False}
    joblib.dump({"artifact_type": "srasta_public_breathing_native_v1", "model": model, "feature_names": FEATURE_NAMES, "classes": ["empty", "sleep"], "research_only": True, "protocol": protocol}, args.out_dir / "model.joblib")
    save("metrics.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

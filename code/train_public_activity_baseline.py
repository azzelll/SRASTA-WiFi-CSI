#!/usr/bin/env python3
"""Native HAR research baseline: supplied source-train only, held-out user U06."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import h5py
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

from srasta_csi.native_features import FEATURE_NAMES, native_motion_features


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("data/csi-bench/HumanActivityRecognition"))
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--cap-per-class", type=int, default=400)
    args = p.parse_args()
    if args.cap_per_class < 1:
        p.error("positive cap required")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    allowed = set(json.loads((args.source / "splits/train_id.json").read_text()))
    with (args.source / "metadata/sample_metadata.csv").open() as f:
        rows = [r for r in csv.DictReader(f) if r["id"] in allowed]
    labels = sorted({r["label"] for r in rows})
    selected = {}
    for split in ["train", "validation"]:
        result = []
        for label in labels:
            candidates = [r for r in rows if r["label"] == label and (r["user"] == "U06") == (split == "validation")]
            candidates.sort(key=lambda r: hashlib.sha256(("srasta-har-v1:" + r["id"]).encode()).hexdigest())
            result.extend(candidates[:args.cap_per_class])
        if {r["label"] for r in result} != set(labels):
            raise ValueError("both grouped partitions must contain every observed class")
        selected[split] = result
    protocol = {"classes": labels, "metadata_num_classes": json.loads((args.source / "metadata/label_mapping.json").read_text())["num_classes"], "observed_num_classes": len(labels), "split": "source-train only; held-out user U06 before sampling", "source_test_opened": False, "nominal_rate_hz": 100, "native_frames": 500, "features": FEATURE_NAMES, "source_metadata_sha256": hashlib.sha256((args.source / "metadata/sample_metadata.csv").read_bytes()).hexdigest(), "normal_candidate": "seated-breathing is an activity label; awake context needs review before three-class breathing training", "ESP32_S3_validated": False}
    save = lambda name, value: (args.out_dir / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    save("protocol.json", protocol)
    save("selected_metadata.json", selected)
    def load(records):
        xs = []
        for i, r in enumerate(records):
            source = (args.source / r["file_path"]).resolve()
            if not source.is_relative_to(args.source.resolve()):
                raise ValueError("source escaped corpus")
            with h5py.File(source) as f:
                amplitude = np.asarray(f["CSI_amps"], dtype=np.float32)
            if amplitude.shape != (int(r["num_sub"]), 500, 1):
                raise ValueError(f"unexpected HAR native shape {amplitude.shape}")
            xs.append(native_motion_features(amplitude[:, :, 0].T, 100))
            if (i+1) % 500 == 0:
                print(f"Loaded {i+1}/{len(records)} HAR recordings", flush=True)
        return np.stack(xs), np.asarray([labels.index(r["label"]) for r in records])
    arrays = {split: load(rs) for split, rs in selected.items()}
    model = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced", random_state=42, n_jobs=2).fit(*arrays["train"])
    x, y = arrays["validation"]
    pred = model.predict(x)
    report = {"classification": classification_report(y, pred, target_names=labels, output_dict=True, zero_division=0), "confusion_matrix": confusion_matrix(y, pred).tolist(), "recordings": {s: dict(Counter(r["label"] for r in rs)) for s, rs in selected.items()}, "source_test_opened": False, "ESP32_S3_validated": False}
    save("metrics.json", report)
    joblib.dump({"artifact_type": "srasta_public_har_native_v1", "research_only": True, "model": model, "classes": labels, "feature_names": FEATURE_NAMES, "protocol": protocol}, args.out_dir / "model.joblib")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

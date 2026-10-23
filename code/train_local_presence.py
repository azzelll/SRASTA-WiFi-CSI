#!/usr/bin/env python3
"""Train presence only when reviewed, grouped local train/validation exist."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

from srasta_csi.native_features import FEATURE_NAMES
from srasta_csi.presence import ARTIFACT_TYPE, collect_presence_windows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path("../SRASTA_LOCAL_CAPTURE"))
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    rows, excluded = collect_presence_windows(args.root)
    partitions = {s: [r for r in rows if r["split"] == s] for s in ["train", "validation"]}
    ready = all({r["label"] for r in rs} == {0, 1} for rs in partitions.values())
    subjects = {s: {r["subject_id"] for r in rs} for s, rs in partitions.items()}
    if subjects["train"] & subjects["validation"]:
        raise ValueError("presence subject leakage")
    profile_hashes = {r["capture_profile_hash"] for r in rows}
    ready = ready and len(profile_hashes) == 1
    report = {"ready_to_train": ready, "windows": {s: len(rs) for s, rs in partitions.items()}, "excluded_sessions": excluded, "local_test_opened": False, "required": "accepted local train and validation with both labels, disjoint subjects, one capture profile"}
    if ready:
        arrays = {s: (np.stack([r["features"] for r in rs]), np.asarray([r["label"] for r in rs])) for s, rs in partitions.items()}
        model = RandomForestClassifier(n_estimators=200, min_samples_leaf=3, class_weight="balanced", random_state=42, n_jobs=2).fit(*arrays["train"])
        x, y = arrays["validation"]
        report["classification"] = classification_report(y, model.predict(x), target_names=["empty", "present"], output_dict=True, zero_division=0)
        joblib.dump({"artifact_type": ARTIFACT_TYPE, "model": model, "classes": ["empty", "present"], "feature_names": FEATURE_NAMES, "threshold": .5, "capture_profile_hash": next(iter(profile_hashes))}, args.out_dir / "model.joblib")
    (args.out_dir / "readiness.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Train the transparent train/validation-only SRASTA Random Forest baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np

from srasta_csi.baseline import FEATURE_NAMES, motion_features
from srasta_csi.contract import CaptureProfile
from srasta_csi.data import ManifestRow, manifest_sha256, read_h5_amplitude, read_manifest, resolve_source_path, split_report, timestamps
from srasta_csi.metrics import classification_metrics, unavailable_event_metrics
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


def load_features(rows: list[ManifestRow], split: str, data_root: Path, processor: CausalPreprocessor, window_length: int = 250) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for row in rows:
        if row.split != split:
            continue
        values = read_h5_amplitude(resolve_source_path(row, data_root))
        window, _ = processor.window(values, timestamps(len(values)), window_length, centered=True)
        x.append(motion_features(window, motion_threshold=processor.config.motion_energy_threshold))
        y.append(row.label_id)
    if not x:
        raise ValueError(f"no {split} rows")
    return np.stack(x), np.asarray(y, dtype=np.int64)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/srasta_rf_baseline"))
    parser.add_argument("--trees", type=int, default=500)
    args = parser.parse_args()
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite {args.out_dir}")
    from sklearn.ensemble import RandomForestClassifier

    rows = read_manifest(args.manifest)
    data_root = args.data_root.resolve()
    expected_manifest = data_root / "curated/esp32_s3_fall_v1/manifest.csv"
    if args.manifest.resolve() != expected_manifest.resolve():
        raise ValueError("Random Forest training only accepts esp32_s3_fall_v1/manifest.csv")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    profile = CaptureProfile()
    config = PreprocessConfig(capture_profile_hash=profile.hash)
    processor = CausalPreprocessor(config)
    x_train, y_train = load_features(rows, "train", data_root, processor)
    x_validation, y_validation = load_features(rows, "validation", data_root, processor)
    model = RandomForestClassifier(n_estimators=args.trees, random_state=42, class_weight="balanced_subsample", min_samples_leaf=2, n_jobs=-1)
    model.fit(x_train, y_train)
    metrics = {
        "evaluation": "grouped recording/center-window proxy; internal baseline only",
        "validation_classification": classification_metrics(y_validation, model.predict(x_validation)),
        "locked_test": {"status": "not_evaluated", "reason": "not read during baseline selection"},
        "unavailable": unavailable_event_metrics(),
    }
    fingerprint = manifest_sha256(args.manifest)
    joblib.dump({"artifact_type": "srasta_rf_baseline_v1", "model": model, "window_length": 250, "feature_names": FEATURE_NAMES, "capture_profile_hash": profile.hash, "preprocess_config_hash": config.hash, "manifest_sha256": fingerprint}, args.out_dir / "model.joblib")
    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (args.out_dir / "preprocess_config.json").write_text(json.dumps(config.to_json(), indent=2) + "\n")
    (args.out_dir / "capture_profile.json").write_text(json.dumps(profile.to_json(), indent=2) + "\n")
    report = split_report(rows)
    report["manifest_sha256"] = fingerprint
    (args.out_dir / "split_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / "MODEL_CARD.md").write_text("# Random Forest baseline\n\nInternal transparent BE+AI sanity baseline; not the submission, deployment, or clinical artifact. Train and validation only; locked test was not read.\n")
    print(json.dumps({"out_dir": str(args.out_dir), "validation": metrics["validation_classification"]}, indent=2))


if __name__ == "__main__":
    main()

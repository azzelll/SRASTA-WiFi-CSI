#!/usr/bin/env python3
"""Train, validate, and export the grouped SRASTA TCN-Lite engineering candidate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from srasta_csi.contract import CaptureProfile
from srasta_csi.data import ManifestRow, manifest_sha256, read_h5_amplitude, read_manifest, resolve_source_path, split_report, timestamps
from srasta_csi.metrics import classification_metrics, unavailable_event_metrics
from srasta_csi.model import TFLiteModel, build_tcn_lite, export_full_int8, parity_report
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


def load_windows(rows: list[ManifestRow], split: str, data_root: Path, processor: CausalPreprocessor, length: int) -> tuple[np.ndarray, np.ndarray]:
    windows, labels = [], []
    for row in rows:
        if row.split != split:
            continue
        values = read_h5_amplitude(resolve_source_path(row, data_root))
        window, _ = processor.window(values, timestamps(len(values)), length, centered=True)
        windows.append(window)
        labels.append(row.label_id)
    if not windows:
        raise ValueError(f"no {split} rows")
    return np.stack(windows).astype(np.float32), np.asarray(labels, dtype=np.int64)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/srasta_tcn_lite"))
    parser.add_argument("--window-length", type=int, default=250)
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.window_length <= 0 or args.epochs <= 0 or args.batch_size <= 0:
        raise ValueError("window length, epochs, and batch size must be positive")
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite {args.out_dir}")

    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    import tensorflow as tf

    tf.keras.utils.set_random_seed(args.seed)
    rows = read_manifest(args.manifest)
    data_root = args.data_root.resolve()
    expected_manifest = data_root / "curated/esp32_s3_fall_v1/manifest.csv"
    if args.manifest.resolve() != expected_manifest.resolve():
        raise ValueError("TCN-Lite training only accepts esp32_s3_fall_v1/manifest.csv")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    profile = CaptureProfile()
    config = PreprocessConfig(capture_profile_hash=profile.hash)
    processor = CausalPreprocessor(config)
    x_train, y_train = load_windows(rows, "train", data_root, processor, args.window_length)
    x_validation, y_validation = load_windows(rows, "validation", data_root, processor, args.window_length)

    model = build_tcn_lite(args.window_length, args.seed)
    counts = np.bincount(y_train, minlength=2)
    if np.any(counts == 0):
        raise ValueError("TCN training split must contain both classes")
    class_weight = {index: float(len(y_train) / (2 * count)) for index, count in enumerate(counts)}
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    checkpoint = args.out_dir / "checkpoint.weights.h5"
    history = model.fit(
        x_train, y_train,
        validation_data=(x_validation, y_validation),
        epochs=args.epochs,
        batch_size=args.batch_size,
        shuffle=True,
        class_weight=class_weight,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True),
            tf.keras.callbacks.ModelCheckpoint(checkpoint, monitor="val_loss", save_best_only=True, save_weights_only=True),
        ],
        verbose=2,
    )
    model_path = args.out_dir / "model.keras"
    model.save(model_path)
    representative_count = min(len(x_train), 128)
    tflite_path = export_full_int8(model, x_train[:representative_count], args.out_dir / "model.tflite")
    runtime = TFLiteModel(tflite_path)
    parity = parity_report(model, runtime, x_validation)
    (args.out_dir / "parity.json").write_text(json.dumps(parity, indent=2) + "\n")

    predictions = np.asarray([np.argmax(runtime.predict(window)) for window in x_validation], dtype=np.int64)
    classification = classification_metrics(y_validation, predictions)
    model_size_bytes = tflite_path.stat().st_size
    gates = {
        "fall_recall_at_least_0_88": classification["recall"]["fall"] >= 0.88,
        "nonfall_specificity_at_least_0_80": classification["recall"]["nonfall"] >= 0.80,
        "model_at_most_1_mb": model_size_bytes <= 1_000_000,
        "inference_at_most_100_ms_per_window": parity["mean_tflite_inference_ms"] <= 100.0,
        "int8_parity": parity["status"] == "passed",
        "event_and_false_alert_evidence_available": False,
    }
    metrics = {
        "evaluation": "grouped subject/session-disjoint validation; one centered window per recording",
        "validation_classification": classification,
        "parity": parity,
        "model_size_bytes": model_size_bytes,
        "deployment_status": "deployment_ready" if all(gates.values()) else "not_deployment_ready",
        "deployment_gate": gates,
        "locked_test": {"status": "not_evaluated", "reason": "held out until model and thresholds are explicitly frozen"},
        "unavailable": unavailable_event_metrics(),
    }
    training = {
        "seed": args.seed,
        "epochs_requested": args.epochs,
        "epochs_completed": len(history.history["loss"]),
        "batch_size": args.batch_size,
        "window_length": args.window_length,
        "architecture": {"channels": 24, "kernel": 3, "dilations": [1, 2, 4], "pooling": "global_average", "classes": 2},
        "representative_dataset": "curated ESP32-S3 train split only",
        "representative_window_count": representative_count,
        "manifest_sha256": manifest_sha256(args.manifest),
    }
    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (args.out_dir / "training_config.json").write_text(json.dumps(training, indent=2) + "\n")
    (args.out_dir / "preprocess_config.json").write_text(json.dumps(config.to_json(), indent=2) + "\n")
    (args.out_dir / "capture_profile.json").write_text(json.dumps(profile.to_json(), indent=2) + "\n")
    report = split_report(rows)
    report["manifest_sha256"] = training["manifest_sha256"]
    (args.out_dir / "split_report.json").write_text(json.dumps(report, indent=2) + "\n")
    failed = [name for name, passed in gates.items() if not passed]
    (args.out_dir / "MODEL_CARD.md").write_text(
        "# SRASTA TCN-Lite engineering candidate\n\n"
        "Two-class grouped CSI fall-path candidate. This does not narrow the proposal's four-output/multi-purpose product requirement.\n\n"
        f"Deployment status: **{metrics['deployment_status']}**. Failed or unavailable gates: {', '.join(failed) or 'none'}. "
        "The locked test was not read. Event/FAR validation requires continuous annotated ESP32-S3 captures.\n"
    )
    print(json.dumps({"out_dir": str(args.out_dir), "validation": classification, "parity": parity, "deployment_status": metrics["deployment_status"]}, indent=2))


if __name__ == "__main__":
    main()

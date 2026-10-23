#!/usr/bin/env python3
"""Seven-class ESP-Fi encoder with grouped source-train validation and INT8."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from sklearn.metrics import classification_report, confusion_matrix

from srasta_csi.data import timestamps
from srasta_csi.model import export_full_int8, parity_report, TFLiteModel
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig
from train_srasta_release import build, crop, save


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=45)
    p.add_argument("--normalization-mode", choices=("relative", "log_difference"), default="relative")
    p.add_argument("--hampel-history", choices=("filtered", "raw"), default="filtered")
    args = p.parse_args()
    if args.epochs < 1:
        p.error("epochs must be positive")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    import tensorflow as tf
    tf.keras.utils.set_random_seed(42)
    manifest = args.data_root / "external/esp_fi_har/manifest.csv"
    with manifest.open() as f:
        rows = [r for r in csv.DictReader(f) if r["source_partition"] == "train" and r["pretraining_train_eligible"] == "yes" and r["main_test_eligible"] == "no"]
    train_rows = [r for r in rows if r["subject_id"] != "8"]
    validation_rows = [r for r in rows if r["subject_id"] == "8"]
    actions = sorted({r["action"] for r in train_rows})
    if len(actions) != 7 or {r["action"] for r in validation_rows} != set(actions):
        raise ValueError("seven labels must occur in both grouped source partitions")
    # The public amplitude corpus does not establish a raw LLTF capture hash.
    config = PreprocessConfig(capture_profile_hash="", normalized_clip=2., normalization_mode=args.normalization_mode, hampel_history=args.hampel_history)
    processor = CausalPreprocessor(config)
    protocol = {"source": "ESP-Fi HAR; Wen et al. (2026), CC BY 4.0", "hardware": "ESP32-C3; different capture domain", "role": "research encoder pretraining; not live SRASTA classifier", "source_test_opened": False, "train_subjects": sorted({r["subject_id"] for r in train_rows}), "validation_subjects": ["8"], "classes": actions, "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(), "timestamps": "nominal 100 Hz; no actual packet timing", "crop": "centered measured 500 frames", "selection": "source validation loss, early stopping; representative quantization source-train only", "SRASTA_performance_claim": False, "preprocess": config.to_json()}
    save(args.out_dir / "protocol.json", protocol)
    save(args.out_dir / "selected_metadata.json", {"train": train_rows, "validation": validation_rows})
    def load(selected):
        xs = []
        for row in selected:
            source = (args.data_root.parent / row["source_path"]).resolve()
            if not source.is_relative_to((args.data_root / "external/esp_fi_har").resolve()):
                raise ValueError("source path escaped corpus")
            amplitude = np.asarray(loadmat(source)["CSIamp"], dtype=np.float32)
            if amplitude.shape != (950, 52):
                raise ValueError("expected native [950,52] amplitude")
            xs.append(processor.transform(amplitude, timestamps(950)))
        return crop(np.stack(xs), 500), np.asarray([actions.index(r["action"]) for r in selected])
    x, y = load(train_rows)
    xv, yv = load(validation_rows)
    spec = {"name": "motion_tcn_500", "length": 500, "channels": 24, "kernel": 5, "dilations": [1, 2, 4, 8, 16], "dropout": .1, "l2": 1e-4}
    model = build(spec, x, 42, classes=7)
    model.compile(optimizer=tf.keras.optimizers.Adam(3e-4, clipnorm=1), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    history = model.fit(x, y, validation_data=(xv, yv), epochs=args.epochs, batch_size=16, callbacks=[tf.keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True), tf.keras.callbacks.ReduceLROnPlateau(patience=4, factor=.5, min_lr=1e-5)], verbose=2)
    model.save(args.out_dir / "model.keras")
    save(args.out_dir / "history.json", history.history)
    representative_indices = np.random.default_rng(42).choice(len(x), min(256, len(x)), replace=False)
    if set(y[representative_indices]) != set(range(7)):
        raise ValueError("INT8 representative set must contain all source activities")
    export_full_int8(model, x[representative_indices], args.out_dir / "model.tflite")
    save(args.out_dir / "quantization_provenance.json", {"source_partition": "train", "sample_ids": [train_rows[i]["sample_id"] for i in representative_indices], "classes": actions, "source_validation_used": False})
    runtime = TFLiteModel(args.out_dir / "model.tflite")
    parity = parity_report(model, runtime, xv)
    predictions = np.argmax(np.stack([runtime.predict(v) for v in xv]), axis=1)
    report = {"classes": actions, "classification": classification_report(yv, predictions, labels=list(range(7)), target_names=actions, output_dict=True, zero_division=0), "confusion_matrix": confusion_matrix(yv, predictions, labels=list(range(7))).tolist(), "parity": parity, "train_recordings": len(x), "validation_recordings": len(xv), "model_size_bytes": (args.out_dir / "model.tflite").stat().st_size, "ESP32_S3_validated": False, "source_test_opened": False}
    save(args.out_dir / "metrics.json", report)
    save(args.out_dir / "preprocess_config.json", config.to_json())
    save(args.out_dir / "training_config.json", {"classes": actions, "window_length": 500, "research_only": True, "architecture": spec})
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

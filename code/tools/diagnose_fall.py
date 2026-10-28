#!/usr/bin/env python3
"""Reproduce selected INT8 recording decisions on train/development only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srasta_csi.data import manifest_sha256, timestamps
from srasta_csi.development import load_development
from srasta_csi.fall_diagnostics import preprocess_trace, recording_decision, quantization_saturation
from srasta_csi.metrics import classification_metrics, unavailable_event_metrics
from srasta_csi.model import TFLiteModel
from srasta_csi.preprocess import PreprocessConfig


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def plot_example(path, trace, record):
    # SVG stays local alongside derived diagnostics; no plotting dependency.
    series = [trace["held"].mean(axis=1), trace["processed"].mean(axis=1),
              np.mean(np.diff(trace["processed"], axis=0) ** 2, axis=1)]
    labels = ["Raw mean amplitude", "Preprocessed mean", "Derivative energy (not annotated onset)"]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="600" viewBox="0 0 900 600">',
             '<rect width="900" height="600" fill="white"/>',
             f'<text x="35" y="25" font-family="sans-serif" font-size="14">{record["sample_id"]} {record["outcome"]} p={record["probability"]:.3f} missed_by={record["missed_by"]}</text>']
    for i, (values, label) in enumerate(zip(series, labels)):
        low, high = float(values.min()), float(values.max())
        top = 65 + i * 175
        points = " ".join(f"{40+820*j/(len(values)-1):.1f},{top+125-120*(v-low)/max(high-low,1e-12):.1f}" for j, v in enumerate(values))
        parts += [f'<text x="40" y="{top-10}" font-family="sans-serif" font-size="12">{label}, range {low:.5g}..{high:.5g}</text>',
                  f'<path d="M40 {top} V{top+125} H860" fill="none" stroke="#bbb"/>',
                  f'<polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="1.2"/>']
    parts.append('<text x="40" y="590" font-family="sans-serif" font-size="12">Frame index 0..499; nominal 100 Hz, not packet/event latency.</text></svg>')
    path.write_text("\n".join(parts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--selected", type=Path, default=Path("artifacts/releases/20261001-tcn-v8-motion-calibrated/selected"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    config = PreprocessConfig.from_json(json.loads((args.selected / "preprocess_config.json").read_text()))
    frozen = json.loads((args.selected / "frozen.json").read_text())
    digest = hashlib.sha256((args.selected / "model.tflite").read_bytes()).hexdigest()
    if digest != frozen["model_sha256"]:
        raise ValueError("selected model hash differs from frozen metadata")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    protocol = {"model_sha256": digest, "preprocess": config.to_json(), "threshold": frozen["threshold"],
                "manifest_sha256": manifest_sha256(args.data_root / "curated/esp32_s3_fall_v1/manifest.csv"),
                "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    (Path(__file__), Path(__file__).parents[1] / "srasta_csi/fall_diagnostics.py")},
                "interpretation": {"train": "in-sample, not OOF/generalization", "validation": "historically reused U19 diagnostic, not threshold/candidate selection"},
                "test_payload_opened": False, "unavailable": unavailable_event_metrics()}
    write_json(args.out_dir / "protocol.json", protocol)
    runtime = TFLiteModel(args.selected / "model.tflite")
    records, summaries = [], {}
    for split in ("train", "validation"):
        rows, raw = load_development(args.data_root, split)
        examples = set()
        current = []
        for row, values in zip(rows, raw):
            trace = preprocess_trace(values, timestamps(len(values)), config)
            window = trace["processed"]
            probability = runtime.probability(window)
            stats = trace["stats"]
            decision = recording_decision(row.label_id, probability, stats["motion_energy"], frozen["threshold"], config.motion_energy_threshold)
            record = {"sample_id": row.sample_id, "subject": row.subject_id, "split": split,
                      "label": row.label_id, "probability": probability, **stats, **decision,
                      "int8_saturated_fraction": quantization_saturation(window, runtime.input_detail["quantization"])}
            current.append(record)
            if decision["outcome"] not in examples:
                plot_example(args.out_dir / f'{split}_{decision["outcome"]}.svg', trace, record)
                examples.add(decision["outcome"])
        summaries[split] = {"recordings": len(current), "classifier_only": classification_metrics(
            [r["label"] for r in current], [r["classifier_prediction"] for r in current]),
            "after_motion_gate": classification_metrics([r["label"] for r in current], [r["trigger_prediction"] for r in current]),
            "missed_by": {reason: sum(r["missed_by"] == reason for r in current) for reason in ("classifier", "motion_gate", "classifier_and_motion_gate")},
            "median_hampel_replaced_fraction": float(np.median([r["hampel_replaced_fraction"] for r in current])),
            "median_int8_saturated_fraction": float(np.median([r["int8_saturated_fraction"] for r in current])),
            "per_subject": {s: classification_metrics([r["label"] for r in current if r["subject"] == s],
                              [r["trigger_prediction"] for r in current if r["subject"] == s]) for s in sorted({r["subject"] for r in current})}}
        records.extend(current)
    with (args.out_dir / "baseline_predictions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    write_json(args.out_dir / "report.json", {**protocol, "splits": summaries})
    print(json.dumps({"output": str(args.out_dir), "splits": summaries}, indent=2))


if __name__ == "__main__":
    main()

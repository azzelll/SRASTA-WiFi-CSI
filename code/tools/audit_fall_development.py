#!/usr/bin/env python3
"""Audit unmodified primary train/validation files; never inspect test payloads."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srasta_csi.data import read_manifest, resolve_source_path, manifest_sha256
from srasta_csi.decoder import USABLE_SUBCARRIER_INDICES
from srasta_csi.development import PIPELINES, prepare_windows, pipeline_config
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    manifest = args.data_root / "curated/esp32_s3_fall_v1/manifest.csv"
    selected = [r for r in read_manifest(manifest) if r.split in ("train", "validation")]
    with (args.data_root / "csi-bench/FallDetection/metadata/sample_metadata.csv").open() as stream:
        metadata = {str(Path(r["file_path"])): r for r in csv.DictReader(stream) if r["device"] == "ESP32"}
    duplicates = defaultdict(list)
    records, arrays = [], []
    unused = sorted(set(range(64)) - set(USABLE_SUBCARRIER_INDICES))
    for row in selected:
        path = resolve_source_path(row, args.data_root)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        with h5py.File(path) as handle:
            x = np.asarray(handle["CSI_amps"], dtype=np.float32)
            keys = list(handle.keys())
            attrs = sorted(handle.attrs.keys())
        if x.shape != (64, 500, 1) or not np.isfinite(x).all() or (x < 0).any():
            raise ValueError(f"bad raw amplitude recording: {row.sample_id}")
        source_meta = metadata.get(str(Path(row.source_path.removeprefix("csi-bench/FallDetection/"))))
        matched = bool(source_meta and source_meta["user"] == row.subject_id
                       and source_meta["session"] == row.session_id
                       and source_meta["label"].lower().replace("_", "") == row.label)
        values = x[:, :, 0].T[:, USABLE_SUBCARRIER_INDICES]
        digest = hashlib.sha256(x.tobytes()).hexdigest()
        duplicates[digest].append({"id": row.sample_id, "label": row.label, "split": row.split})
        arrays.append(values)
        e = np.mean(np.diff(values, axis=0) ** 2, axis=1)
        peak = int(e.argmax())
        records.append({"id": row.sample_id, "split": row.split, "subject": row.subject_id,
                        "label": row.label, "file_sha256": file_hash, "amplitude_sha256": digest,
                        "metadata_matches": matched, "unused_nonzero": int(np.count_nonzero(x[unused])),
                        "dead_selected_carriers": int(np.count_nonzero(np.max(values, axis=0) == 0)),
                        "flat_selected_carriers": int(np.count_nonzero(np.std(values, axis=0) == 0)),
                        "zero_fraction": float((values == 0).mean()), "raw_mean": float(values.mean()),
                        "raw_std": float(values.std()), "raw_derivative_energy": float(e.mean()),
                        "derivative_peak_frame": peak, "peak_inside_center_250": 125 <= peak < 374,
                        "actual_clock_available": any("time" in k.lower() for k in keys + attrs),
                        "keys": keys, "environment": source_meta["environment"] if source_meta else None,
                        "source_difficulty": source_meta["Difficulty"] if source_meta else None})
    raw = np.stack(arrays)
    preprocess_summary = {}
    for name in PIPELINES:
        prepared = prepare_windows(raw, name)
        derivatives = np.diff(prepared, axis=1)
        cfg = pipeline_config(name)
        if name.startswith("causal"):
            processor = CausalPreprocessor(PreprocessConfig.from_json(cfg["shared_preprocess_config"]))
            replaced = [float(np.mean(processor._hampel(v) != v)) for v in raw]
        else:
            replaced = [0.] * len(raw)
        details = []
        for i, row in enumerate(records):
            v = prepared[i]
            details.append({"id": row["id"], "label": row["label"], "split": row["split"],
                            "hampel_replaced_fraction": replaced[i],
                            "normalized_std": float(v.std()),
                            "normalized_derivative_energy": float(np.mean(derivatives[i] ** 2)),
                            "clip_fraction": float(np.mean(np.abs(v) >= 2.)) if name.startswith("causal") else None})
        preprocess_summary[name] = {"config": cfg, "records": details,
                                    "median_hampel_replaced_fraction": float(np.median(replaced)),
                                    "median_derivative_energy": float(np.median([r["normalized_derivative_energy"] for r in details]))}
    dup_groups = [v for v in duplicates.values() if len(v) > 1]
    summary = {"test_payload_opened": False, "excluded_payload_opened": False,
               "records": len(records), "split_counts": dict(Counter(r["split"] for r in records)),
               "subject_class_counts": {s: dict(Counter(r["label"] for r in records if r["subject"] == s)) for s in sorted({r["subject"] for r in records})},
               "shape_finite_nonnegative": "passed", "fixed_mask": "passed" if not any(r["unused_nonzero"] for r in records) else "failed",
               "metadata_mismatches": [r["id"] for r in records if not r["metadata_matches"]],
               "duplicate_groups": dup_groups,
               "conflicting_duplicate_groups": [v for v in dup_groups if len({r["label"] for r in v}) > 1],
               "cross_split_duplicate_groups": [v for v in dup_groups if len({r["split"] for r in v}) > 1],
               "dead_selected_carrier_records": sum(r["dead_selected_carriers"] > 0 for r in records),
               "actual_clock_record_count": sum(r["actual_clock_available"] for r in records),
               "center_250_contains_largest_derivative": sum(r["peak_inside_center_250"] for r in records),
               "largest_derivative_is_verified_fall_onset": False,
               "environments": dict(Counter(r["environment"] for r in records)),
               "difficulty": dict(Counter(r["source_difficulty"] for r in records)),
               "local_kaggle_version": "unknown; no supplied version attestation",
               "local_layout": "legacy top-level HumanActivityRecognition",
               "upstream_declared_version": 12,
               "version_difference_proves_payload_issue": False,
               "manifest_sha256": manifest_sha256(manifest),
               "paper": "https://arxiv.org/abs/2505.21866",
               "upstream": "https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark"}
    report = {"summary": summary, "records": records, "preprocessing": preprocess_summary}
    (args.out_dir / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    np.savez_compressed(args.out_dir / "development_windows.npz", raw=raw,
                        ids=np.asarray([r["id"] for r in records]),
                        splits=np.asarray([r["split"] for r in records]))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()

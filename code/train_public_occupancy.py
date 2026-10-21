#!/usr/bin/env python3
"""Train public sleep/empty and presence with disjoint subjects, native CSI."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from srasta_csi.native_features import FEATURE_NAMES, native_motion_features
from srasta_csi.public_occupancy import (ARTIFACT_TYPE, INVARIANT_NAMES, LAYOUTS,
                                      invariant_features, load_amplitude, select_protocol, source_rows)


def metrics(y, probability, classes):
    prediction = probability >= .5
    cm = confusion_matrix(y, prediction, labels=[0, 1])
    return {"classification": classification_report(y, prediction, labels=[0, 1], target_names=classes,
                                                     output_dict=True, zero_division=0),
            "confusion_matrix": cm.tolist(), "positive_recall": float(cm[1, 1] / cm[1].sum()),
            "empty_recall_specificity": float(cm[0, 0] / cm[0].sum()),
            "balanced_accuracy": float((cm[1, 1] / cm[1].sum() + cm[0, 0] / cm[0].sum()) / 2),
            "roc_auc": float(roc_auc_score(y, probability))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/csi-bench"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--cap-per-stratum", type=int, default=2000)
    args = parser.parse_args()
    selected = select_protocol(args.source, args.cap_per_stratum)
    args.out_dir.mkdir(parents=True, exist_ok=False)

    def save(name, data):
        (args.out_dir / name).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")

    allowed = {task: source_rows(args.source, task)[1] for task in ("BreathingDetection", "HumanActivityRecognition")}
    protocol = {"classes": {"breathing": ["empty", "sleep"], "presence": ["empty", "present"]},
                "mapping": {"empty": "empty", "sleep": "present", "HAR_human_activity": "present"},
                "subject_split": {split: sorted({r["user"] for rs in part.values() for r in rs}) for split, part in selected.items()},
                "selection": "round-robin native device/placement/label strata; metadata only; source-train IDs only",
                "validation": "custom cross-user and cross-environment development validation; previously inspected subjects",
                "official_validation_test_payloads_opened": False, "local_capture_payloads_opened": False,
                "candidate_selection": "validation min class recall, balanced accuracy, macro F1; threshold fixed 0.5; seed 42 fixed",
                "layouts": {"declared_axes": "transpose original [channels,time,1] as in previous baseline",
                            "flat_time_major_ablation": "reconstruct original time-major flattened native channels; layout hypothesis, not author-verified"},
                "model_candidates": ["legacy RF", "invariant RF", "invariant RBF SVM"],
                "limitations": ["no awake-vs-sleep classifier", "no local ESP32 accuracy", "class/corpus and device confounding remains",
                                "nominal sample rates, no raw packet clocks", "two breathing subjects with both labels only", "no independent final test score"],
                "local_deployment_ready": False, "research_only": True}
    protocol["source_index_hashes"] = {str(path.relative_to(args.source)): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for task in allowed for path in (args.source / task / "metadata/sample_metadata.csv", args.source / task / "splits/train_id.json")}
    save("protocol.json", protocol)
    save("selected_metadata.json", selected)
    arrays = {}
    hashes = {}
    layout_audit = []
    excluded = []
    for split, part in selected.items():
        arrays[split] = {}
        for stratum, rows in part.items():
            features = {(layout, kind): [] for layout in LAYOUTS for kind in ("legacy", "invariant")}
            eligible = []
            for index, row in enumerate(rows):
                path = args.source / row["task"] / row["file_path"]
                hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                measured = {layout: load_amplitude(args.source, row, allowed[row["task"]], layout) for layout in LAYOUTS}
                if not np.any(measured["declared_axes"][0]):
                    excluded.append({"id": row["id"], "task": row["task"], "split": split,
                                     "stratum": stratum, "reason": "all-zero recording; no measured signal"})
                    continue
                for layout in LAYOUTS:
                    values, rate = measured[layout]
                    features[layout, "legacy"].append(native_motion_features(values, rate))
                    features[layout, "invariant"].append(invariant_features(values, rate))
                    if index < 3:
                        layout_audit.append({"id": row["id"], "task": row["task"], "stratum": stratum, "layout": layout,
                                             "native_shape": list(values.shape), "fixed_zero_carriers": np.flatnonzero(np.all(values == 0, axis=0)).tolist(),
                                             "median_cv": float(np.median(values.std(axis=0) / np.maximum(values.mean(axis=0), 1e-9)))})
                eligible.append(row)
                if (index + 1) % 500 == 0:
                    print(f"Features {split}/{stratum}: {index + 1}/{len(rows)}", flush=True)
            if not eligible:
                raise ValueError(f"no usable recordings in {split}/{stratum}")
            selected[split][stratum] = eligible
            arrays[split][stratum] = {k: np.stack(v) for k, v in features.items()}
    save("layout_audit.json", layout_audit)
    save("excluded_recordings.json", excluded)
    save("eligible_metadata.json", selected)
    protocol["signal_quality_exclusion"] = "all-zero recordings excluded in each partition before fitting; IDs and original labels retained in excluded_recordings.json"
    protocol["excluded_recordings"] = len(excluded)
    save("protocol.json", protocol)
    duplicate_hashes = set(hashes[str(args.source / r["task"] / r["file_path"])] for rs in selected["train"].values() for r in rs) & set(
        hashes[str(args.source / r["task"] / r["file_path"])] for rs in selected["validation"].values() for r in rs)
    if duplicate_hashes:
        raise ValueError("exact duplicate recordings across development partitions")
    source_integrity = {"selected_payload_sha256": hashes, "cross_partition_byte_duplicates": 0}
    save("source_integrity_before.json", source_integrity)
    all_results = {}
    for task, classes in protocol["classes"].items():
        task_out = args.out_dir / task
        task_out.mkdir()
        strata = ["empty", "sleep"] + (["awake"] if task == "presence" else [])
        trials = []
        for layout in LAYOUTS:
            for kind, family in (("legacy", "rf"), ("invariant", "rf"), ("invariant", "svm")):
                xy = {}
                for split in selected:
                    x = np.concatenate([arrays[split][stratum][layout, kind] for stratum in strata])
                    y = np.concatenate([np.full(len(selected[split][stratum]), int(stratum != "empty")) for stratum in strata])
                    xy[split] = x, y
                if family == "rf":
                    model = RandomForestClassifier(n_estimators=300, min_samples_leaf=5, max_features="sqrt", class_weight="balanced", random_state=42, n_jobs=2)
                else:
                    model = make_pipeline(StandardScaler(), SVC(C=1., kernel="rbf", gamma="scale", class_weight="balanced", probability=True, random_state=42))
                started = time.perf_counter()
                model.fit(*xy["train"])
                x, y = xy["validation"]
                probability = model.predict_proba(x)[:, 1]
                result = {"layout": layout, "features": kind, "family": family, "metrics": metrics(y, probability, classes),
                          "fit_and_evaluate_s": time.perf_counter() - started,
                          "stratum_positive_prediction_rate": {s: float((model.predict_proba(arrays["validation"][s][layout, kind])[:, 1] >= .5).mean()) for s in strata}}
                name = f"{layout}-{kind}-{family}"
                result["candidate"] = name
                result["predictions_file"] = name + "-predictions.npz"
                np.savez_compressed(task_out / result["predictions_file"], y=y, positive_probability=probability)
                payload = {"artifact_type": ARTIFACT_TYPE, "task": task, "model": model, "classes": classes,
                           "layout": layout, "features": kind, "feature_names": FEATURE_NAMES if kind == "legacy" else INVARIANT_NAMES,
                           "research_only": True, "local_deployment_ready": False, "protocol": protocol}
                joblib.dump(payload, task_out / (name + ".joblib"), compress=3)
                trials.append(result)
                print(task, name, json.dumps(result["metrics"]["confusion_matrix"]),
                      f"balanced={result['metrics']['balanced_accuracy']:.3f}", flush=True)
        def score(r):
            m = r["metrics"]
            return min(m["positive_recall"], m["empty_recall_specificity"]), m["balanced_accuracy"], m["classification"]["macro avg"]["f1-score"]
        best = max(trials, key=score)
        chosen = joblib.load(task_out / (best["candidate"] + ".joblib"))
        joblib.dump(chosen, task_out / "model.joblib", compress=3)
        all_results[task] = {"selected": best, "candidates": trials,
                             "counts": {split: {s: len(selected[split][s]) for s in strata} for split in selected},
                             "model_sha256": hashlib.sha256((task_out / "model.joblib").read_bytes()).hexdigest(),
                             "local_deployment_ready": False, "normal_class_ready": False}
    changed = [path for path, before in hashes.items() if hashlib.sha256(Path(path).read_bytes()).hexdigest() != before]
    if changed:
        raise ValueError("source payload changed during training")
    save("source_integrity_after.json", {"checked_payloads": len(hashes), "changed_payloads": changed})
    save("metrics.json", all_results)
    print(json.dumps({task: r["selected"] for task, r in all_results.items()}, indent=2), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Bounded primary-only fall development with subject-held-out calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "4")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "2")

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from srasta_csi.data import manifest_sha256
from srasta_csi.development import (PIPELINES, DEVELOPMENT_FEATURE_NAMES,
    load_development, prepare_windows, pipeline_config, development_features,
    grouped_folds, select_threshold)
from srasta_csi.metrics import classification_metrics, unavailable_event_metrics
from srasta_csi.model import TFLiteModel, export_full_int8, parity_report
from train_srasta_release import build

SEEDS = (42, 43, 44)
TCN_PIPELINES = ("causal_filtered", "paper_window_zscore")
TCN_SPEC = {"name": "grouped_tcn_500", "length": 500, "channels": 24,
            "kernel": 3, "dilations": [1, 2, 4, 8, 16], "l2": 1e-4, "dropout": .1}


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def classifier(family, seed):
    if family == "rf":
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
            max_features="sqrt", class_weight="balanced_subsample", random_state=seed, n_jobs=2)
    if family == "svm":
        # The scaler and Platt fit see ONLY the four fitting subjects.
        return make_pipeline(StandardScaler(), SVC(C=1., gamma="scale", kernel="rbf",
            class_weight="balanced", probability=True, random_state=seed))
    raise ValueError("unknown baseline family")


def fit_tcn(x, y, seed, epochs, calibration=None):
    import tensorflow as tf
    tf.keras.backend.clear_session()
    model = build(TCN_SPEC, x, seed)
    model.compile(optimizer=tf.keras.optimizers.Adam(3e-4, clipnorm=1.),
                  loss="sparse_categorical_crossentropy")
    counts = np.bincount(y, minlength=2)
    if (counts == 0).any():
        raise ValueError("fit subjects must include both classes")
    kwargs = {"epochs": epochs, "batch_size": 16, "verbose": 0,
              "class_weight": {i: float(len(y)/(2*counts[i])) for i in (0, 1)}}
    if calibration is not None:
        kwargs.update(validation_data=calibration,
                      callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=6,
                                  restore_best_weights=True)])
    history = model.fit(x, y, **kwargs)
    best_epoch = int(np.argmin(history.history["val_loss"]) + 1) if calibration else epochs
    return model, history.history, best_epoch


def summary(runs):
    recall = np.array([r["outer_classification"]["recall"]["fall"] for r in runs])
    specificity = np.array([r["outer_classification"]["recall"]["nonfall"] for r in runs])
    f1 = np.array([r["outer_classification"]["macro_f1"] for r in runs])
    return {"recall_mean": float(recall.mean()), "recall_std": float(recall.std()),
            "specificity_mean": float(specificity.mean()), "specificity_std": float(specificity.std()),
            "macro_f1_mean": float(f1.mean()), "joint_80_mean_pass": bool(recall.mean() >= .8 and specificity.mean() >= .8),
            "all_seeds_joint_80_pass": bool(((recall >= .8) & (specificity >= .8)).all())}


def evaluate_candidate(rows, x, family, name, epochs, path):
    y = np.asarray([r.label_id for r in rows]); groups = np.asarray([r.subject_id for r in rows])
    seeds = []
    for seed in SEEDS:
        probabilities = np.full(len(rows), np.nan)
        predictions = np.full(len(rows), -1, dtype=np.int64)
        folds = []
        for fold in grouped_folds(groups):
            started = time.perf_counter()
            fit, cal, ev = (fold[k] for k in ("fit", "calibrate", "evaluate"))
            if family == "tcn":
                model, history, best_epoch = fit_tcn(x[fit], y[fit], seed, epochs, (x[cal], y[cal]))
                p_cal = model.predict(x[cal], verbose=0)[:, 1]
                p_eval = model.predict(x[ev], verbose=0)[:, 1]
            else:
                model = classifier(family, seed).fit(x[fit], y[fit])
                p_cal = model.predict_proba(x[cal])[:, 1]
                p_eval = model.predict_proba(x[ev])[:, 1]
                history, best_epoch = None, None
            threshold = select_threshold(y[cal], p_cal)
            probabilities[ev] = p_eval
            predictions[ev] = (p_eval >= threshold["threshold"]).astype(np.int64)
            entry = {"held_out_subject": fold["held_out_subject"],
                     "calibration_subject": fold["calibration_subject"],
                     "fit_subjects": fold["fit_subjects"],
                     "fit_ids": [rows[i].sample_id for i in fit],
                     "calibration_ids": [rows[i].sample_id for i in cal],
                     "evaluation_ids": [rows[i].sample_id for i in ev],
                     "threshold_selected_on_calibration_only": threshold,
                     "outer_classification": classification_metrics(y[ev], predictions[ev]),
                     "epochs_best": best_epoch, "history": history,
                     "elapsed_s": time.perf_counter() - started}
            folds.append(entry)
            print(f'{family}/{name} seed={seed} held_out={fold["held_out_subject"]} '
                  f'recall={entry["outer_classification"]["recall"]["fall"]:.3f} '
                  f'specificity={entry["outer_classification"]["recall"]["nonfall"]:.3f} '
                  f'sec={entry["elapsed_s"]:.1f}', flush=True)
            # Preserve bounded work even if a later fit is interrupted.
            save(path / f"progress_seed_{seed}.json", {"completed_folds": folds})
        if not np.isfinite(probabilities).all() or (predictions < 0).any():
            raise ValueError("incomplete outer-fold coverage")
        oof_threshold = select_threshold(y, probabilities)
        seeds.append({"seed": seed, "folds": folds,
                      "outer_classification": classification_metrics(y, predictions),
                      "outer_auc": float(roc_auc_score(y, probabilities)),
                      "global_oof_threshold": oof_threshold,
                      "global_oof_threshold_is_development_tuned": True,
                      "predictions": [{"id": r.sample_id, "label": r.label_id,
                          "probability": float(p), "calibration_threshold_prediction": int(d)}
                          for r, p, d in zip(rows, probabilities, predictions)]})
        save(path / f"seed_{seed}.json", seeds[-1])
    result = {"family": family, "pipeline": name, "config": pipeline_config(name),
              "seed_runs": seeds, "summary": summary(seeds),
              "test_payload_opened": False, "source_validation_used_for_fitting": False}
    save(path / "result.json", result)
    print(json.dumps({"family": family, "pipeline": name, "summary": result["summary"]}), flush=True)
    return result


def candidate_score(candidate):
    metrics = candidate["summary"]
    return (metrics["joint_80_mean_pass"], min(metrics["recall_mean"], metrics["specificity_mean"]),
            metrics["macro_f1_mean"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("baseline", "tcn", "final"), required=True)
    parser.add_argument("--epochs", type=int, default=35)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("epochs must be positive")
    manifest = args.data_root / "curated/esp32_s3_fall_v1/manifest.csv"
    fingerprint = manifest_sha256(manifest)
    protocol = {"manifest_sha256": fingerprint, "seeds": list(SEEDS), "targets": {"recall": .8, "specificity": .8},
                "epochs_max": args.epochs, "tcn_spec": TCN_SPEC, "tcn_pipelines": list(TCN_PIPELINES),
                "baseline_pipelines": list(PIPELINES), "baseline_families": ["rf", "svm"],
                "outer_split": "leave one primary train subject out; six folds",
                "calibration": "next subject in sorted cyclic order; excluded from fitting and outer evaluation",
                "candidate_selection": "mean nested-threshold outer metrics over three seeds; joint gates, min recall/specificity, macro F1",
                "final_seed": 42, "final_threshold": "global train OOF only; no U19 threshold search",
                "final_tcn_epochs": "median best inner-calibration epoch from seed42 outer folds",
                "source_validation_status": "U19 historically reused; development check, not independent test",
                "test_payload_opened": False, "external_data_used": False,
                "evaluation_unit": "one full measured 500-frame recording, not fall events",
                "source_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "source_files_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                    for name in ("train_srasta_release.py", "srasta_csi/development.py", "srasta_csi/baseline.py",
                                 "srasta_csi/preprocess.py", "srasta_csi/model.py", "srasta_csi/data.py")},
                "versions": {name: version(name) for name in ("numpy", "tensorflow", "scikit-learn", "h5py")},
                "paper": "https://arxiv.org/abs/2505.21866"}
    if args.stage == "baseline":
        args.out_dir.mkdir(parents=True, exist_ok=False)
        save(args.out_dir / "protocol.json", protocol)
    else:
        prior = json.loads((args.out_dir / "protocol.json").read_text())
        if prior != protocol:
            raise ValueError("protocol/code/dataset changed after preregistration")
    rows, raw = load_development(args.data_root, "train")
    expected = {"U08", "U09", "U11", "U12", "U17", "U18"}
    if len(rows) != 288 or {r.subject_id for r in rows} != expected:
        raise ValueError("unexpected primary train cohort")
    y = np.asarray([r.label_id for r in rows])
    if args.stage in ("baseline", "tcn"):
        pipelines = PIPELINES if args.stage == "baseline" else TCN_PIPELINES
        families = ("rf", "svm") if args.stage == "baseline" else ("tcn",)
        for name in pipelines:
            windows = prepare_windows(raw, name)
            for family in families:
                path = args.out_dir / f"{family}_{name}"
                if (path / "result.json").exists():
                    print(f"Already complete: {path.name}", flush=True)
                    continue
                path.mkdir(exist_ok=True)
                x = windows if family == "tcn" else np.stack([development_features(v) for v in windows])
                evaluate_candidate(rows, x, family, name, args.epochs, path)
        return
    if (args.out_dir / "final_report.json").exists():
        raise FileExistsError("final validation already recorded; no adaptive rerun")
    all_results = [json.loads(p.read_text()) for p in sorted(args.out_dir.glob("*/result.json"))]
    chosen = {family: max((r for r in all_results if r["family"] == family), key=candidate_score)
              for family in ("rf", "svm", "tcn")}
    save(args.out_dir / "selection_before_validation.json", {
        "selected": {k: {"pipeline": v["pipeline"], "summary": v["summary"]} for k, v in chosen.items()},
        "rule": protocol["candidate_selection"], "final_phase_validation_loaded_at_selection": False,
        "source_validation_used_for_candidate_selection": False,
        "prior_validation_audit_or_historical_use": "U19 previously inspected; this is development validation",
        "test_payload_opened": False})
    fitted = {}
    # Freeze all three family choices, weights, thresholds, and epochs before
    # loading U19 payloads. U19 does not pick a winner or alter an artifact.
    for family, result in chosen.items():
        name = result["pipeline"]
        windows = prepare_windows(raw, name)
        run = next(r for r in result["seed_runs"] if r["seed"] == 42)
        threshold = run["global_oof_threshold"]["threshold"]
        path = args.out_dir / f"final_{family}"
        path.mkdir(exist_ok=False)
        if family == "tcn":
            epochs = max(1, int(np.median([f["epochs_best"] for f in run["folds"]])))
            model, history, _ = fit_tcn(windows, y, 42, epochs)
            model.save(path / "model.keras")
            indices = np.random.default_rng(42).choice(len(rows), 256, replace=False)
            export_full_int8(model, windows[indices], path / "model.tflite")
            digest = hashlib.sha256((path / "model.tflite").read_bytes()).hexdigest()
            save(path / "history.json", history)
            save(path / "quantization_provenance.json", {"representative_split": "primary train only",
                 "ids": [rows[i].sample_id for i in indices], "seed": 42})
        else:
            epochs = None
            features = np.stack([development_features(v) for v in windows])
            model = classifier(family, 42).fit(features, y)
            joblib.dump({"artifact_type": "srasta_fall_grouped_research_v1", "research_only": True,
                         "model": model, "pipeline": pipeline_config(name),
                         "feature_names": DEVELOPMENT_FEATURE_NAMES, "threshold": threshold}, path / "model.joblib")
            digest = hashlib.sha256((path / "model.joblib").read_bytes()).hexdigest()
        training = {"research_only": True, "classes": ["nonfall", "fall"], "window_length": 500,
                    "pipeline": pipeline_config(name), "seed": 42, "epochs": epochs,
                    "threshold": threshold, "threshold_selected_on": "train out-of-fold predictions only",
                    "model_sha256": digest, "manifest_sha256": fingerprint,
                    "test_payload_opened": False, "deployment_ready": False}
        save(path / "training_config.json", training)
        save(path / "frozen.json", training)
        save(path / "research_preprocess.json", pipeline_config(name))
        fitted[family] = (model, threshold, name, path)
    validation_rows, validation_raw = load_development(args.data_root, "validation")
    val_y = np.asarray([r.label_id for r in validation_rows])
    finals = []
    for family, (model, threshold, name, path) in fitted.items():
        windows = prepare_windows(validation_raw, name)
        if family == "tcn":
            fp32 = model.predict(windows, verbose=0)[:, 1]
            runtime = TFLiteModel(path / "model.tflite")
            p = np.asarray([runtime.probability(v) for v in windows])
            parity = parity_report(model, runtime, windows)
        else:
            p = model.predict_proba(np.stack([development_features(v) for v in windows]))[:, 1]
            fp32, parity = p, None
        metrics = classification_metrics(val_y, (p >= threshold).astype(np.int64))
        item = {"family": family, "pipeline": name, "frozen_threshold": threshold,
                "classification": metrics, "fp32_classification": classification_metrics(val_y, (fp32 >= threshold).astype(np.int64)),
                "auc": float(roc_auc_score(val_y, p)), "parity": parity,
                "joint_80_pass": bool(metrics["recall"]["fall"] >= .8 and metrics["recall"]["nonfall"] >= .8),
                "test_payload_opened": False, "validation_threshold_tuned": False,
                "deployment_ready": False,
                "predictions": [{"id": r.sample_id, "label": r.label_id, "probability": float(q)}
                                for r, q in zip(validation_rows, p)]}
        save(path / "metrics.json", item)
        finals.append(item)
        print(json.dumps({k: v for k, v in item.items() if k != "predictions"}), flush=True)
    report = {"protocol": protocol,
              "candidates": [{"family": r["family"], "pipeline": r["pipeline"], "summary": r["summary"]} for r in all_results],
              "frozen_validation": finals, "unavailable": unavailable_event_metrics(),
              "test_payload_opened": False, "raw_source_modified": False,
              "production_default_changed": False}
    save(args.out_dir / "final_report.json", report)


if __name__ == "__main__":
    main()

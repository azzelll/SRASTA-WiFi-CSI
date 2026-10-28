#!/usr/bin/env python3
"""Bounded v8-architecture Hampel ablation; primary-train subject folds only."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time

import numpy as np

from srasta_csi.data import manifest_sha256, timestamps
from srasta_csi.development import grouped_folds, load_development, select_threshold
from srasta_csi.metrics import classification_metrics
from srasta_csi.model import TFLiteModel, export_full_int8, parity_report
from srasta_csi.preprocess import CausalPreprocessor, PreprocessConfig
from train_srasta_release import build

SPEC = {"name": "tcn_500", "length": 500, "channels": 32, "dilations": [1, 2, 4, 8, 16]}
SEEDS = (42, 43, 44)
TARGETS = {"recall_target": .88, "specificity_target": .8}
CANDIDATES = ("filtered", "raw")


def save(path, value):
    # Completed folds survive interruption; no partial JSON checkpoints.
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def train(x, y, seed, epochs, calibration=None):
    import tensorflow as tf
    tf.keras.backend.clear_session()
    model = build(SPEC, x, seed)
    model.compile(optimizer=tf.keras.optimizers.Adam(3e-4, clipnorm=1.), loss="sparse_categorical_crossentropy")
    counts = np.bincount(y, minlength=2)
    if (counts == 0).any():
        raise ValueError("fit cohort needs both labels")
    weights = {i: float(len(y) / (2 * counts[i])) for i in (0, 1)}
    kwargs = {}
    if calibration is not None:
        kwargs = {"validation_data": calibration, "callbacks": [tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=6, restore_best_weights=True)]}
    history = model.fit(x, y, epochs=epochs, batch_size=16, class_weight=weights, verbose=0, **kwargs).history
    best = int(np.argmin(history["val_loss"]) + 1) if calibration is not None else epochs
    return model, history, best


def probability(model, x):
    return np.concatenate([np.asarray(model(x[i:i+32], training=False))[:, 1] for i in range(0, len(x), 32)])


def windows(raw, config):
    return np.stack([CausalPreprocessor(config).transform(v, timestamps(len(v))) for v in raw])


def metric(y, p, energies, threshold, motion):
    return classification_metrics(y, ((p >= threshold) & (energies >= motion)).astype(int))


def rank(summary):
    return (min(summary["recall_mean"] / .88, summary["specificity_mean"] / .8), summary["macro_f1_mean"])


def select_candidate(results):
    baseline, candidate = (results[name]["summary"] for name in CANDIDATES)
    # No promotion by trading one target away. Below-target wins stay research.
    improves = (candidate["recall_mean"] >= baseline["recall_mean"] and
                candidate["specificity_mean"] >= baseline["specificity_mean"] and rank(candidate) > rank(baseline))
    return {"chosen": "raw" if improves else None, "improved_both_vs_grouped_baseline": improves,
            "proposal_targets_all_seeds_pass": bool(improves and results["raw"]["summary"]["all_seeds_targets_pass"]),
            "deployment_ready": False,
            "reason": "OOF development improvement; independent local evidence still required" if improves else
                      "single preprocessing change did not improve both grouped recall and specificity; retain v8 demo"}


def compare(args, protocol, base_config):
    rows, raw = load_development(args.data_root, "train")
    if len(rows) != 288 or {r.subject_id for r in rows} != {"U08", "U09", "U11", "U12", "U17", "U18"}:
        raise ValueError("unexpected primary train cohort")
    y = np.array([r.label_id for r in rows]); groups = np.array([r.subject_id for r in rows])
    results = {}
    for name in CANDIDATES:
        config = replace(base_config, hampel_history=name)
        x = windows(raw, config)
        energy = np.array([CausalPreprocessor.motion_energy(v) for v in x])
        path = args.out_dir / name
        path.mkdir(exist_ok=True)
        runs = []
        for seed in SEEDS:
            p = np.full(len(rows), np.nan); decisions = np.full(len(rows), -1)
            folds = []
            for fold in grouped_folds(groups):
                destination = path / f'seed_{seed}_{fold["held_out_subject"]}.json'
                fit, cal, ev = (fold[k] for k in ("fit", "calibrate", "evaluate"))
                if destination.exists():
                    record = json.loads(destination.read_text())
                    if record["evaluation_ids"] != [rows[i].sample_id for i in ev]:
                        raise ValueError("checkpoint row order changed")
                else:
                    started = time.perf_counter()
                    model, history, epochs = train(x[fit], y[fit], seed, args.epochs, (x[cal], y[cal]))
                    cut = select_threshold(y[cal], probability(model, x[cal]), **TARGETS)
                    motion = float(np.quantile(energy[fit][y[fit] == 1], .01))
                    p_eval = probability(model, x[ev])
                    prediction = ((p_eval >= cut["threshold"]) & (energy[ev] >= motion)).astype(int)
                    record = {"seed": seed, "held_out_subject": fold["held_out_subject"],
                              "calibration_subject": fold["calibration_subject"], "fit_subjects": fold["fit_subjects"],
                              "fit_ids": [rows[i].sample_id for i in fit], "calibration_ids": [rows[i].sample_id for i in cal],
                              "evaluation_ids": [rows[i].sample_id for i in ev], "evaluation_labels": y[ev].tolist(),
                              "probabilities": p_eval.tolist(), "predictions": prediction.tolist(),
                              "threshold": cut, "motion_threshold": motion, "epochs_best": epochs,
                              "history": history, "classification": classification_metrics(y[ev], prediction),
                              "elapsed_s": time.perf_counter() - started}
                    save(destination, record)
                    m = record["classification"]["recall"]
                    print(f'{name} seed={seed} held_out={fold["held_out_subject"]} recall={m["fall"]:.3f} specificity={m["nonfall"]:.3f} seconds={record["elapsed_s"]:.1f}', flush=True)
                p[ev] = record["probabilities"]; decisions[ev] = record["predictions"]
                folds.append(record)
            if not np.isfinite(p).all() or (decisions < 0).any():
                raise ValueError("OOF coverage incomplete")
            runs.append({"seed": seed, "folds": folds, "classification": classification_metrics(y, decisions),
                         "ids": [r.sample_id for r in rows], "probabilities": p.tolist(),
                         "predictions": decisions.tolist(),
                         "refit_threshold_development_tuned": select_threshold(y, p, **TARGETS)})
        recall = np.array([r["classification"]["recall"]["fall"] for r in runs])
        specificity = np.array([r["classification"]["recall"]["nonfall"] for r in runs])
        summary = {"recall_mean": float(recall.mean()), "recall_std": float(recall.std()),
                   "specificity_mean": float(specificity.mean()), "specificity_std": float(specificity.std()),
                   "macro_f1_mean": float(np.mean([r["classification"]["macro_f1"] for r in runs])),
                   "all_seeds_targets_pass": bool(((recall >= .88) & (specificity >= .8)).all())}
        results[name] = {"config": config.to_json(), "summary": summary, "runs": runs}
        save(path / "result.json", results[name])
    decision = select_candidate(results)
    save(args.out_dir / "comparison.json", {"protocol": protocol, "results": results, "decision": decision,
         "validation_payload_opened": False, "test_payload_opened": False})
    print(json.dumps({"summary": {k: v["summary"] for k, v in results.items()}, "decision": decision}, indent=2), flush=True)


def finalize(args, protocol, base_config):
    comparison = json.loads((args.out_dir / "comparison.json").read_text())
    chosen = comparison["decision"]["chosen"]
    if not chosen:
        print("No candidate eligible for refit/export; decision recorded, v8 unchanged.")
        return
    destination = args.out_dir / "final"
    destination.mkdir(exist_ok=False)
    result = comparison["results"][chosen]
    run = next(r for r in result["runs"] if r["seed"] == 42)
    config = replace(base_config, hampel_history=chosen)
    rows, raw = load_development(args.data_root, "train")
    x = windows(raw, config); y = np.array([r.label_id for r in rows])
    epochs = max(1, int(np.median([f["epochs_best"] for f in run["folds"]])))
    config = replace(config, motion_energy_threshold=float(np.quantile(
        [CausalPreprocessor.motion_energy(v) for v, label in zip(x, y) if label == 1], .01)))
    threshold = run["refit_threshold_development_tuned"]["threshold"]
    model, history, _ = train(x, y, 42, epochs)
    model.save(destination / "model.keras")
    indices = np.random.default_rng(42).choice(len(x), 256, replace=False)
    export_full_int8(model, x[indices], destination / "model.tflite")
    runtime = TFLiteModel(destination / "model.tflite")
    parity = parity_report(model, runtime, x)
    frozen = {"research_only": True, "deployment_ready": False, "chosen": chosen, "threshold": threshold,
              "epochs": epochs, "seed": 42, "preprocess": config.to_json(),
              "model_sha256": hashlib.sha256((destination / "model.tflite").read_bytes()).hexdigest(),
              "representative_ids": [rows[i].sample_id for i in indices], "representative_split": "primary train only",
              "train_parity": parity, "size_bytes": (destination / "model.tflite").stat().st_size,
              "protocol": protocol, "history": history, "validation_loaded_at_freeze": False, "test_payload_opened": False}
    save(destination / "frozen.json", frozen)
    # Historical U19 loaded only AFTER artifact, cutoff and motion floor freeze.
    val_rows, val_raw = load_development(args.data_root, "validation")
    values = windows(val_raw, config)
    labels = np.array([r.label_id for r in val_rows])
    p = np.array([runtime.probability(v) for v in values])
    energies = np.array([CausalPreprocessor.motion_energy(v) for v in values])
    save(destination / "validation.json", {"interpretation": "reused U19 diagnostic, not independent test; no further tuning",
         "classification": metric(labels, p, energies, threshold, config.motion_energy_threshold),
         "parity": parity_report(model, runtime, values), "ids": [r.sample_id for r in val_rows],
         "probabilities": p.tolist(), "labels": labels.tolist(), "test_payload_opened": False})
    print((destination / "validation.json").read_text(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--selected", type=Path, default=Path("artifacts/releases/20261001-tcn-v8-motion-calibrated/selected"))
    parser.add_argument("--stage", choices=("compare", "finalize"), default="compare")
    parser.add_argument("--epochs", type=int, default=35)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("epochs must be positive")
    base_config = PreprocessConfig.from_json(json.loads((args.selected / "preprocess_config.json").read_text()))
    sources = [Path(__file__), Path(__file__).parent / "train_srasta_release.py"] + [Path(__file__).parent / "srasta_csi" / (n + ".py") for n in ("preprocess", "development", "model", "data")]
    protocol = {"hypothesis": "raw past Hampel samples recover sustained motion rejected by recursive filtered history",
                "change": "hampel_history only; v8 TCN32 architecture, shared pipeline, no new architecture search",
                "spec": SPEC, "seeds": SEEDS, "epochs_max": args.epochs, "patience": 6, "targets": TARGETS,
                "roles": "six folds: four subjects fit, next cyclic subject calibration, one evaluation",
                "motion_floor": "1st percentile positive FIT energy only; classifier cutoff calibrated separately",
                "selection": "raw must improve min-target-ratio and not reduce either mean recall or specificity vs baseline",
                "epoch_rule": "median best calibration epoch across seed42 folds; full train refit",
                "refit_threshold": "seed42 pooled primary OOF; development tuned, no U19 selection",
                "base_config": base_config.to_json(),
                "manifest_sha256": manifest_sha256(args.data_root / "curated/esp32_s3_fall_v1/manifest.csv"),
                "code_sha256": {str(p.relative_to(Path(__file__).parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                "versions": {n: version(n) for n in ("numpy", "tensorflow", "scikit-learn", "h5py")},
                "test_payload_opened": False, "U19": "historically reused diagnostic only; never loaded in compare"}
    # JSON roundtrip normalizes tuples for strict resume comparisons.
    protocol = json.loads(json.dumps(protocol))
    if not args.out_dir.exists():
        if args.stage != "compare":
            raise ValueError("comparison must run first")
        args.out_dir.mkdir(parents=True)
        save(args.out_dir / "protocol.json", protocol)
    elif json.loads((args.out_dir / "protocol.json").read_text()) != protocol:
        raise ValueError("source/config/protocol changed; choose a new output directory")
    (compare if args.stage == "compare" else finalize)(args, protocol, base_config)


if __name__ == "__main__":
    main()

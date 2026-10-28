#!/usr/bin/env python3
"""Bounded local TCN head fine-tuning; A/B/C development, never local D/E fitting."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
import os
from pathlib import Path
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")

import numpy as np

from srasta_csi.capture_archive import digest, private_write, utc_now
from srasta_csi.local_fall import collect_local_fall_windows
from srasta_csi.metrics import classification_metrics
from srasta_csi.model import TFLiteModel, export_full_int8, parity_report
from srasta_csi.preprocess import PreprocessConfig

SEEDS = (42, 43, 44)


def save(path, payload):
    private_write(path, payload)


def select_joint(y, probability, energy, motion):
    """Select on the named calibration person only, using a frozen finite grid."""
    best = None
    for cut in np.r_[np.arange(.05, 1., .05), 1.000001]:
        for multiplier in (0., .25, .5, .75, 1.):
            threshold = motion * multiplier
            decisions = (probability >= cut) & (energy >= threshold)
            recall = float(np.mean(decisions[y == 1]))
            specificity = float(np.mean(~decisions[y == 0]))
            tp, fp, fn, tn = (np.sum(decisions & (y == 1)), np.sum(decisions & (y == 0)),
                              np.sum(~decisions & (y == 1)), np.sum(~decisions & (y == 0)))
            macro = float((2*tp/max(1, 2*tp+fp+fn) + 2*tn/max(1, 2*tn+fp+fn))/2)
            rank = (recall >= .88 and specificity >= .8, min(recall/.88, specificity/.8),
                    macro, -abs(float(cut)-.45), multiplier)
            if best is None or rank > best[0]:
                best = (rank, {"threshold": float(cut), "motion_threshold": float(threshold)})
    return best[1]


def prepare(args):
    selected = args.base
    frozen = json.loads((selected / "frozen.json").read_text())
    assert digest(selected / "model.tflite") == frozen["model_sha256"]
    config = PreprocessConfig.from_json(json.loads((selected / "preprocess_config.json").read_text()))
    protocol = {"recorded_at_utc": utc_now(), "stage": "local_development_only",
                "base_model_sha256": frozen["model_sha256"], "base_keras_sha256": digest(selected / "model.keras"),
                "preprocessing": config.to_json(), "window_length": 500, "raw_ring_frames": 512,
                "positive_sampling": "one actual window ending at each reviewed fall end; no replicated samples",
                "negative_sampling": "up to 24 deterministic windows inside each reviewed nonfall interval",
                "empty_use": "background diagnostic only; never fitting or person-fold selection",
                "groups": ["LOC_A", "LOC_B", "LOC_C"], "seeds": list(SEEDS), "epochs": 8,
                "fit": "only final Dense head; v8 encoder frozen; Adam 0.001, balanced classes",
                "fold_roles": [{"fit": "LOC_A", "calibrate": "LOC_B", "evaluate": "LOC_C"},
                               {"fit": "LOC_B", "calibrate": "LOC_C", "evaluate": "LOC_A"},
                               {"fit": "LOC_C", "calibrate": "LOC_A", "evaluate": "LOC_B"}],
                "calibration": "probability grid 0.05..0.95 and 1.000001; motion multipliers 0,.25,.5,.75,1",
                "selection": "no decline in either pooled OOF recall or specificity versus fixed v8; at least one strict improvement",
                "local_validation_payload_opened": False, "local_test_payload_opened": False,
                "independent_validation_available": False, "deployment_ready": False,
                "metric_scope": "window proxies; sampled negatives cannot estimate continuous FAR/latency",
                "source_sha256": {str(p.relative_to(Path(__file__).parent)): digest(p) for p in
                    (Path(__file__), Path(__file__).parent / "srasta_csi/local_fall.py",
                     Path(__file__).parent / "srasta_csi/capture_governance.py")}}
    save(args.out / "protocol.json", protocol)
    print("Preparing accepted train sessions; validation/test/pilot payloads excluded", flush=True)
    rows, inventory = collect_local_fall_windows(args.root, config)
    if not rows:
        raise ValueError("no accepted local windows")
    profiles = {r["capture_profile_hash"] for r in rows}
    if len(profiles) != 1:
        raise ValueError("local windows must share one capture profile")
    x = np.stack([r["window"] for r in rows])
    metadata = [{key: value for key, value in row.items() if key != "window"} for row in rows]
    np.savez_compressed(args.out / "windows.npz", x=x)
    save(args.out / "windows.json", metadata)
    save(args.out / "inventory.json", inventory)
    save(args.out / "candidate_preprocess_config.json", replace(config, capture_profile_hash=next(iter(profiles))).to_json())
    save(args.out / "prepared.json", {"windows_sha256": digest(args.out / "windows.npz"),
        "metadata_sha256": digest(args.out / "windows.json"), "protocol_sha256": digest(args.out / "protocol.json"),
        "windows": len(rows), "counts": dict(Counter(f'{r["subject_id"]}:{r["label"]}' for r in rows))})
    print(json.dumps({"prepared_windows": len(rows), "counts": dict(Counter(f'{r["subject_id"]}:{r["label"]}' for r in rows))}), flush=True)


def train_head(embedding, labels, weights, seed):
    import tensorflow as tf

    tf.keras.utils.set_random_seed(seed)
    head = tf.keras.Sequential([tf.keras.Input((embedding.shape[1],)), tf.keras.layers.Dense(2, activation="softmax")])
    head.layers[-1].set_weights(weights)
    head.compile(optimizer=tf.keras.optimizers.Adam(.001), loss="sparse_categorical_crossentropy")
    counts = np.bincount(labels, minlength=2)
    if (counts == 0).any():
        raise ValueError("each fitting person must have both classes")
    sample_weights = np.asarray([len(labels)/(2*counts[label]) for label in labels], dtype=np.float32)
    rng = np.random.default_rng(seed)
    for _ in range(8):
        indices = rng.permutation(len(labels))
        for offset in range(0, len(indices), 16):
            batch = indices[offset:offset+16]
            head.train_on_batch(embedding[batch], labels[batch], sample_weight=sample_weights[batch])
    return head


def fit(args):
    import tensorflow as tf

    protocol = json.loads((args.out / "protocol.json").read_text())
    prepared = json.loads((args.out / "prepared.json").read_text())
    for name, key in (("windows.npz", "windows_sha256"), ("windows.json", "metadata_sha256"),
                      ("protocol.json", "protocol_sha256")):
        if digest(args.out / name) != prepared[key]:
            raise ValueError("prepared development inputs changed")
    if digest(args.base / "model.keras") != protocol["base_keras_sha256"]:
        raise ValueError("base model changed after protocol freeze")
    x = np.load(args.out / "windows.npz")["x"]
    rows = json.loads((args.out / "windows.json").read_text())
    y = np.asarray([r["label"] for r in rows])
    groups = np.asarray([r["subject_id"] for r in rows])
    energies = np.asarray([r["motion_energy"] for r in rows])
    people = np.isin(groups, protocol["groups"])
    if set(groups[people]) != set(protocol["groups"]) or any(set(y[groups == g]) != {0, 1} for g in protocol["groups"]):
        raise ValueError("three confirmed training people with both labels required")
    base = tf.keras.models.load_model(args.base / "model.keras", compile=False)
    encoder = tf.keras.Model(base.inputs, base.layers[-1].input)
    embedding = np.concatenate([np.asarray(encoder(x[i:i+32], training=False)) for i in range(0, len(x), 32)])
    old_head = base.layers[-1].get_weights()
    lite = TFLiteModel(args.base / "model.tflite")
    base_probabilities = np.asarray([lite.probability(window) for window in x])
    motion = protocol["preprocessing"]["motion_energy_threshold"]
    fixed = ((base_probabilities >= .45) & (energies >= motion)).astype(np.int64)
    baseline = classification_metrics(y[people], fixed[people])
    runs = []
    oof_probabilities = []
    for seed in SEEDS:
        p = np.full(len(x), np.nan)
        predictions = np.full(len(x), -1)
        folds = []
        for roles in protocol["fold_roles"]:
            started = time.perf_counter()
            fit_mask, cal_mask, eval_mask = (groups == roles[k] for k in ("fit", "calibrate", "evaluate"))
            head = train_head(embedding[fit_mask], y[fit_mask], old_head, seed)
            p_cal = np.asarray(head(embedding[cal_mask], training=False))[:, 1]
            cut = select_joint(y[cal_mask], p_cal, energies[cal_mask], motion)
            p[eval_mask] = np.asarray(head(embedding[eval_mask], training=False))[:, 1]
            predictions[eval_mask] = ((p[eval_mask] >= cut["threshold"]) &
                                      (energies[eval_mask] >= cut["motion_threshold"])).astype(int)
            metric = classification_metrics(y[eval_mask], predictions[eval_mask])
            folds.append({**roles, "cut": cut, "classification": metric,
                          "fit_sessions": sorted({r["session_id"] for r,m in zip(rows, fit_mask) if m}),
                          "calibration_sessions": sorted({r["session_id"] for r,m in zip(rows, cal_mask) if m}),
                          "evaluation_sessions": sorted({r["session_id"] for r,m in zip(rows, eval_mask) if m}),
                          "elapsed_s": time.perf_counter()-started})
            print(json.dumps({"seed": seed, "evaluate": roles["evaluate"], "recall": metric["recall"]}), flush=True)
        if np.any(predictions[people] < 0):
            raise ValueError("incomplete OOF coverage")
        result = {"seed": seed, "folds": folds, "classification": classification_metrics(y[people], predictions[people]),
                  "OOF_predictions": [{"session_id": r["session_id"], "start_us": r["start_us"],
                                       "label": r["label"], "probability": float(prob), "prediction": int(pred)}
                                      for r,prob,pred,keep in zip(rows,p,predictions,people) if keep]}
        save(args.out / f"seed_{seed}.json", result)
        runs.append(result)
        oof_probabilities.append(p[people])
    mean_recall = {key: float(np.mean([r["classification"]["recall"][key] for r in runs])) for key in ("fall", "nonfall")}
    improves = all(mean_recall[k] >= baseline["recall"][k] for k in mean_recall) and any(mean_recall[k] > baseline["recall"][k] for k in mean_recall)
    final_cut = select_joint(y[people], np.mean(oof_probabilities, axis=0), energies[people], motion)
    final_head = train_head(embedding[people], y[people], old_head, 42)
    base.layers[-1].set_weights(final_head.layers[-1].get_weights())
    base.save(args.out / "candidate.keras")
    representative = x[people]
    export_full_int8(base, representative, args.out / "candidate.tflite")
    parity = parity_report(base, TFLiteModel(args.out / "candidate.tflite"), representative)
    save(args.out / "parity.json", parity)
    candidate = {"model_sha256": digest(args.out / "candidate.tflite"), **final_cut,
                 "model_status": "research_candidate_requires_D_validation", "deployment_ready": False,
                 "independent_validation_available": False, "local_test_payload_opened": False,
                 "parity_pass": parity["status"] == "passed"}
    save(args.out / "candidate.json", candidate)
    result = {"scope": "A/B/C development; previously inspected local cohort; window proxies only",
              "baseline_v8_INT8": baseline, "candidate_mean_OOF_recall": mean_recall,
              "seed_results": [{"seed": r["seed"], "classification": r["classification"]} for r in runs],
              "improves_both_without_tradeoff": bool(improves), "candidate": candidate,
              "candidate_continuous_event_recall": None, "candidate_false_alerts_per_hour": None,
              "candidate_suspected_latency_s": None, "candidate_confirmed_latency_s": None,
              "unavailable_reason": "sampled event windows do not supply continuous state-machine prediction coverage; D/E not recorded",
              "promoted_to_live": False, "validation_payload_opened": False, "test_payload_opened": False}
    save(args.out / "comparison.json", result)
    print(json.dumps({"baseline": baseline["recall"], "candidate_mean_OOF": mean_recall,
                      "improvement_without_tradeoff": bool(improves), "parity_pass": parity["status"] == "passed",
                      "deployment_ready": False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("../SRASTA_LOCAL_CAPTURE"))
    parser.add_argument("--base", type=Path, default=Path("artifacts/releases/20261001-tcn-v8-motion-calibrated/selected"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", choices=("prepare", "fit"), required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.out.mkdir(parents=True, exist_ok=True)
    (prepare if args.stage == "prepare" else fit)(args)


if __name__ == "__main__":
    main()

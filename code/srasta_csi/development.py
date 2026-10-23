"""Recording-level development helpers; no test payloads or event labels."""

from __future__ import annotations

import numpy as np

from .baseline import FEATURE_NAMES, motion_features
from .contract import CaptureProfile
from .data import read_h5_amplitude, read_manifest, resolve_source_path, timestamps
from .metrics import classification_metrics
from .preprocess import CausalPreprocessor, PreprocessConfig


PIPELINES = ("causal_filtered", "causal_raw", "paper_window_zscore")
DEVELOPMENT_FEATURE_NAMES = (*FEATURE_NAMES,
    *(f"derivative_energy_bin_{i}" for i in range(10)),
    *(f"temporal_variance_bin_{i}" for i in range(10)),
    "derivative_energy_p10", "derivative_energy_p25", "derivative_energy_p50",
    "derivative_energy_p75", "derivative_energy_p90", "derivative_energy_p95",
    "derivative_energy_p99", "peak_time_fraction", "peak_to_mean_energy",
    "carrier_variance_p25", "carrier_variance_p75")


def load_development(data_root, split):
    # Check the allowed split BEFORE resolving or reading a payload.
    if split not in ("train", "validation"):
        raise ValueError("development may load only train or validation")
    rows = [r for r in read_manifest(data_root / "curated/esp32_s3_fall_v1/manifest.csv")
            if r.split == split]
    values = [read_h5_amplitude(resolve_source_path(r, data_root)) for r in rows]
    if not values or any(v.shape != (500, 52) for v in values):
        raise ValueError("development requires measured 500-frame, 52-carrier recordings")
    return rows, np.stack(values).astype(np.float32)


def pipeline_config(name):
    if name not in PIPELINES:
        raise ValueError("unknown development pipeline")
    if name == "paper_window_zscore":
        return {"name": name, "research_only": True, "window_length": 500,
                "normalization": "one mean/std over the measured current [500,52] window",
                "epsilon": 1e-6, "filters": "none", "future_packets_used": False,
                "within_window_prefix_causal": False,
                "runtime_installed": False, "capture_profile_attested": False,
                "reference": "https://arxiv.org/html/2505.21866v2#S4.SS2"}
    config = PreprocessConfig(capture_profile_hash=CaptureProfile().hash,
                              normalized_clip=2.,
                              hampel_history="raw" if name == "causal_raw" else "filtered")
    return {"name": name, "shared_preprocess_config": config.to_json(),
            "source_capture_profile_attested": False}


def prepare_windows(values, name):
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 3 or values.shape[1:] != (500, 52) or not np.isfinite(values).all():
        raise ValueError("development windows require finite [n,500,52]")
    config = pipeline_config(name)
    if name == "paper_window_zscore":
        # Statistics are local to each complete current window. No other
        # recording, validation subject, or test observation is involved.
        means = values.mean(axis=(1, 2), keepdims=True, dtype=np.float64)
        scales = values.std(axis=(1, 2), keepdims=True, dtype=np.float64)
        return ((values - means) / (scales + config["epsilon"])).astype(np.float32)
    processor = CausalPreprocessor(PreprocessConfig.from_json(config["shared_preprocess_config"]))
    return np.stack([processor.transform(v, timestamps(len(v))) for v in values])


def development_features(window):
    values = np.asarray(window, dtype=np.float32)
    base = motion_features(values, motion_threshold=1e-4)
    energy = np.mean(np.diff(values.astype(np.float64), axis=0) ** 2, axis=1)
    energy_bins = [float(v.mean()) for v in np.array_split(energy, 10)]
    variance_bins = [float(np.var(v, axis=0).mean()) for v in np.array_split(values, 10)]
    features = np.r_[base, energy_bins, variance_bins,
                     np.quantile(energy, [.1, .25, .5, .75, .9, .95, .99]),
                     np.argmax(energy) / len(energy), energy.max() / (energy.mean() + 1e-12),
                     np.quantile(np.var(values, axis=0), [.25, .75])].astype(np.float32)
    if features.shape != (len(DEVELOPMENT_FEATURE_NAMES),) or not np.isfinite(features).all():
        raise ValueError("invalid development features")
    return features


def grouped_folds(groups):
    """Six outer subject folds with a separate cyclic calibration subject."""
    groups = np.asarray(groups)
    subjects = sorted(set(groups.tolist()))
    if len(subjects) < 3:
        raise ValueError("fit, calibration, and evaluation need different subjects")
    for i, held_out in enumerate(subjects):
        calibration = subjects[(i + 1) % len(subjects)]
        fit = np.flatnonzero((groups != held_out) & (groups != calibration))
        calibrate = np.flatnonzero(groups == calibration)
        evaluate = np.flatnonzero(groups == held_out)
        yield {"fit": fit, "calibrate": calibrate, "evaluate": evaluate,
               "held_out_subject": held_out, "calibration_subject": calibration,
               "fit_subjects": sorted(set(groups[fit].tolist()))}


def select_threshold(y, probabilities, recall_target=.8, specificity_target=.8):
    y = np.asarray(y, dtype=np.int64)
    p = np.asarray(probabilities, dtype=np.float64)
    if (y.shape != p.shape or y.ndim != 1 or set(y.tolist()) != {0, 1}
            or not np.isfinite(p).all() or np.any((p < 0) | (p > 1))):
        raise ValueError("threshold selection needs both classes and finite probabilities")
    if not 0 < recall_target <= 1 or not 0 < specificity_target <= 1:
        raise ValueError("metric targets must lie in (0,1]")
    # Midpoints make a selected cut less dependent on float rounding. Include
    # both endpoints; the top cut also permits an all-negative decision.
    distinct = np.unique(p)
    cuts = np.unique(np.r_[0., (distinct[:-1] + distinct[1:]) / 2.,
                           np.nextafter(distinct[-1], np.inf)])
    results = []
    for cut in cuts:
        metrics = classification_metrics(y, (p >= cut).astype(np.int64))
        recall = metrics["recall"]["fall"]
        specificity = metrics["recall"]["nonfall"]
        passed = recall >= recall_target and specificity >= specificity_target
        results.append({"threshold": float(cut), "classification": metrics,
                        "proxy_gates_pass": passed,
                        "targets": {"recall": recall_target, "specificity": specificity_target}})
    return max(results, key=lambda r: (r["proxy_gates_pass"],
               min(r["classification"]["recall"]["fall"] / recall_target,
                   r["classification"]["recall"]["nonfall"] / specificity_target),
               r["classification"]["macro_f1"], -abs(r["threshold"] - .5)))

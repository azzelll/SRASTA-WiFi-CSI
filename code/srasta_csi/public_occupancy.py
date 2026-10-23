"""Public-data sleep/occupancy experiments on measured native channels.

These artifacts are for recorded-source inference, not local ESP32 deployment.
The alternate storage interpretation is an explicit ablation, not an axis fix
asserted by the source author. No channels are resized to a 52-carrier tensor.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import h5py
import joblib
import numpy as np

from .native_features import FEATURE_NAMES, native_motion_features

ARTIFACT_TYPE = "srasta_public_occupancy_native_v2"
LAYOUTS = ("declared_axes", "flat_time_major_ablation")
AWAKE_LABELS = {"walking", "running", "jumping", "wavinghand", "seated-breathing"}
EXTRA_NAMES = tuple(f"{signal}_{q}" for signal in
                    ("relative_std", "relative_difference", "lag1", "lag30")
                    for q in ("p25", "median", "p75", "p90"))
INVARIANT_NAMES = FEATURE_NAMES + EXTRA_NAMES + ("common_band_fraction", "common_peak", "common_entropy")


def source_rows(root: Path, task: str):
    """Filter official source-train IDs before any payload is opened."""
    if task not in {"BreathingDetection", "HumanActivityRecognition"}:
        raise ValueError("unsupported occupancy source task")
    folder = root / task
    allowed = set(json.loads((folder / "splits/train_id.json").read_text()))
    with (folder / "metadata/sample_metadata.csv").open() as f:
        rows = [dict(r, task=task) for r in csv.DictReader(f) if r["id"] in allowed]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("duplicate source IDs")
    return rows, allowed


def balanced_sample(rows, cap, salt):
    """Round-robin device/placement/label strata; selection never uses CSI."""
    groups = defaultdict(list)
    for r in rows:
        key = (r["user"], r["device"], r["num_sub"], r.get("deplyoment", ""), r["label"])
        groups[key].append(r)
    for rs in groups.values():
        rs.sort(key=lambda r: hashlib.sha256((salt + r["id"]).encode()).hexdigest())
    result = []
    for offset in range(max(map(len, groups.values()), default=0)):
        for key in sorted(groups):
            if offset < len(groups[key]):
                result.append(groups[key][offset])
                if len(result) >= cap:
                    return result
    return result


def select_protocol(root: Path, cap: int):
    if cap < 1:
        raise ValueError("positive per-stratum cap required")
    breathing, _ = source_rows(root, "BreathingDetection")
    har, _ = source_rows(root, "HumanActivityRecognition")
    observed = defaultdict(set)
    for r in breathing:
        observed[(r["user"], r["device"], r["num_sub"])].add(r["label"])
    breathing = [r for r in breathing if observed[(r["user"], r["device"], r["num_sub"])] == {"empty", "sleep"}]
    selected = {}
    for split, user in (("train", "U06"), ("validation", "U23")):
        selected[split] = {}
        for label in ("empty", "sleep"):
            selected[split][label] = balanced_sample(
                [r for r in breathing if r["user"] == user and r["label"] == label], cap, "occupancy-v2:")
        awake = [r for r in har if r["label"] in AWAKE_LABELS and
                 (r["user"] == "U05" if split == "validation" else r["user"] in {"U01", "U02", "U03", "U04", "U06"})]
        selected[split]["awake"] = balanced_sample(awake, cap, "occupancy-v2:")
        if any(not rs for rs in selected[split].values()):
            raise ValueError("missing empty/sleep/awake stratum")
    ids = [{(r["task"], r["id"]) for rs in part.values() for r in rs} for part in selected.values()]
    people = [{r["user"] for rs in part.values() for r in rs} for part in selected.values()]
    if ids[0] & ids[1] or people[0] & people[1]:
        raise ValueError("subject/recording overlap")
    return selected


def load_amplitude(root: Path, row, allowed, layout):
    """Native source shape is enforced before either disclosed interpretation."""
    if row["id"] not in allowed:
        raise ValueError("official validation/test payload forbidden")
    if layout not in LAYOUTS:
        raise ValueError("unknown source layout")
    task = row["task"]
    if task not in {"BreathingDetection", "HumanActivityRecognition"}:
        raise ValueError("unsupported occupancy source task")
    folder = (root / task).resolve()
    path = (folder / row["file_path"]).resolve()
    if not path.is_relative_to(folder):
        raise ValueError("source path escapes corpus")
    frames = 300 if task == "BreathingDetection" else 500
    carriers = int(row["num_sub"])
    with h5py.File(path, "r") as f:
        data = np.asarray(f["CSI_amps"], dtype=np.float32)
    if data.shape != (carriers, frames, 1) or carriers < 2:
        raise ValueError(f"unexpected native shape {data.shape}")
    if not np.isfinite(data).all() or np.any(data < 0):
        raise ValueError("invalid native amplitude")
    # The ablation reinterprets storage order at the ORIGINAL channel count.
    values = data[:, :, 0].T if layout == "declared_axes" else data.reshape(frames, carriers)
    return values, 30. if task == "BreathingDetection" else 100.


def invariant_features(values, rate_hz):
    """Gain-independent summaries; aggregate real channels without correspondence."""
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or min(x.shape) < 2 or not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError("finite nonnegative native [time,channels] required")
    if not np.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("positive measured/nominal rate required")
    means = x.mean(axis=0)
    active = means > max(float(means.max()) * 1e-9, 0.)
    # Dead channels are excluded from SUMMARY statistics, never remapped/padded.
    if not np.any(active):
        raise ValueError("no measured active carriers")
    relative = x[:, active] / means[active]
    base = native_motion_features(relative, rate_hz)
    axis = np.linspace(-1., 1., len(relative))
    design = np.column_stack((axis, np.ones(len(axis))))
    residual = relative - design @ np.linalg.lstsq(design, relative, rcond=None)[0]
    std = residual.std(axis=0)
    difference = np.sqrt(np.mean(np.diff(relative, axis=0) ** 2, axis=0))
    correlations = []
    for lag in (1, min(int(round(rate_hz)), len(relative) // 3)):
        left, right = residual[:-lag], residual[lag:]
        correlations.append(np.mean(left * right, axis=0) /
                            np.maximum(np.sqrt(np.mean(left ** 2, axis=0) * np.mean(right ** 2, axis=0)), 1e-12))
    extras = np.concatenate([np.quantile(v, [.25, .5, .75, .9]) for v in (std, difference, *correlations)])
    power = np.abs(np.fft.rfft(residual * np.hanning(len(residual))[:, None], axis=0)) ** 2
    power[0] = 0
    normalized = power / np.maximum(power.sum(axis=0), 1e-12)
    common = normalized.mean(axis=1)
    freq = np.fft.rfftfreq(len(residual), 1. / rate_hz)
    aggregate = [common[(freq >= .1) & (freq <= .6)].sum(), common.max(),
                 -(common * np.log(np.maximum(common, 1e-12))).sum() / np.log(len(common))]
    features = np.concatenate((base, extras, aggregate)).astype(np.float32)
    if features.shape != (len(INVARIANT_NAMES),) or not np.isfinite(features).all():
        raise ValueError("invalid invariant feature vector")
    return features


class PublicOccupancyInference:
    """Explicit recorded-data adapter, intentionally separate from PresenceInference."""
    def __init__(self, path):
        self.payload = joblib.load(path)
        p = self.payload
        if p.get("artifact_type") != ARTIFACT_TYPE or p.get("research_only") is not True:
            raise ValueError("public research artifact required")
        if p.get("task") not in {"breathing", "presence"} or list(p["model"].classes_) != [0, 1]:
            raise ValueError("invalid binary task/classes")
        if p.get("classes") != (["empty", "sleep"] if p["task"] == "breathing" else ["empty", "present"]):
            raise ValueError("invalid task label mapping")
        self.threshold = float(p.get("threshold", .5))
        if not np.isfinite(self.threshold) or not 0 < self.threshold <= 1:
            raise ValueError("invalid decision threshold")
        expected = FEATURE_NAMES if p.get("features") == "legacy" else INVARIANT_NAMES
        if p.get("feature_names") != expected or p.get("layout") not in LAYOUTS:
            raise ValueError("feature/layout mismatch")

    def predict(self, values, rate_hz):
        p = self.payload
        features = native_motion_features(values, rate_hz) if p["features"] == "legacy" else invariant_features(values, rate_hz)
        positive = float(p["model"].predict_proba(features[None])[0, 1])
        return {"task": p["task"], "label": p["classes"][int(positive >= self.threshold)],
                "positive_probability": positive, "source": "public_recording",
                "research_only": True, "ESP32_validated": False,
                "layout": p["layout"], "threshold": self.threshold, "normal_class_available": False}

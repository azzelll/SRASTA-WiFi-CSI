"""Transparent motion features used by the internal Random Forest baseline."""

from __future__ import annotations

import numpy as np

from .decoder import FEATURE_COUNT


FEATURE_NAMES = (
    "mean_absolute_change", "peak_derivative_energy", "mean_derivative_energy",
    "signal_variance", "signal_energy", "motion_duration_s", "spectral_entropy",
    "log_post_pre_motion_ratio",
)


def motion_features(values: np.ndarray, sample_rate_hz: float = 100.0, motion_threshold: float = 0.02) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] != FEATURE_COUNT or len(values) < 4 or not np.isfinite(values).all():
        raise ValueError("motion features require finite [time,52] input")
    derivative = np.diff(values, axis=0)
    energy = np.mean(np.square(derivative), axis=1)
    section = max(1, len(energy) // 4)
    power = np.abs(np.fft.rfft(energy - np.mean(energy)))[1:] ** 2
    entropy = 0.0
    if len(power) > 1 and np.sum(power) > 1e-12:
        probabilities = power / np.sum(power)
        entropy = float(-np.sum(probabilities * np.log(probabilities + 1e-12)) / np.log(len(probabilities)))
    return np.asarray([
        np.mean(np.abs(derivative)), np.max(energy), np.mean(energy), np.mean(np.var(values, axis=0)),
        np.mean(np.square(values)), np.count_nonzero(energy >= motion_threshold) / sample_rate_hz,
        entropy, np.log((np.mean(energy[-section:]) + 1e-12) / (np.mean(energy[:section]) + 1e-12)),
    ], dtype=np.float32)

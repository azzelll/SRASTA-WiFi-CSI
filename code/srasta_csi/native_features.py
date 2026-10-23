"""Research features on native CSI channels; never resize to an ESP32 tensor."""
from __future__ import annotations

import numpy as np

STATISTICS = ("median", "p25", "p75", "p90")
SIGNALS = ("log_std", "difference_rms", "relative_difference", "breathing_fraction", "peak_concentration", "spectral_entropy")
FEATURE_NAMES = tuple(f"{signal}_{statistic}" for signal in SIGNALS for statistic in STATISTICS)


def native_motion_features(values: np.ndarray, rate_hz: float) -> np.ndarray:
    """Aggregate measured channels without inventing carrier correspondences."""
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 2 or min(x.shape) < 2 or not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError("native amplitude must be finite nonnegative [time,channels]")
    if not np.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    x = np.log1p(x)
    axis = np.arange(len(x), dtype=float)
    design = np.column_stack((axis, np.ones(len(x))))
    detrended = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
    std = detrended.std(axis=0)
    differences = np.sqrt(np.mean(np.diff(x, axis=0) ** 2, axis=0))
    power = np.abs(np.fft.rfft(detrended * np.hanning(len(x))[:, None], axis=0)) ** 2
    power[0] = 0
    total = power.sum(axis=0)
    normalized = power / np.maximum(total, 1e-12)
    freq = np.fft.rfftfreq(len(x), 1 / rate_hz)
    respiration = normalized[(freq >= .1) & (freq <= .6)].sum(axis=0)
    peaks = normalized.max(axis=0)
    entropy = -(normalized * np.log(np.maximum(normalized, 1e-12))).sum(axis=0) / np.log(len(power))
    signals = (std, differences, differences / np.maximum(std, 1e-6), respiration, peaks, entropy)
    result = np.concatenate([np.quantile(v, [.5, .25, .75, .9]) for v in signals]).astype(np.float32)
    if not np.isfinite(result).all():
        raise ValueError("native summary produced nonfinite features")
    return result

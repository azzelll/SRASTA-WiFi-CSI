"""Native-channel research features. These are not a live capture adapter."""
from __future__ import annotations

import numpy as np

QUANTILES = (.1, .25, .5, .75, .9)
SIGNALS = ("relative_std", "relative_difference", "roughness", "lag_100ms",
           "lag_500ms", "band_01_06", "band_06_2", "band_2_5", "band_5_10",
           "spectral_entropy", "spectral_peak")
FEATURE_NAMES = tuple(f"{s}_q{int(q*100)}" for s in SIGNALS for q in QUANTILES) + tuple(
    f"temporal_energy_{i}" for i in range(10)) + (
    "burst_p50", "burst_p90", "burst_p99", "burst_max", "energy_centroid",
    "pre_post_ratio", "common_energy_fraction", "relative_level_drift")


def temporal_features(values, rate_hz):
    """Summarize gain-normalized dynamics, retaining measured carrier positions.

    Only feature summaries aggregate carriers. No carrier padding, resizing,
    selection by activity label, or interpolation between source devices.
    Statistics use the complete current recording, not a causal frame prefix.
    """
    x = np.asarray(values, dtype=np.float64)
    if (x.ndim != 2 or min(x.shape) < 2 or len(x) < 20
            or not np.isfinite(x).all() or np.any(x < 0)):
        raise ValueError("finite nonnegative native amplitude [time,channels] required")
    if not np.isfinite(rate_hz) or rate_hz < 20:
        raise ValueError("research spectral features require a rate of at least 20 Hz")
    means = x.mean(axis=0)
    active = means > 0
    if not active.any():
        raise ValueError("all-zero recording has no measured signal")
    relative = x[:, active] / means[active] - 1.
    axis = np.linspace(-1., 1., len(x))
    trend = np.column_stack((axis, np.ones(len(x))))
    residual = relative - trend @ np.linalg.lstsq(trend, relative, rcond=None)[0]
    variance = np.mean(residual ** 2, axis=0)
    std = np.sqrt(variance)
    delta = np.diff(relative, axis=0)
    difference = np.sqrt(np.mean(delta ** 2, axis=0))
    signals = [np.log1p(std), np.log1p(difference), difference / np.maximum(std, 1e-12)]
    for seconds in (.1, .5):
        lag = max(1, min(int(round(rate_hz * seconds)), len(x) // 3))
        a, b = residual[:-lag], residual[lag:]
        signals.append(np.mean(a*b, axis=0) / np.maximum(
            np.sqrt(np.mean(a*a, axis=0)*np.mean(b*b, axis=0)), 1e-12))
    power = abs(np.fft.rfft(residual * np.hanning(len(x))[:, None], axis=0)) ** 2
    power[0] = 0
    power /= np.maximum(power.sum(axis=0), 1e-12)
    freq = np.fft.rfftfreq(len(x), 1. / rate_hz)
    for low, high in ((.1, .6), (.6, 2.), (2., 5.), (5., 10.)):
        signals.append(power[(freq >= low) & (freq < high)].sum(axis=0))
    signals += [-(power * np.log(np.maximum(power, 1e-12))).sum(axis=0) / np.log(len(power)),
                power.max(axis=0)]
    energy = np.mean(delta ** 2, axis=1)
    energy /= max(float(energy.mean()), 1e-12)
    temporal = [v.mean() for v in np.array_split(energy, 10)]
    # A single argmax is discontinuous when periodic peaks tie: rounding from
    # gain/channel permutation could move it across most of the recording.
    centroid = np.dot(energy, np.arange(len(energy)) / len(energy)) / max(float(energy.sum()), 1e-12)
    extras = [*np.log1p(np.quantile(energy, [.5, .9, .99, 1.])), centroid,
              np.log((energy[-len(energy)//3:].mean()+1e-6) / (energy[:len(energy)//3].mean()+1e-6)),
              np.mean(np.mean(residual, axis=1)**2) / max(float(variance.mean()), 1e-12),
              np.median(abs(relative[-len(x)//5:].mean(axis=0)-relative[:len(x)//5].mean(axis=0)))]
    features = np.r_[*[np.quantile(v, QUANTILES) for v in signals], temporal, extras].astype(np.float32)
    if features.shape != (len(FEATURE_NAMES),) or not np.isfinite(features).all():
        raise ValueError("invalid research features")
    return features


def channel_normalize(values):
    """Per-current-window channel normalization; fixed ESP32 52-channel contract."""
    x = np.asarray(values, dtype=np.float32)
    if x.ndim != 3 or x.shape[1:] != (500, 52) or not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError("measured [n,500,52] amplitude required")
    relative = x / np.maximum(x.mean(axis=1, keepdims=True), 1e-6) - 1.
    return np.clip(relative / np.maximum(relative.std(axis=1, keepdims=True), .01), -5., 5.).astype(np.float32)

"""Serializable causal preprocessing shared by training and edge inference."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields

import numpy as np

from .decoder import FEATURE_COUNT


@dataclass(frozen=True)
class PreprocessConfig:
    target_rate_hz: float = 100.0
    max_gap_s: float = 0.05
    hampel_window: int = 7
    hampel_sigma: float = 3.0
    lowpass_hz: float = 10.0
    baseline_warmup_frames: int = 25
    baseline_alpha: float = 0.002
    baseline_epsilon: float = 1e-3
    motion_energy_threshold: float = 0.02
    capture_profile_hash: str = ""

    def __post_init__(self) -> None:
        if self.target_rate_hz <= 0 or self.max_gap_s <= 0 or self.lowpass_hz <= 0:
            raise ValueError("preprocessing rates and gaps must be positive")
        if self.hampel_window < 1 or self.hampel_sigma <= 0 or self.baseline_warmup_frames < 1:
            raise ValueError("preprocessing windows and thresholds must be positive")
        if not 0 < self.baseline_alpha <= 1 or self.baseline_epsilon <= 0:
            raise ValueError("baseline parameters are invalid")

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def to_json(self) -> dict[str, object]:
        return {**asdict(self), "hash": self.hash}

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> "PreprocessConfig":
        names = {field.name for field in fields(cls)}
        config = cls(**{name: payload[name] for name in names if name in payload})
        expected = payload.get("hash")
        if expected is not None and expected != config.hash:
            raise ValueError("preprocessing configuration hash mismatch")
        return config


class CausalPreprocessor:
    def __init__(self, config: PreprocessConfig):
        self.config = config

    def transform(self, values: np.ndarray, times: np.ndarray) -> np.ndarray:
        resampled, _ = self.transform_with_times(values, times)
        return resampled

    def transform_with_times(self, values: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values, times = self._validate(values, times)
        grid = self._grid(times)
        # Zero-order hold is causal: no future packet changes an earlier output.
        source_indices = np.searchsorted(times, grid, side="right") - 1
        # Hold the most recent measured packet; this is causal and never
        # extrapolates beyond the last timestamp validated above.
        resampled = values[source_indices]
        filtered = self._hampel(resampled)
        filtered = self._lowpass(filtered)
        return self._normalize(filtered), grid

    def window(self, values: np.ndarray, times: np.ndarray, length: int, *, centered: bool) -> tuple[np.ndarray, np.ndarray]:
        processed, grid = self.transform_with_times(values, times)
        if not isinstance(length, (int, np.integer)) or isinstance(length, bool) or length <= 0 or len(processed) < length:
            raise ValueError("recording cannot provide the requested preprocessed window")
        start = (len(processed) - length) // 2 if centered else len(processed) - length
        return processed[start : start + length], grid[start : start + length]

    def _validate(self, values: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        values = np.asarray(values, dtype=np.float32)
        times = np.asarray(times, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != FEATURE_COUNT or times.shape != (len(values),) or len(values) < 2:
            raise ValueError("preprocessing requires values [time,52] with matching timestamps")
        deltas = np.diff(times)
        if not np.isfinite(values).all() or not np.isfinite(times).all():
            raise ValueError("preprocessing values and timestamps must be finite")
        if np.any(deltas <= 0) or np.any(deltas > self.config.max_gap_s):
            raise ValueError("timestamps are non-monotonic or exceed the maximum packet gap")
        return values, times

    def _grid(self, times: np.ndarray) -> np.ndarray:
        count = int(np.floor((times[-1] - times[0]) * self.config.target_rate_hz + 1e-7)) + 1
        grid = times[0] + np.arange(count, dtype=np.float64) / self.config.target_rate_hz
        if len(grid) < 2:
            raise ValueError("timestamps cannot provide two resampled frames")
        return grid

    def _hampel(self, values: np.ndarray) -> np.ndarray:
        output = values.copy()
        for index in range(self.config.hampel_window, len(values)):
            history = output[index - self.config.hampel_window : index]
            median = np.median(history, axis=0)
            mad = np.median(np.abs(history - median), axis=0)
            limit = self.config.hampel_sigma * 1.4826 * mad
            deviation = np.abs(values[index] - median)
            # A flat history only rejects a jump once it exceeds a small
            # relative floor; ordinary motion is left for grouped validation.
            floor = self.config.hampel_sigma * np.maximum(np.abs(median) * 0.05, self.config.baseline_epsilon)
            outlier = deviation > np.maximum(limit, floor)
            output[index, outlier] = median[outlier]
        return output

    def _lowpass(self, values: np.ndarray) -> np.ndarray:
        step = 1.0 / self.config.target_rate_hz
        alpha = step / (step + 1.0 / (2.0 * np.pi * self.config.lowpass_hz))
        output = np.empty_like(values)
        output[0] = values[0]
        for index in range(1, len(values)):
            output[index] = output[index - 1] + alpha * (values[index] - output[index - 1])
        return output

    def _normalize(self, values: np.ndarray) -> np.ndarray:
        output = np.empty_like(values)
        baseline = values[0].copy()
        for index, value in enumerate(values):
            output[index] = (value - baseline) / np.maximum(np.abs(baseline), self.config.baseline_epsilon)
            rate = 1.0 / (index + 1) if index < self.config.baseline_warmup_frames else self.config.baseline_alpha
            baseline = (1 - rate) * baseline + rate * value
        return output

    @staticmethod
    def motion_energy(values: np.ndarray) -> float:
        values = np.asarray(values, dtype=np.float32)
        return float(np.mean(np.square(np.diff(values, axis=0)))) if len(values) > 1 else 0.0

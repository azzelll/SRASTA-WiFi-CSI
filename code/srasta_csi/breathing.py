"""Quality-gated SVD/FFT respiratory-motion estimate; not a medical diagnosis."""
from __future__ import annotations

import time
import threading
from collections import deque

import numpy as np


class BreathingMonitor:
    def __init__(self, duration_s: float = 30.0):
        self.duration_s = duration_s
        self.frames = deque(maxlen=4000)
        self.bpm: float | None = None
        self.quality = 0
        self.reason = "Mengumpulkan sinyal saat tubuh diam"
        self.last_update = 0.0
        self.lock = threading.RLock()
        self.generation = 0

    def reset(self) -> None:
        with self.lock:
            self.frames.clear()
            self.bpm, self.quality = None, 0
            self.reason = "Mengumpulkan sinyal saat tubuh diam"
            self.generation += 1

    def add(self, amplitude: np.ndarray, timestamp_s: float) -> None:
        with self.lock:
            if self.frames and (timestamp_s <= self.frames[-1][0] or timestamp_s - self.frames[-1][0] > 0.15):
                self.reset()
            self.frames.append((timestamp_s, amplitude.copy()))
            while self.frames and timestamp_s - self.frames[0][0] > self.duration_s + 1:
                self.frames.popleft()

    def update(self, motion_energy: float, motion_threshold: float) -> None:
        if motion_energy >= motion_threshold:
            with self.lock:
                self.reset()
                self.reason = "Gerakan tubuh terlalu besar"
            return
        now = time.monotonic()
        if now - self.last_update < 5:
            return
        self.last_update = now
        with self.lock:
            if len(self.frames) < 100 or self.frames[-1][0] - self.frames[0][0] < self.duration_s:
                return
            rows = list(self.frames)
            generation = self.generation
        times = np.asarray([r[0] for r in rows])
        values = np.stack([r[1] for r in rows])
        bpm, quality = estimate_breathing(values, times)
        with self.lock:
            if generation == self.generation:
                self.bpm, self.quality = bpm, quality
                self.reason = "Estimasi SVD-FFT" if bpm is not None else "Periodisitas belum cukup andal"


def estimate_breathing(values: np.ndarray, times: np.ndarray) -> tuple[float | None, int]:
    """Use actual times, detrend, SVD, and consistent peaks in both half windows."""
    if values.ndim != 2 or values.shape[1] != 52 or len(times) != len(values) or len(times) < 100:
        return None, 0
    gaps = np.diff(times)
    if not np.isfinite(values).all() or not np.isfinite(times).all() or np.any(gaps <= 0) or np.max(gaps) > 0.15 or times[-1] - times[0] < 30:
        return None, 0
    grid = np.arange(times[0], times[-1], 0.1)  # 10 Hz, no extrapolation/padding.
    samples = np.column_stack([np.interp(grid, times, values[:, i]) for i in range(52)])
    t = np.arange(len(grid), dtype=float)
    design = np.column_stack([t, np.ones_like(t)])
    samples -= design @ np.linalg.lstsq(design, samples, rcond=None)[0]
    if float(np.std(samples)) < 1e-5:
        return None, 0
    u, singular, _ = np.linalg.svd(samples, full_matrices=False)
    signal = u[:, 0] * singular[0]
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) ** 2
    frequencies = np.fft.rfftfreq(len(signal), 0.1)
    band = (frequencies >= 0.1) & (frequencies <= 0.6)
    positions = np.flatnonzero(band)
    peak = int(positions[np.argmax(spectrum[band])])
    concentration = float(spectrum[max(peak - 1, 0):peak + 2].sum() / max(spectrum[1:].sum(), 1e-12))
    dominance = float(singular[0] ** 2 / max(np.sum(singular ** 2), 1e-12))
    half_peaks = []
    for half in np.array_split(signal, 2):
        freq = np.fft.rfftfreq(len(half), 0.1)
        power = np.abs(np.fft.rfft(half * np.hanning(len(half)))) ** 2
        indices = np.flatnonzero((freq >= 0.1) & (freq <= 0.6))
        half_peaks.append(float(freq[indices[np.argmax(power[indices])]]))
    quality = round(100 * min(concentration, dominance))
    if concentration < 0.65 or dominance < 0.5 or abs(half_peaks[0] - half_peaks[1]) > 0.08:
        return None, min(quality, 49)
    return round(float(frequencies[peak] * 60), 1), quality

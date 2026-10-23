"""Fixed ESP32-S3 I/Q decoder with declared physical frequency ordering."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


RAW_COMPLEX_COUNT = 64
RAW_IQ_BYTE_COUNT = 128
USABLE_SUBCARRIER_INDICES = np.asarray(list(range(6, 32)) + list(range(33, 59)), dtype=np.int64)
FEATURE_COUNT = int(len(USABLE_SUBCARRIER_INDICES))
SUBCARRIER_ORDERS = ("centered", "esp_idf_native")


def decode_iq_to_amplitude(iq_bytes: Sequence[int] | np.ndarray, *, first_word_invalid: bool = False, subcarrier_order: str = "centered") -> np.ndarray:
    """Decode `[imaginary, real]` signed-int8 pairs into a fixed 52-vector."""
    if subcarrier_order not in SUBCARRIER_ORDERS:
        raise ValueError("subcarrier order must be explicitly centered or esp_idf_native")
    raw = np.asarray(iq_bytes)
    if raw.shape != (RAW_IQ_BYTE_COUNT,):
        raise ValueError("ESP32-S3 CSI payload must contain exactly 128 I/Q bytes")
    if not np.issubdtype(raw.dtype, np.integer) or np.any(raw < -128) or np.any(raw > 127):
        raise ValueError("I/Q bytes must be signed int8 values in [-128, 127]")
    iq = raw.astype(np.float32, copy=False).reshape(RAW_COMPLEX_COUNT, 2)
    amplitude = np.hypot(iq[:, 0], iq[:, 1])
    if first_word_invalid:
        # ESP-IDF marks the first four bytes (two complex positions) invalid.
        # Mask in the original byte order before any frequency-coordinate map.
        # Never delete invalid positions or shift the remaining payload pairs.
        amplitude[:2] = 0.0
    if subcarrier_order == "esp_idf_native":
        # ESP-IDF HT20 LLTF: 0..31,-32..-1. CSI-Bench: -32..31.
        # This exact 64-bin permutation maps physical frequencies; it is not
        # inferred from zeros, a resize, padding, or a replacement channel mask.
        amplitude = np.fft.fftshift(amplitude)
    selected = amplitude[USABLE_SUBCARRIER_INDICES]
    if selected.shape != (FEATURE_COUNT,):
        raise AssertionError("fixed CSI mask did not produce 52 features")
    return selected.astype(np.float32, copy=False)

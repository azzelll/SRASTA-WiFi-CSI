"""Recording diagnostics, deliberately separate from event-level acceptance."""
from __future__ import annotations

from dataclasses import replace
import numpy as np

from .preprocess import CausalPreprocessor, PreprocessConfig


def preprocess_trace(raw, times, config: PreprocessConfig):
    """Observe the exact shared stages without changing their behavior."""
    processor = CausalPreprocessor(config)
    raw, times = processor._validate(raw, times)
    grid = processor._grid(times)
    held = raw[np.searchsorted(times, grid, side="right") - 1]
    hampel = processor._hampel(held)
    lowpass = processor._lowpass(hampel)
    unbounded = CausalPreprocessor(replace(config, normalized_clip=None))._normalize(lowpass)
    processed = processor._normalize(lowpass)
    stats = {
        "hampel_replaced_fraction": float(np.mean(hampel != held)),
        "clipped_fraction": float(np.mean(unbounded != processed)),
        "motion_energy": processor.motion_energy(processed),
        "raw_derivative_energy": processor.motion_energy(held),
        "hampel_derivative_energy": processor.motion_energy(hampel),
    }
    return {"held": held, "processed": processed, "times": grid, "stats": stats}


def recording_decision(label, probability, energy, fall_threshold, motion_threshold):
    if label not in (0, 1) or not np.isfinite([probability, energy, fall_threshold, motion_threshold]).all():
        raise ValueError("decision needs a binary label and finite inputs")
    if not 0 <= probability <= 1 or not 0 <= fall_threshold <= 1 or min(energy, motion_threshold) < 0:
        raise ValueError("invalid probability, threshold or motion energy")
    classifier = int(probability >= fall_threshold)
    gate = int(energy >= motion_threshold)
    trigger = classifier * gate
    outcome = ("TP" if trigger else "FN") if label else ("FP" if trigger else "TN")
    reason = ("classifier_and_motion_gate" if not classifier and not gate else
              "classifier" if not classifier else "motion_gate") if label and not trigger else "none"
    return {"classifier_prediction": classifier, "motion_gate_pass": gate,
            "trigger_prediction": trigger, "outcome": outcome, "missed_by": reason}


def quantization_saturation(window, quantization):
    scale, zero = quantization
    if scale <= 0:
        raise ValueError("quantization scale must be positive")
    integers = np.round(np.asarray(window) / scale + zero)
    return float(np.mean((integers < -128) | (integers > 127)))

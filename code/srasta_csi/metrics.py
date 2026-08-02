"""Classification and explicit unavailable-metric reporting."""

from __future__ import annotations

import numpy as np


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, object]:
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

    p, r, f, support = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1], zero_division=0)
    return {
        "precision": {"nonfall": float(p[0]), "fall": float(p[1])},
        "recall": {"nonfall": float(r[0]), "fall": float(r[1])},
        "f1": {"nonfall": float(f[0]), "fall": float(f[1])},
        "macro_f1": float(np.mean(f)),
        "support": {"nonfall": int(support[0]), "fall": int(support[1])},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }


def unavailable_event_metrics() -> dict[str, dict[str, object]]:
    reason = "Curated H5 clips lack continuous packet timestamps, onset/offset, inactivity annotations, and nonfall exposure duration."
    return {name: {"value": None, "status": "not_available", "reason": reason} for name in (
        "event_recall", "event_precision", "event_f1", "false_alerts_per_hour", "packet_drop_rate",
        "suspected_fall_latency_ms", "confirmed_fall_latency_ms",
    )}

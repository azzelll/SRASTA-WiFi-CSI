"""Motion/inactivity on fresh measurements and explicit occupancy evidence."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class InactivityMonitor:
    threshold_s: float = 60.
    max_gap_s: float = 1.
    presence: bool | None = None
    moving: bool | None = None
    inactive: bool | None = None
    stationary_since_s: float | None = None
    last_sample_s: float | None = None

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in (self.threshold_s, self.max_gap_s)):
            raise ValueError("inactivity thresholds must be finite and positive")

    def reset(self):
        self.presence = self.moving = self.inactive = None
        self.stationary_since_s = self.last_sample_s = None

    def observe(self, *, present: bool | None, moving: bool, timestamp_s: float):
        if present is not None and type(present) is not bool or type(moving) is not bool or not math.isfinite(timestamp_s):
            raise ValueError("explicit boolean evidence and finite receiver time required")
        if self.last_sample_s is not None:
            delta = timestamp_s - self.last_sample_s
            if delta <= 0 or delta > self.max_gap_s:
                self.reset()
        self.last_sample_s = timestamp_s
        self.presence, self.moving = present, moving
        if present is None:
            self.stationary_since_s, self.inactive = None, None
        elif not present or moving:
            self.stationary_since_s, self.inactive = None, False
        else:
            if self.stationary_since_s is None:
                self.stationary_since_s = timestamp_s
            self.inactive = timestamp_s - self.stationary_since_s >= self.threshold_s
        return self.status()

    def status(self):
        return {"presence": "unknown" if self.presence is None else "present" if self.presence else "empty", "motion": "unknown" if self.moving is None else "moving" if self.moving else "still", "inactive": self.inactive, "stationary_duration_s": None if self.stationary_since_s is None else self.last_sample_s - self.stationary_since_s, "inactivity_threshold_s": self.threshold_s, "breathing_condition": None}

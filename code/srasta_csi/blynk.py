"""Fail-closed Blynk contract; external delivery is disabled for this milestone."""

from __future__ import annotations

import time


class DisabledBlynkAdapter:
    enabled = False

    def __init__(self, *, min_interval_s: float = 30.0):
        if min_interval_s <= 0:
            raise ValueError("alert rate limit must be positive")
        self.min_interval_s = min_interval_s
        self.disabled_attempts = 0
        self.rate_limited_attempts = 0
        self._last_attempt_s: float | None = None

    def send(self, *_args, now_s: float | None = None, **_kwargs) -> bool:
        now_s = time.monotonic() if now_s is None else float(now_s)
        if self._last_attempt_s is not None and now_s - self._last_attempt_s < self.min_interval_s:
            self.rate_limited_attempts += 1
            return False
        self._last_attempt_s = now_s
        self.disabled_attempts += 1
        return False

    def status(self) -> dict[str, int | bool | float]:
        return {
            "enabled": False,
            "network_delivery_available": False,
            "min_interval_s": self.min_interval_s,
            "disabled_attempts": self.disabled_attempts,
            "rate_limited_attempts": self.rate_limited_attempts,
        }

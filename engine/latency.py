"""Per-leg latency instrumentation — measures the full order round-trip.

Legs:
  signal   → strategy emitted the order
  gateway  → time since last market tick (feed freshness)
  router   → broker submit → ACK
  fill     → ACK → FILLED
  total    → signal → FILLED (end-to-end)
"""
from __future__ import annotations

import time
from collections import deque
from statistics import mean


class LatencyTracker:
    def __init__(self, window: int = 200):
        self.window = window
        self._samples: deque[dict] = deque(maxlen=window)

    def record(self, signal_ts: float, ack_ts: float | None,
               fill_ts: float | None, gateway_age: float | None) -> dict:
        row = {
            "ts": time.time(),
            "signal_to_ack_ms": round((ack_ts - signal_ts) * 1000, 3) if ack_ts else None,
            "ack_to_fill_ms": round((fill_ts - ack_ts) * 1000, 3) if (ack_ts and fill_ts) else None,
            "total_ms": round((fill_ts - signal_ts) * 1000, 3) if fill_ts else None,
            "gateway_age_ms": round(gateway_age * 1000, 3) if gateway_age is not None else None,
        }
        self._samples.append(row)
        return row

    def summary(self) -> dict:
        if not self._samples:
            return {"samples": 0}
        def avg(key):
            vals = [s[key] for s in self._samples if s.get(key) is not None]
            return round(mean(vals), 3) if vals else None
        return {
            "samples": len(self._samples),
            "signal_to_ack_ms": avg("signal_to_ack_ms"),
            "ack_to_fill_ms": avg("ack_to_fill_ms"),
            "total_ms": avg("total_ms"),
            "gateway_age_ms": avg("gateway_age_ms"),
            "last": self._samples[-1],
        }

    def reset(self):
        self._samples.clear()

"""Observed-rain features for obs v8 (no forecast, so no leakage): what has already fallen."""
from __future__ import annotations
import numpy as np

RAIN_FEATURE_NAMES = ["rain_now", "rain_1h", "rain_3h", "rain_6h", "rain_24h", "hours_since_start", "rain_peak"]
RAIN_SCALES = np.array([10.0, 25.0, 50.0, 75.0, 150.0, 24.0, 10.0])      # mm / hours scales -> O(1) features


def rain_features(rain_mm_per_15min, n_applied: int) -> np.ndarray:
    """n_applied = number of 15-min intervals already applied to the model (env: max(self.t - 1, 0))."""
    r = np.asarray(rain_mm_per_15min, float)
    n = int(min(max(n_applied, 0), len(r)))
    if n == 0:
        return np.zeros(len(RAIN_SCALES), np.float32)
    seen = r[:n]
    wet = np.flatnonzero(seen > 0)
    since = (n - wet[0]) * 0.25 if wet.size else 0.0
    f = np.array([seen[-1], seen[-4:].sum(), seen[-12:].sum(), seen[-24:].sum(), seen[-96:].sum(), since, seen.max()])
    return (f / RAIN_SCALES).astype(np.float32)

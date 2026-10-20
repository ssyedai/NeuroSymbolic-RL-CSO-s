"""Detroit IDF helpers (fit used in the PFSMC literature) and return-period language.

i [in/h] = 38.4164 * T**0.2082 / (12.3258 + D)**0.8405,  T in years, D in minutes.
The fit is reliable only up to roughly 100 yr; for larger T use NOAA Atlas 14 values (research/scenarios.py, pfds).
Return period T and annual exceedance probability (AEP) are related by AEP = 1/T (for T >= ~10 they are
practically identical). A "1000-yr event" is defined PER DURATION: a storm can be 1000-yr at 1 h and only 50-yr at 24 h.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

_A, _B, _C, _D = 38.4164, 0.2082, 12.3258, 0.8405
DURATIONS = {60: "max1h_mm", 180: "max3h_mm", 360: "max6h_mm", 1440: "max24h_mm"}


def idf_i(T, D_min):
    """Design intensity in in/h."""
    return _A * np.power(T, _B) / np.power(_C + np.asarray(D_min, float), _D)


def idf_depth_mm(T, D_min):
    """Design depth in mm for return period T (yr) and duration D_min (min)."""
    return idf_i(T, D_min) * np.asarray(D_min, float) / 60.0 * 25.4


def t_eq(depth_mm, D_min):
    """Equivalent return period (yr) of a depth over a duration. Returns 0 for zero depth."""
    d = np.maximum(np.asarray(depth_mm, float), 0.0)
    i = d / 25.4 * 60.0 / float(D_min)
    return np.power(i * np.power(_C + float(D_min), _D) / _A, 1.0 / _B)


def aep(T):
    return 1.0 / float(T)


def prob_at_least_once(T, years):
    """P(at least one exceedance in `years` years) = 1 - (1 - 1/T)**years."""
    return 1.0 - (1.0 - 1.0 / float(T)) ** float(years)


def classify(ev: pd.DataFrame) -> pd.DataFrame:
    """Add T_eq (max over >=1 h durations), a 15-min spike flag and a severity class to an events table."""
    ev = ev.copy()
    for D, c in DURATIONS.items():
        ev[f"T{D}"] = t_eq(ev[c].clip(lower=0.0), D)
    ev["T_eq"] = ev[[f"T{D}" for D in DURATIONS]].max(axis=1)
    ev["spike_flag"] = (ev["max15_mm"] / ev["total_mm"].clip(lower=1e-9) > 0.75) & (ev["total_mm"] > 20)
    ev["severity"] = pd.cut(ev["T_eq"], [-1, 1, 2, 5, 10, 25, np.inf],
                            labels=["<1", "1-2", "2-5", "5-10", "10-25", ">=25"])
    return ev

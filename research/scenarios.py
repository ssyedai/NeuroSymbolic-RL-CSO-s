"""Scenario factory: amplify REAL hyetographs (shape preserved, one multiplier k per event).

Two ways to choose k (both keep the temporal pattern of the real storm):
  family "T": return-period anchored  - k so the anchor-duration depth (default 6 h) equals the design depth of T years.
  family "C": CSO-onset anchored      - k = m * k_onset, where k_onset is the smallest amplification at which the
                                        network (true native control) starts to spill. Guarantees CSO exists.
Unscaled events are family "R" (provenance "observed"); amplified ones have provenance "scaled_real".
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from research.idf import idf_depth_mm, t_eq

N_STEPS = 288
ANCHOR_MIN = 360


def roll_max(depth15, steps: int) -> float:
    x = np.asarray(depth15, float)
    if len(x) < steps:
        return float("nan")
    return float(pd.Series(x).rolling(steps).sum().max())


def target_depth(T, anchor_min=ANCHOR_MIN, pfds: pd.DataFrame | None = None) -> float:
    """Atlas 14 table (index = duration in min, columns = ARI in yr, values in mm) when given; else the Detroit IDF fit."""
    if pfds is not None and T in pfds.columns:
        return float(pfds.loc[anchor_min, T])
    if T > 100:
        raise ValueError(f"T={T} yr needs an Atlas 14 table (pfds); the IDF fit is extrapolated beyond ~100 yr")
    return float(idf_depth_mm(T, anchor_min))


def severity_equiv(depth15) -> dict:
    """T_eq (yr) of the hyetograph at 1 h, 6 h and 24 h (IDF fit; indicative above ~100 yr)."""
    return {D: float(t_eq(roll_max(depth15, D // 15), D)) for D in (60, 360, 1440)}


def shape_spread(T_by_dur: dict) -> float:
    v = [max(x, 1e-9) for x in T_by_dur.values()]
    return max(v) / min(v)


def _variant(parent, family, rung, k, depth, **extra):
    d = np.asarray(depth, float) * k
    T_by = severity_equiv(d)
    return dict(variant_id=f"{parent['storm_id']}__{rung}", parent=parent["storm_id"], year=parent.get("year"),
                family=family, rung=rung, k=float(k), depth=d, T_by_dur=T_by, T_anchor=T_by[360], **extra)


def build_T_variants(parents, ladder, anchor_min=ANCHOR_MIN, k_lo=0.67, k_hi=4.0, min_anchor_mm=15.0,
                     max_spread=10.0, pfds=None):
    out, rej = [], []
    for p in parents:
        d = np.asarray(p["depth"], float)
        base = roll_max(d, anchor_min // 15)
        if not np.isfinite(base) or base < min_anchor_mm:
            rej.append(dict(parent=p["storm_id"], rung="*", reason="below_min_anchor_depth")); continue
        for T in ladder:
            rung = f"T{T:g}"
            try:
                k = target_depth(T, anchor_min, pfds) / base
            except ValueError:
                rej.append(dict(parent=p["storm_id"], rung=rung, reason="needs_atlas14_table")); continue
            if not (k_lo <= k <= k_hi):
                rej.append(dict(parent=p["storm_id"], rung=rung, reason=f"k_out_of_range({k:.2f})")); continue
            v = _variant(p, "T", rung, k, d, T_target=float(T), onset_mult=float("nan"))
            if shape_spread(v["T_by_dur"]) > max_spread:
                rej.append(dict(parent=p["storm_id"], rung=rung, reason="implausible_shape")); continue
            out.append(v)
    return out, rej


def build_C_variants(parents, onset: dict, mults=(1.0, 1.5, 2.0, 3.0), k_cap=12.0):
    """onset: {storm_id: k_onset or None}. k = m * k_onset (so rung C1.0 sits exactly at the network's CSO threshold)."""
    out, rej = [], []
    for p in parents:
        ko = onset.get(p["storm_id"])
        if ko is None or not np.isfinite(ko):
            rej.append(dict(parent=p["storm_id"], rung="C*", reason="no_cso_onset_within_k_cap")); continue
        for m in mults:
            k = ko * m
            rung = f"C{m:g}"
            if k > k_cap:
                rej.append(dict(parent=p["storm_id"], rung=rung, reason=f"k_over_cap({k:.2f})")); continue
            out.append(_variant(p, "C", rung, k, p["depth"], T_target=float("nan"), onset_mult=float(m), k_onset=float(ko)))
    return out, rej


def build_F_variants(parents, factors=(2.0,)):
    """Flat multiplier on every event (what you used so far). Kept as an ABLATION diet, not the default."""
    out = []
    for p in parents:
        for k in factors:
            out.append(_variant(p, "F", f"F{k:g}", k, p["depth"], T_target=float("nan"), onset_mult=float("nan")))
    return out, []


def eligible_for_training(v: dict, train_max_T: float) -> bool:
    """Training ceiling on the anchor (6 h) equivalent return period. Default policy: 100. D3 diet: 1000."""
    return bool(np.isfinite(v["T_anchor"]) and v["T_anchor"] <= train_max_T)


def assign_parent_splits(parents, val_years, test_years) -> dict:
    """Split by calendar year of the PARENT; every amplified child inherits it (no leakage)."""
    out = {}
    for p in parents:
        y = p.get("year")
        out[p["storm_id"]] = "test" if y in set(test_years) else "val" if y in set(val_years) else "train"
    return out

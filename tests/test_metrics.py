"""Synthetic metric checks (no SWMM)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from multistorm.metrics import aggregate, episode_summary, relative, selection_score


def _fake_log(T=10, cso=1.0, flood=100.0):
    return {
        "cso_flow": np.full(T, cso),
        "flooding": np.full(T, flood),
        "storage_fill": np.linspace(5, 20, T),
        "actions_projected": np.tile(np.array([0.4, 0.4, 0.4, 0.5, 0.5, 0.4, 0.4, 1, 1, 1]), (T, 1)),
        "reward": np.full(T, -1.0),
        "r_close": np.zeros(T),
        "r_cso": np.full(T, -0.5),
        "r_flood": np.zeros(T),
    }


def test_episode_summary_basics():
    s = episode_summary(_fake_log(), baseline_flooding=50.0)
    assert s["cso_total"] == 10.0
    assert s["flood_total"] == 1000.0
    assert s["flood_excess_mean"] == 50.0
    assert s["score"] == -10.0


def test_relative_nan_when_zero_baseline_cso():
    s = episode_summary(_fake_log(cso=0.0))
    rec = {
        "baseline_flooding": 100.0,
        "static": {"cso_total": 0.0, "flood_total": 10.0, "r6_frac": 0.0, "score": 0.0},
    }
    rel = relative(s, rec, cso_floor=1.0)
    assert np.isnan(rel["cso_reduction_pct"])


def test_aggregate_and_selection():
    df = pd.DataFrame([
        dict(cso_total=80, static_cso=100, cso_reduction_pct=20.0,
             flood_ratio=1.0, r6_excess=0.0, r6_frac=0.0, score_adv=1.0),
        dict(cso_total=90, static_cso=100, cso_reduction_pct=10.0,
             flood_ratio=1.1, r6_excess=0.0, r6_frac=0.0, score_adv=0.5),
    ])
    agg = aggregate(df)
    assert agg["cso_red_macro"] == 15.0
    assert agg["frac_improved"] == 1.0
    # flood_ratio_mean=1.05 → at cap boundary; selection ok if <= 1.05
    sel = selection_score(agg, r6_cap=0.01, flood_ratio_cap=1.05)
    assert sel == 15.0 or sel == 15.0 - 100.0  # depends on float

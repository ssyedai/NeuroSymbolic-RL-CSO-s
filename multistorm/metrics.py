# multistorm/metrics.py
from __future__ import annotations
import numpy as np
import pandas as pd

FLOOD_THRESHOLD = 9500.0   # R6 (frozen KB value)
STORAGE_R1 = 0.85
STORAGE_CLOSE = 0.70


def episode_summary(L: dict, baseline_flooding: float | None = None,
                    flood_threshold: float = FLOOD_THRESHOLD) -> dict:
    cso = np.asarray(L["cso_flow"], float)
    fl = np.asarray(L["flooding"], float)
    fill = np.asarray(L["storage_fill"], float)
    acts = np.asarray(L["actions_projected"], float)
    out = dict(
        steps=len(cso),
        score=float(np.sum(L["reward"])),
        cso_total=float(cso.sum()), cso_peak=float(cso.max()) if len(cso) else 0.0,
        cso_active_frac=float((cso > 0).mean()) if len(cso) else 0.0,
        flood_total=float(fl.sum()), flood_mean=float(fl.mean()) if len(fl) else 0.0,
        flood_peak=float(fl.max()) if len(fl) else 0.0,
        r6_frac=float((fl > flood_threshold).mean()) if len(fl) else 0.0,
        fill_min=float(fill.min()) if len(fill) else 0.0,
        fill_max=float(fill.max()) if len(fill) else 0.0,
        r1_frac=float((fill >= STORAGE_R1 * 35.0).mean()) if len(fill) else 0.0,
        close_frac=float((fill < STORAGE_CLOSE * 35.0).mean()) if len(fill) else 0.0,
    )
    # Note: fill thresholds use absolute depth-sum (capacity 35m) matching Trial 7 KB.
    if baseline_flooding is not None:
        out["flood_excess_mean"] = float(np.maximum(fl - baseline_flooding, 0).mean()) if len(fl) else 0.0
    if acts.ndim == 2 and acts.shape[1] >= 7:
        for k in range(7):
            out[f"gate{k}_mean"] = float(acts[:, k].mean())
    for k in ("r_close", "r_cso", "r_flood"):
        if k in L:
            out[f"sum_{k}"] = float(np.sum(L[k]))
    # Opt-in environment supplies integrated volumes, explicitly tagged in m3.
    out.update(L.get("accounting_summary", {}))
    return out


def relative(s: dict, rec: dict, cso_floor: float = 1.0) -> dict:
    """Compare an episode summary to the per-storm reference records."""
    b = rec["static"]
    o = dict(static_cso=b["cso_total"], static_flood_total=b["flood_total"],
             static_r6_frac=b["r6_frac"], baseline_flooding=rec["baseline_flooding"])
    o["cso_delta"] = s["cso_total"] - b["cso_total"]
    o["cso_reduction_pct"] = (100 * (b["cso_total"] - s["cso_total"]) / b["cso_total"]
                              if b["cso_total"] > cso_floor else float("nan"))
    o["flood_ratio"] = s["flood_total"] / b["flood_total"] if b["flood_total"] > 0 else float("nan")
    o["r6_excess"] = max(s["r6_frac"] - b["r6_frac"], 0.0)
    o["score_adv"] = s["score"] - b["score"]
    n = rec.get("native")
    if n and n["cso_total"] > cso_floor:
        o["native_cso"] = n["cso_total"]
        o["cso_reduction_vs_native_pct"] = 100 * (n["cso_total"] - s["cso_total"]) / n["cso_total"]
    return o


def aggregate(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["cso_reduction_pct"])
    micro = (100 * (d.static_cso.sum() - d.cso_total.sum()) / d.static_cso.sum()
             if len(d) and d.static_cso.sum() > 0 else float("nan"))
    g = lambda col, f: float(f(df[col])) if col in df and len(df) else float("nan")
    return dict(
        n_storms=len(df), n_scored=len(d),
        cso_red_macro=float(d.cso_reduction_pct.mean()) if len(d) else float("nan"),
        cso_red_median=float(d.cso_reduction_pct.median()) if len(d) else float("nan"),
        cso_red_std=float(d.cso_reduction_pct.std(ddof=0)) if len(d) else float("nan"),
        cso_red_worst=float(d.cso_reduction_pct.min()) if len(d) else float("nan"),
        cso_red_micro=float(micro),
        frac_improved=float((d.cso_reduction_pct > 0).mean()) if len(d) else float("nan"),
        flood_ratio_mean=g("flood_ratio", np.nanmean), flood_ratio_max=g("flood_ratio", np.nanmax),
        flood_regress_frac=float((df.flood_ratio > 1.05).mean()) if "flood_ratio" in df else float("nan"),
        r6_excess_mean=g("r6_excess", np.mean), r6_frac_max=g("r6_frac", np.max),
        score_adv_mean=g("score_adv", np.mean),
    )


def selection_score(agg: dict, r6_cap: float = 0.01, flood_ratio_cap: float = 1.05) -> float:
    """Primary = macro CSO reduction on validation storms. Safety caps demote infeasible models."""
    s = agg["cso_red_macro"]
    if s != s:
        return -1e9
    ok = agg["r6_excess_mean"] <= r6_cap and agg["flood_ratio_mean"] <= flood_ratio_cap
    return s if ok else s - 100.0

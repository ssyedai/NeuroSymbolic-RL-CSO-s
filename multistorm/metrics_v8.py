"""Per-event metrics added in v8: hindsight regret, flood non-regression, scorecard."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Legacy episode totals are sums of 15-minute endpoint flows (CFS), not volumes.
SAMPLED_CFS_SUM_TO_M3 = 900.0 * 0.028316846592


def vs_hindsight(s: dict, ref: dict, hind: dict | None, floor: float = 1.0) -> dict:
    """s/ref/hind: episode summaries (need cso_total). pct_achievable_captured = share of the achievable reduction obtained."""
    if not hind:
        return {}
    den = ref["cso_total"] - hind["cso_total"]
    return dict(pct_achievable_captured=(100.0 * (ref["cso_total"] - s["cso_total"]) / den) if den > floor else float("nan"),
                regret_vs_hindsight=s["cso_total"] - hind["cso_total"])


def flood_nonregression(s: dict, ref: dict, rel_tol=0.02, abs_tol=10.0) -> dict:
    """ref = TRUE native record. Non-regression: never worse than the reference (small tolerance).
    zero-when-feasible: if the reference does not flood, the agent must not flood either."""
    ok = s["flood_total"] <= ref["flood_total"] * (1.0 + rel_tol) + abs_tol
    ref_zero = ref["flood_total"] <= abs_tol
    return dict(flood_nonregress=bool(ok),
                flood_zero_when_feasible=bool((not ref_zero) or s["flood_total"] <= abs_tol))


def scorecard(row: dict) -> bool:
    return bool(row["flood_nonregress"] and row.get("flood_zero_when_feasible", False)
                and row["cso_delta"] <= 0 and row.get("total_overflow_nonregress", True))


def enrich(s: dict, ref: dict, hind: dict | None = None, cso_floor: float = 1.0) -> dict:
    if s.get("volume_units") != ref.get("volume_units"):
        raise ValueError("Agent and native reference use different volume units")
    if hind and s.get("volume_units") != hind.get("volume_units"):
        raise ValueError("Agent and hindsight use different volume units")
    out = flood_nonregression(s, ref)
    out["cso_delta"] = s["cso_total"] - ref["cso_total"]
    out["native_cso"] = ref["cso_total"]
    out["native_flood_total"] = ref["flood_total"]
    out["cso_reduction_pct"] = (100.0 * -out["cso_delta"] / ref["cso_total"]
                                if ref["cso_total"] > cso_floor else float("nan"))
    out["cso_reduction_vs_native_pct"] = out["cso_reduction_pct"]
    out["flood_ratio"] = (s["flood_total"] / ref["flood_total"]
                           if ref["flood_total"] > 0 else float("nan"))
    out["reference_control"] = "native"
    # Explicitly a sampled, MONITORED volume: bypass outfalls are not logged.
    conversion = 1.0 if s.get("volume_units") == "m3" else SAMPLED_CFS_SUM_TO_M3
    out["overflow_accounting_complete"] = bool(s.get("overflow_accounting_complete", False))
    if out["overflow_accounting_complete"]:
        out["total_overflow_delta_m3"] = s["total_overflow_vol_m3"] - ref["total_overflow_vol_m3"]
        out["total_overflow_nonregress"] = out["total_overflow_delta_m3"] <= 0
        out["native_total_overflow_vol_m3"] = ref["total_overflow_vol_m3"]
    else:
        out["flood_vol_m3_sampled"] = s["flood_total"] * conversion
        out["monitored_overflow_vol_m3_sampled"] = (s["cso_total"] + s["flood_total"]) * conversion
        out["native_monitored_overflow_vol_m3_sampled"] = (ref["cso_total"] + ref["flood_total"]) * conversion
    out.update(vs_hindsight(s, ref, hind))
    out["scorecard_pass"] = scorecard(out)
    return out


def aggregate_native(df: pd.DataFrame) -> dict:
    """Native-only summaries; zero-CSO references stay in safety and micro totals.

    This is descriptive reporting, not a confidence interval. Report each
    family/rung separately and average children within parent before inference.
    """
    required = {"native_cso", "cso_total", "cso_reduction_vs_native_pct", "flood_nonregress"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing native metrics: {sorted(required - set(df.columns))}")
    d = df.loc[np.isfinite(df.cso_reduction_vs_native_pct)]
    ref = df.native_cso.sum(min_count=1)
    known = np.isfinite(df.native_cso).all() and np.isfinite(df.cso_total).all()
    macro = float(d.cso_reduction_vs_native_pct.mean()) if len(d) else float("nan")
    return dict(reference_control="native", n_storms=len(df), n_scored=len(d),
                n_parents=int(df.parent.nunique()) if "parent" in df else None,
                cso_red_macro=macro,
                cso_red_micro=float(100 * (ref - df.cso_total.sum()) / ref)
                    if known and ref > 0 else float("nan"),
                flood_nonregress_rate=float(df.flood_nonregress.eq(True).mean()),
                flood_zero_when_feasible_rate=float(df.flood_zero_when_feasible.eq(True).mean())
                    if "flood_zero_when_feasible" in df else float("nan"),
                intervention_rate=float(df.intervention_rate.mean())
                    if "intervention_rate" in df else float("nan"))

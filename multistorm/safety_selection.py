"""Validation-only checkpoint selection; safety is assessed on every event."""
from __future__ import annotations

import numpy as np
import pandas as pd


def validation_selection(df: pd.DataFrame, strict: bool = False) -> float:
    """Keep the protocol's -100 penalty, or opt into rejecting unsafe checkpoints.

    Zero-reference-CSO events have undefined reductions but must still count
    toward safety. Missing/nonfinite safety evidence is never a passing result.
    """
    required = {"cso_reduction_vs_native_pct", "flood_nonregress",
                "flood_zero_when_feasible", "intervention_rate", "split"}
    if df.empty or not required.issubset(df.columns):
        return -float("inf")
    if not df["split"].eq("val").all():
        raise ValueError("Checkpoint selection requires validation events only")
    reduction = pd.to_numeric(df["cso_reduction_vs_native_pct"], errors="coerce")
    scored = df.loc[np.isfinite(reduction)].copy()
    if scored.empty:
        return -float("inf")
    scored["cso_reduction_vs_native_pct"] = reduction.loc[scored.index]
    macro = (scored.groupby("rung")["cso_reduction_vs_native_pct"].mean().mean()
             if "rung" in scored else scored["cso_reduction_vs_native_pct"].mean())
    flood = df["flood_nonregress"].eq(True).mean()
    zero = df["flood_zero_when_feasible"].eq(True).all()
    intervention = pd.to_numeric(df["intervention_rate"], errors="coerce")
    valid = np.isfinite(intervention).all() and intervention.between(0, 1).all()
    safe = flood >= 0.95 and valid and intervention.mean() <= 0.5
    if strict:
        safe = safe and zero
        if "overflow_accounting_complete" in df and df.overflow_accounting_complete.eq(True).any():
            safe = (safe and df.overflow_accounting_complete.eq(True).all()
                    and "total_overflow_nonregress" in df
                    and df.total_overflow_nonregress.eq(True).all())
    if not safe:
        return -float("inf") if strict else float(macro) - 100.0
    return float(macro)

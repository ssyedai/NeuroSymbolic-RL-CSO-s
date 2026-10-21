# multistorm/metrics_ext.py
from __future__ import annotations

import numpy as np

CFS_TO_M3_PER_STEP = 0.028316846592 * 900.0
CSO_ON_CFS = 0.01


def count_events(active: np.ndarray, min_gap_steps: int = 24) -> int:
    idx = np.flatnonzero(active)
    if idx.size == 0:
        return 0
    return int(1 + np.sum(np.diff(idx) - 1 >= min_gap_steps))


def extended_summary(L: dict) -> dict:
    step_s = float(L.get("control_step_s", 900.0))
    volume_per_cfs_step = 0.028316846592 * step_s
    if "cso_definition" not in L and "cso_flow_35391" in L and "cso_flow_35444" in L:
        q1 = np.asarray(L["cso_flow_35391"], float)
        q2 = np.asarray(L["cso_flow_35444"], float)
        cso = q1 + q2
    else:
        cso = np.asarray(L["cso_flow"], float)
        q1 = np.asarray(L.get("cso_flow_35391", np.full_like(cso, np.nan)), float)
        q2 = np.asarray(L.get("cso_flow_35444", np.full_like(cso, np.nan)), float)
    pump = np.asarray(L.get("pump_flow", np.zeros_like(cso)), float)
    acts = np.asarray(L["actions_projected"], float)
    if acts.ndim == 2 and acts.shape[1] >= 7:
        acts = acts[:, :7]
    raw = np.asarray(L.get("actions_raw", acts), float)
    if raw.ndim == 2 and raw.shape[1] >= 7:
        raw = raw[:, :7]
    admissible = np.asarray(L.get("actions_admissible", raw), float)
    if admissible.ndim == 2 and admissible.shape[1] >= 7:
        admissible = admissible[:, :7]
    v_cso = float(cso.sum() * volume_per_cfs_step)
    v_pump = float(pump.sum() * volume_per_cfs_step)
    d = (np.abs(acts - admissible)
         if acts.shape == admissible.shape else np.zeros_like(acts))
    constrained = (np.abs(admissible - raw)
                   if admissible.shape == raw.shape else np.zeros_like(acts))
    total_override = (np.abs(acts - raw)
                      if acts.shape == raw.shape else np.zeros_like(acts))
    dA = np.diff(acts, axis=0) if len(acts) > 1 else np.zeros((0, acts.shape[-1] if acts.ndim == 2 else 0))
    sgn = np.sign(np.where(np.abs(dA) > 0.02, dA, 0.0)) if len(dA) else np.zeros((0, 1))
    reversals = int(np.sum((sgn[1:] * sgn[:-1]) < 0)) if len(sgn) > 1 else 0
    result = dict(
        cso_vol_m3=v_cso,
        cso_vol_35391_m3=float(q1.sum() * volume_per_cfs_step),
        cso_vol_35444_m3=float(q2.sum() * volume_per_cfs_step),
        cso_events=count_events(cso > CSO_ON_CFS),
        cso_hours=float((cso > CSO_ON_CFS).sum() * step_s / 3600.0),
        cso_peak_cfs=float(cso.max()) if len(cso) else 0.0,
        capture_ratio=float(v_pump / (v_pump + v_cso)) if (v_pump + v_cso) > 0 else float("nan"),
        actuation_tv=float(np.abs(dA).mean()) if len(dA) else 0.0,
        gate_reversals=reversals,
        intervention_rate=float((d.max(axis=1) > 1e-6).mean()) if len(d) else 0.0,
        intervention_mag=float(d.mean()) if len(d) else 0.0,
        actor_constraint_rate=float((constrained.max(axis=1) > 1e-6).mean()) if len(constrained) else 0.0,
        actor_constraint_mag=float(constrained.mean()) if len(constrained) else 0.0,
        total_override_rate=float((total_override.max(axis=1) > 1e-6).mean()) if len(total_override) else 0.0,
        total_override_mag=float(total_override.mean()) if len(total_override) else 0.0,
        max_depth_ratio_peak=float(np.max(L["max_depth_ratio"])) if "max_depth_ratio" in L else float("nan"),
        routing_error_pct=float(L.get("routing_error_pct", float("nan"))),
        runoff_error_pct=float(L.get("runoff_error_pct", float("nan"))),
    )
    result.update(L.get("accounting_summary", {}))
    return result

"""Storage-first specification (signal-temporal-logic style) and storage metrics.

phi_safe  : G( flood_t <= eps )                       -> never flood
phi_store : G( cso_t > eps_cso -> fill_t >= 1-delta ) -> overflow only when storage is (nearly) full
Robustness rho >= 0  <=>  the property is satisfied on the trace.
`fill` MUST be the fill ratio of the real storage units (env log key `store_fill_ratio`).
"""
from __future__ import annotations
import numpy as np


def rho_flood_free(flood, eps=1e-6) -> float:
    return float(np.min(eps - np.asarray(flood, float)))


def rho_storage_first(cso, fill, eps_cso=0.01, delta=0.05) -> float:
    a = eps_cso - np.asarray(cso, float)                    # (cso_t <= eps)
    b = np.asarray(fill, float) - (1.0 - delta)             # (fill_t >= 1-delta)
    return float(np.min(np.maximum(a, b)))


def storage_metrics(L: dict, eps_cso=0.01, delta=0.05) -> dict:
    cso = np.asarray(L["cso_flow"], float)
    fill = np.asarray(L["store_fill_ratio"], float)
    act = cso > eps_cso
    viol = act & (fill < 1.0 - delta)
    rs = rho_storage_first(cso, fill, eps_cso, delta)
    rf = rho_flood_free(L["flooding"])
    return dict(
        peak_store_util=float(fill.max()),
        suo_onset=float(fill[np.argmax(act)]) if act.any() else float("nan"),      # storage use when overflow STARTS
        fill_during_cso=float(fill[act].mean()) if act.any() else float("nan"),
        store_first_viol_steps=int(viol.sum()),
        store_first_viol_rate=float(viol.sum() / act.sum()) if act.any() else float("nan"),
        rho_storage_first=rs, rho_flood_free=rf,
        sat_storage_first=bool(rs >= 0), sat_flood_free=bool(rf >= 0),
    )

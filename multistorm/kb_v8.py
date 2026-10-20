"""KnowledgeBaseV8: topology-aware rules, storage-first reward, flood cost. Standalone (does not subclass v7).

Env contract (see patches/APP_PATCHES.md): the env must put these keys in obs_dict:
  node_depths {id: depth}, cso_flow, flooding, store_fill_ratio, storage_unit_fill {storage_id: depth/full_depth}
and call kb.extra_features(obs_dict, rain_series, n_applied) when kb.extra_dim > 0.
"""
from __future__ import annotations
import numpy as np
from multistorm.obsfeat import RAIN_SCALES, rain_features

DEFAULT_THETA = dict(theta_f=0.90, theta_f_open=0.50, theta_s=0.80, flood_cfs=1.0, delta=0.05)


class KnowledgeBaseV8:
    PUMP_IDXS = [7, 8, 9]
    GATE_IDXS = list(range(7))
    FLOODING_THRESHOLD = float("inf")        # legacy attribute some v7 code reads; v8 does not use an absolute threshold

    def __init__(self, node_full_depths: dict, junction_ids, gate_topology: dict, theta: dict | None = None,
                 w_cso=10.0, w_store=2.0, eps_cso=0.01, cso_floor=1.0, v_scale_m3=1000.0, margin=2.0,
                 horizon=287, cso_scale=100.0, flood_scale=100.0, use_rain_features=True,
                 freeze_pumps=True):
        self.full = node_full_depths
        self.junctions = [n for n in junction_ids if n in node_full_depths]
        self.topo = gate_topology
        self.theta = {**DEFAULT_THETA, **(theta or {})}
        self.w_cso, self.w_store, self.eps = w_cso, w_store, eps_cso
        self.cso_floor, self.v_scale, self.margin, self.T = cso_floor, v_scale_m3, margin, horizon
        self.cso_scale, self.flood_scale = cso_scale, flood_scale
        self.extra_dim = len(RAIN_SCALES) if use_rain_features else 0
        self.freeze_pumps = bool(freeze_pumps)
        self.ref_cso = float(cso_floor)
        self.last_info: dict = {}

    # ---- env hooks ---------------------------------------------------------
    def reset_episode(self):
        self.last_info = {}

    def set_baseline_flooding(self, v):      # v7 plumbing; v8 uses absolute flood cost -> no-op
        pass

    def set_reference(self, cso_total):
        self.ref_cso = max(float(cso_total), self.cso_floor)

    def _dr(self, obs, ids):
        nd = obs["node_depths"]
        return [nd[n] / max(self.full[n], 1e-6) for n in ids if n in nd]

    # ---- observation -------------------------------------------------------
    def evaluate_predicates(self, obs) -> np.ndarray:
        d, fill = self.theta["delta"], float(obs["store_fill_ratio"])
        drs = self._dr(obs, self.junctions)
        mx, mean = (max(drs), float(np.mean(drs))) if drs else (0.0, 0.0)
        cso, flood = float(obs["cso_flow"]), float(obs["flooding"])
        c = lambda x: float(np.clip(x, 0.0, 1.0))
        return np.array([fill >= 1 - d, fill >= 0.70, mx >= 0.90, mx >= 0.75, cso > self.eps, flood > 1e-6,
                         c(fill), c(mx), c(mean), c(cso / self.cso_scale), c(flood / self.flood_scale)], np.float32)

    def extra_features(self, obs, rain_series, n_applied) -> np.ndarray:
        return rain_features(rain_series, n_applied) if self.extra_dim else np.zeros(0, np.float32)

    # ---- shield ------------------------------------------------------------
    def project_action(self, raw, obs) -> np.ndarray:
        raw = np.asarray(raw, float)
        a = np.clip(raw.copy(), 0.0, 1.0)
        if a.size >= 10 and self.freeze_pumps:
            a[self.PUMP_IDXS] = 1.0
        th, delta = self.theta, self.theta["delta"]
        # For the complete physical objective, "usable" means capacity below
        # the first overflow crest.  Full-depth capacity can be much larger and
        # would falsely tell the shield that storage remains available while it
        # is already spilling.
        ufill = obs.get("usable_storage_unit_fill", obs.get("storage_unit_fill", {}))
        cso_now = float(obs["cso_flow"]) > self.eps
        flood_now = float(obs["flooding"]) > th["flood_cfs"]
        flags = dict(F1=0, F2=0, S1=0)
        explanations = []
        for g in self.GATE_IDXS:
            ctx = self.topo.get(g)
            if not ctx:
                continue
            drs = self._dr(obs, ctx["risk_up"])
            risk = max(drs) if drs else 0.0
            stor = [ufill[n] for n in ctx["storage_down"] if n in ufill]
            full = bool(stor) and min(stor) >= 1 - delta
            spill_direct = bool(ctx["weirs_down"] or ctx.get("cso_outfalls_down", [])) and not stor
            cands = [(0.0, None)]
            if flood_now:
                cands.append((th["theta_f_open"] if (spill_direct or full) else 1.0, "F2"))
            elif risk >= th["theta_f"]:
                cands.append((th["theta_f_open"], "F1"))
            if cso_now and stor and not full and not flood_now:
                cands.append((th["theta_s"], "S1"))
            lb, name = max(cands, key=lambda x: x[0])
            if lb > a[g]:
                a[g] = lb
                flags[name] += 1
                explanations.append(dict(
                    gate_idx=g, rule=name, proposed=float(np.clip(raw[g], 0, 1)),
                    applied=float(a[g]), lower_bound=float(lb),
                    upstream_depth_ratio=float(risk), storage_full=full,
                    downstream_storage=list(ctx["storage_down"]),
                    affected_weirs=list(ctx["weirs_down"]),
                    cso_active=cso_now, flood_active=flood_now,
                ))
        self.last_info = dict(flags=flags, explanations=explanations,
                              intervention=float(np.mean(np.abs(a[:7] - np.clip(raw[:7], 0, 1)))))
        return np.clip(a, 0.0, 1.0)

    # ---- reward / cost -----------------------------------------------------
    def cost(self, obs) -> float:
        # The Lagrangian constraint must use the exact quantity checked by
        # flood non-regression. Junction-depth risk remains in the shield; it
        # is not mixed into the physical flood-volume budget.
        flood_m3 = float(obs["flooding"]) * 900.0 * 0.028316846592
        return flood_m3 / self.v_scale

    def shape_reward(self, obs, raw, proj):
        cso = max(float(obs["cso_flow"]), 0.0)
        fill = float(obs["store_fill_ratio"])
        r_cso = -self.w_cso * cso / self.ref_cso
        viol = float(cso > self.eps) * max(0.0, 1.0 - self.theta["delta"] - fill)
        r_store = -self.w_store * viol / self.T
        total = r_cso + r_store
        return total, dict(cso_penalty=r_cso, store_first=r_store, gate_close=0.0, flood_penalty=0.0,
                           cost=self.cost(obs), total=total)

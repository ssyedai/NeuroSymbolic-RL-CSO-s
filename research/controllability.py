"""Hindsight (open-loop) optimum per event = upper bound on what gate control can achieve, and the regret reference.

`evaluate_fn(policy, storm, use_projection) -> episode summary dict` is the single-storm evaluation from multistorm/evaluate.py.
Run with use_projection=False for the physical upper bound; True for the shielded (rule-augmented) optimum.
"""
from __future__ import annotations
import numpy as np


class SchedulePolicy:
    """Open-loop piecewise-constant gate schedule. params: (n_seg, 7) in [0,1]; pumps = 1."""
    def __init__(self, params, n_steps=288):
        self.p = np.clip(np.asarray(params, float).reshape(-1, 7), 0.0, 1.0)
        self.seg = int(np.ceil(n_steps / len(self.p)))
        self.t = 0

    def reset(self):
        self.t = 0

    def select_action(self, obs=None, deterministic=True):
        a = np.r_[self.p[min(self.t // self.seg, len(self.p) - 1)], np.ones(3)]
        self.t += 1
        return a.astype(np.float32)


def objective(s: dict, ref: dict, w_flood=10.0, flood_floor=1e3) -> float:
    return (s["cso_total"] / max(ref["cso_total"], 1.0)
            + w_flood * max(s["flood_total"] - ref["flood_total"], 0.0) / max(ref["flood_total"], flood_floor))


def safety_objective(s: dict, ref: dict) -> float:
    """Feasibility-first ranking for the complete m3 objective.

    Every flood-violating result ranks below every flood-feasible result;
    within the latter, total-overflow non-regression precedes CSO minimisation.
    A finite weighted sum cannot enforce these priorities. No claim that this
    ranking makes an infeasible search feasible: callers must check the result.
    """
    if s.get("volume_units") != "m3" or ref.get("volume_units") != "m3":
        raise ValueError("Safety-first search requires cumulative m3 summaries")
    values = [s[k] for k in ("flood_total", "cso_total", "total_overflow_vol_m3")]
    values += [ref[k] for k in ("flood_total", "cso_total", "total_overflow_vol_m3")]
    if not np.isfinite(values).all() or min(values) < 0:
        return float("inf")
    flood_cap = 10.0 if ref["flood_total"] <= 10.0 else ref["flood_total"] * 1.02 + 10.0
    flood_violation = max(s["flood_total"] - flood_cap, 0.0)
    if flood_violation:
        return 3.0 + flood_violation / (1.0 + flood_violation)
    overflow_violation = max(s["total_overflow_vol_m3"] - ref["total_overflow_vol_m3"], 0.0)
    if overflow_violation:
        return 2.0 + overflow_violation / (1.0 + overflow_violation)
    return s["cso_total"] / (max(ref["cso_total"], 1.0) + s["cso_total"])


def static_search(evaluate_fn, storm, ref, n=64, seed=0, use_projection=False, safety_first=False):
    rng = np.random.default_rng(seed)
    cands = [np.full(7, 0.5), np.zeros(7), np.ones(7)] + [rng.uniform(0, 1, 7) for _ in range(n)]
    best = None
    for x in cands:
        s = evaluate_fn(SchedulePolicy(x[None]), storm, use_projection)
        c = (safety_objective if safety_first else objective)(s, ref)
        if best is None or c < best[0]:
            best = (c, x, s)
    return best


def cma_search(evaluate_fn, storm, ref, n_seg=4, iters=25, pop=12, seed=0, x0=None, use_projection=False, safety_first=False):
    import cma
    score_fn = safety_objective if safety_first else objective
    f = lambda x: score_fn(evaluate_fn(SchedulePolicy(np.reshape(x, (n_seg, 7))), storm, use_projection), ref)
    es = cma.CMAEvolutionStrategy(np.full(7 * n_seg, 0.5) if x0 is None else np.asarray(x0, float), 0.25,
                                  dict(bounds=[0, 1], popsize=pop, maxiter=iters, seed=seed, verbose=-9))
    while not es.stop():
        xs = es.ask()
        es.tell(xs, [f(x) for x in xs])
    best = np.asarray(es.result.xbest, float)
    return float(es.result.fbest), best, evaluate_fn(SchedulePolicy(best.reshape(n_seg, 7)), storm, use_projection)

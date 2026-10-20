"""Data-calibrated shield parameters (theta) -> optimised-rule controller (baseline B3) and the shield used by NS-SAFE-SAC.

`evaluate_fn(theta: dict, storm) -> (summary dict, ref dict)`; build the env with KnowledgeBaseV8(theta=theta) and a constant
raw action (all gates 0.5) so only the rules act. TRAIN storms only; early-stop on VALIDATION.
"""
from __future__ import annotations
import numpy as np

SPACE = dict(theta_f=(0.70, 0.99), theta_f_open=(0.0, 1.0), theta_s=(0.0, 1.0), flood_cfs=(0.1, 50.0), delta=(0.0, 0.20),
             gate_default=(0.0, 1.0))


def decode(x, names):
    return {n: float(SPACE[n][0] + np.clip(v, 0, 1) * (SPACE[n][1] - SPACE[n][0])) for n, v in zip(names, x)}


def score(theta, storms, evaluate_fn, w_flood=10.0, safety_first=False):
    vals = []
    for st in storms:
        s, ref = evaluate_fn(theta, st)
        if safety_first:
            from .controllability import safety_objective
            vals.append(safety_objective(s, ref))
            continue
        cso = s["cso_total"] / max(ref["cso_total"], 1.0)
        fl = max(s["flood_total"] - ref["flood_total"], 0.0) / max(ref["flood_total"], 1e3)
        vals.append(cso + w_flood * fl)
    if safety_first and vals and max(vals) >= 1:
        return float(max(vals))  # a failure cannot be diluted by many safe storms
    return float(np.mean(vals))


def optimize(evaluate_fn, train, val, names=("theta_f", "theta_f_open", "theta_s", "flood_cfs", "delta", "gate_default"),
             iters=20, pop=10, seed=0, patience=4, safety_first=False):
    import cma
    es = cma.CMAEvolutionStrategy(np.full(len(names), 0.5), 0.25,
                                  dict(bounds=[0, 1], popsize=pop, maxiter=iters, seed=seed, verbose=-9))
    best_val, best_theta, bad = np.inf, None, 0
    gen = 0
    while not es.stop():
        gen += 1
        xs = es.ask()
        es.tell(xs, [score(decode(x, names), train, evaluate_fn, safety_first=safety_first) for x in xs])
        th = decode(es.result.xbest, names)
        v = score(th, val, evaluate_fn, safety_first=safety_first)
        best_show = best_val if np.isfinite(best_val) else v
        print(f"CMA gen={gen} val_score={v:.4f} best={best_show:.4f} "
              f"patience={bad}/{patience} theta={th}", flush=True)
        if v < best_val - 1e-6:
            best_val, best_theta, bad = v, th, 0
        else:
            bad += 1
            if bad >= patience:
                print(f"early-stop at gen={gen}", flush=True)
                break
    return best_theta, best_val

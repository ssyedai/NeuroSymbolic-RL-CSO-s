"""T11 — Calibrate KnowledgeBaseV8 θ on train; early-stop on val. Writes runs/theta.json."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.optimize_rules import optimize
from research.guard import assert_provenance, assert_v8_scenario_manifest
from research.readiness import experiment_status, isolated_output


def _balanced_cap(storms, limit):
    if not limit or len(storms) <= limit:
        return list(storms)
    groups = {}
    for storm in sorted(storms, key=lambda s: s.storm_id):
        key = str((storm.meta or {}).get("rung", "unknown"))
        groups.setdefault(key, []).append(storm)
    chosen = []
    while len(chosen) < limit and groups:
        for key in sorted(list(groups)):
            if groups[key] and len(chosen) < limit:
                chosen.append(groups[key].pop(0))
            if not groups[key]:
                del groups[key]
    return chosen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", required=True)
    ap.add_argument("--split-manifest", default=None)
    ap.add_argument("--out", default="runs/theta.json")
    ap.add_argument("--cache", default="runs/baseline_cache.json")
    ap.add_argument("--max-train", type=int, default=0)
    ap.add_argument("--max-val", type=int, default=0,
                    help="Cap val storms (default 0 = all). Uncapped val makes CMA extremely slow.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--patience", type=int, default=4)
    ap.add_argument("--exploratory", action="store_true")
    a = ap.parse_args(argv)
    status = experiment_status(a.exploratory)
    out = isolated_output(a.out, a.exploratory, "runs/theta.json")
    cache = isolated_output(a.cache, a.exploratory, "runs/baseline_cache.json")

    from multistorm import adapters as A
    from multistorm.baselines import BaselineStore
    from multistorm.complete_overflow import (CompleteOverflowKB,
                                               COMPLETE_BASELINE_TAG,
                                               EXPLORATORY_BASELINE_TAG)
    from multistorm.metrics import episode_summary
    from multistorm.storms import assign_splits, load_storms
    from research.topology import to_kb_dict

    split_path = Path(a.split_manifest or Path(a.rain_dir) / "splits.json")
    split_map = json.loads(split_path.read_text())
    selected = [sid for sid, split in split_map.items() if split in ("train", "val")]
    storms = load_storms(a.rain_dir, scaling="none", storm_ids=selected)
    storms, _ = assign_splits(
        storms, manifest_path=a.split_manifest or str(Path(a.rain_dir) / "splits.json"))
    assert_provenance(storms, a.rain_dir)
    assert_v8_scenario_manifest(a.rain_dir, allow_exploratory=a.exploratory)
    # Prefer C/T storms with CSO signal for rule tuning
    def _pref(ss):
        scored = [s for s in ss
                  if (s.meta or {}).get("family") in ("C", "T")
                  and not (s.meta or {}).get("test_only")]
        return scored or list(ss)
    train = _pref([s for s in storms if s.split == "train"])
    val = _pref([s for s in storms if s.split == "val"])
    if a.max_train:
        train = _balanced_cap(train, a.max_train)
    if a.max_val:
        val = _balanced_cap(val, a.max_val)
    print(f"theta calibrate: n_train={len(train)} n_val={len(val)} "
          f"(~{a.pop*len(train)+len(val)} SWMM eps/CMA generation)", flush=True)

    nodes = pd.read_csv("configs/v8_diag_nodes.csv")
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}
    topo = to_kb_dict(pd.read_csv("configs/v8_gate_topology.csv"))

    env, _, _ = A.build_v8(0, complete_overflow=True, native_pumps=True)
    # swap in a v8 KB for shield evaluation
    kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo)
    env.kb = kb
    env.use_projection = True
    env.policy_dim = 7

    bstore = BaselineStore(cache, "7MPF_CSO_08.inp",
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
                           tag=(EXPLORATORY_BASELINE_TAG if a.exploratory
                                else COMPLETE_BASELINE_TAG))

    def evaluate_fn(theta, storm):
        env.kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo, theta=theta)
        rec = bstore.get(storm)
        ref = rec.get("native") or rec["static"]
        obs, _ = env.reset(options=dict(
            storm=storm, physical_rain=True, baseline_flooding=0.0,
            reference_cso=ref["cso_total"], use_projection=True,
        ))
        done = False
        action = np.full(7, theta["gate_default"])
        while not done:
            obs, _, term, trunc, _ = env.step(action)
            done = bool(term or trunc)
        s = episode_summary(env.get_episode_log(), 0.0)
        return s, ref

    from research.optimize_rules import score
    theta, best_val = optimize(
        evaluate_fn, train, val, seed=a.seed, safety_first=True,
        iters=a.iters, pop=a.pop, patience=a.patience)
    default_theta = dict(theta_f=0.90, theta_f_open=0.50, theta_s=0.80,
                         flood_cfs=1.0, delta=0.05, gate_default=0.5)
    default_val = score(default_theta, val, evaluate_fn, safety_first=True)
    helped = bool(best_val < 1.0 and best_val < default_val - 1e-6)
    blob = dict(theta=theta, best_val=best_val, default_val=default_val,
                b3_beats_b2_on_val=helped, safety_first=True,
                diagnostic_budget=dict(max_train=a.max_train, max_val=a.max_val,
                                       iters=a.iters, pop=a.pop,
                                       patience=a.patience),
                full_protocol_budget=bool(not a.max_train and not a.max_val
                                          and a.iters == 20 and a.pop == 10
                                          and a.patience == 4),
                research_status=status["research_status"],
                hydraulic_gate_passed=status["hydraulic_gate_passed"])
    text = json.dumps(blob, indent=1, default=float)
    out.write_text(text)
    sha = hashlib.sha256(text.encode()).hexdigest()
    Path(str(out) + ".sha256").write_text(sha + "\n")
    print(json.dumps({"theta": theta, "best_val": best_val, "sha256": sha},
                     indent=1, default=float))
    if not helped and not a.exploratory:
        env.close()
        raise RuntimeError("B3 did not beat B2 on validation; report no rule-tuning gain")
    env.close()


if __name__ == "__main__":
    main()

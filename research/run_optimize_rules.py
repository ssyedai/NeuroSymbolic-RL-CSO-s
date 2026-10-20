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
from research.readiness import assert_hydraulic_training_ready


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
    a = ap.parse_args(argv)
    assert_hydraulic_training_ready()

    from multistorm import adapters as A
    from multistorm.baselines import BaselineStore
    from multistorm.complete_overflow import CompleteOverflowKB, COMPLETE_BASELINE_TAG
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
    assert_v8_scenario_manifest(a.rain_dir)
    # Prefer C/T storms with CSO signal for rule tuning
    def _pref(ss):
        scored = [s for s in ss
                  if (s.meta or {}).get("family") in ("C", "T")
                  and not (s.meta or {}).get("test_only")]
        return scored or list(ss)
    train = _pref([s for s in storms if s.split == "train"])
    val = _pref([s for s in storms if s.split == "val"])
    if a.max_train:
        train = train[: a.max_train]
    if a.max_val:
        val = val[: a.max_val]
    print(f"theta calibrate: n_train={len(train)} n_val={len(val)} "
          f"(~{10*len(train)+len(val)} SWMM eps/CMA generation)", flush=True)

    nodes = pd.read_csv("configs/v8_diag_nodes.csv")
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}
    topo = to_kb_dict(pd.read_csv("configs/v8_gate_topology.csv"))

    env, _, _ = A.build_v8(0, complete_overflow=True, native_pumps=True)
    # swap in a v8 KB for shield evaluation
    kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo)
    env.kb = kb
    env.use_projection = True
    env.policy_dim = 7

    bstore = BaselineStore(a.cache, "7MPF_CSO_08.inp",
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
                           tag=COMPLETE_BASELINE_TAG)

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
    theta, best_val = optimize(evaluate_fn, train, val, seed=a.seed, safety_first=True)
    default_theta = dict(theta_f=0.90, theta_f_open=0.50, theta_s=0.80,
                         flood_cfs=1.0, delta=0.05, gate_default=0.5)
    default_val = score(default_theta, val, evaluate_fn, safety_first=True)
    helped = bool(best_val < 1.0 and best_val < default_val - 1e-6)
    blob = dict(theta=theta, best_val=best_val, default_val=default_val,
                b3_beats_b2_on_val=helped, safety_first=True)
    text = json.dumps(blob, indent=1, default=float)
    Path(a.out).write_text(text)
    sha = hashlib.sha256(text.encode()).hexdigest()
    Path(a.out + ".sha256").write_text(sha + "\n")
    print(json.dumps({"theta": theta, "best_val": best_val, "sha256": sha},
                     indent=1, default=float))
    if not helped:
        env.close()
        raise RuntimeError("B3 did not beat B2 on validation; report no rule-tuning gain")
    env.close()


if __name__ == "__main__":
    main()

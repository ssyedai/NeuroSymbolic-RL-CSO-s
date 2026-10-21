"""Evaluate non-learned Tier-1 baselines B0/B1/B2/B3 on test splits (lazy baselines)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from research.guard import assert_provenance, assert_v8_scenario_manifest
from research.readiness import experiment_status, isolated_output


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", default="data/useful/rain_scenarios")
    ap.add_argument("--split-manifest", default=None)
    ap.add_argument("--theta-path", default="runs/theta.json")
    ap.add_argument("--out-dir", default="runs/baselines_tier1")
    ap.add_argument("--which", default="b0,b2,b3",
                    help="comma list among b0,b1,b2,b3,nativeprior,hybridgate2")
    ap.add_argument("--baseline-cache", default=None,
                    help="Optional existing train/validation reference cache")
    ap.add_argument("--control-step", type=int, default=900,
                    choices=[300, 900], help="External control interval in seconds")
    ap.add_argument("--hybrid-action", type=float, default=0.5,
                    help="Constant normalized residual used by the hybridgate2 diagnostic")
    ap.add_argument("--max-storms", type=int, default=0)
    ap.add_argument("--splits", default="test")
    ap.add_argument("--protocol-tag", default="protocol-v1")
    ap.add_argument("--exploratory", action="store_true")
    a = ap.parse_args(argv)
    status = experiment_status(a.exploratory)
    out = isolated_output(a.out_dir, a.exploratory, "runs/baselines_tier1")
    if a.exploratory and a.theta_path == "runs/theta.json":
        a.theta_path = "runs/exploratory/theta.json"

    from multistorm import adapters as A
    from multistorm.baselines import BaselineStore
    from multistorm.complete_overflow import (CompleteOverflowKB,
                                               COMPLETE_BASELINE_TAG,
                                               EXPLORATORY_BASELINE_TAG)
    from multistorm.evaluate_checkpoint import _protocol_commit
    from multistorm.evaluate import evaluate
    from multistorm.kb_v8 import DEFAULT_THETA
    from multistorm.storms import assign_splits, load_storms
    from research.topology import to_kb_dict

    want = {x.strip() for x in a.splits.split(",") if x.strip()}
    if not want or not want <= {"train", "val", "test"}:
        raise ValueError("--splits must contain train, val and/or test")
    if "test" in want:
        _protocol_commit(a.protocol_tag)
    split_path = Path(a.split_manifest or Path(a.rain_dir) / "splits.json")
    split_map = json.loads(split_path.read_text())
    selected = sorted(sid for sid, split in split_map.items() if split in want)
    storms = load_storms(a.rain_dir, scaling="none", storm_ids=selected)
    storms, _ = assign_splits(
        storms, manifest_path=a.split_manifest or str(Path(a.rain_dir) / "splits.json"))
    assert_provenance(storms, a.rain_dir)
    assert_v8_scenario_manifest(a.rain_dir, allow_exploratory=a.exploratory)
    pool = [s for s in storms if s.split in want]
    if a.max_storms:
        from multistorm.train_multi import _balanced_rung_cap
        pool = _balanced_rung_cap(pool, a.max_storms)

    nodes = pd.read_csv("configs/v8_diag_nodes.csv")
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}
    topo = to_kb_dict(pd.read_csv("configs/v8_gate_topology.csv"))
    theta = None
    if Path(a.theta_path).exists():
        theta_blob = json.loads(Path(a.theta_path).read_text())
        theta = theta_blob.get("theta")

    out.mkdir(parents=True, exist_ok=True)

    git_dirty_files = []
    git_diff_sha256 = None
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip()
        git_dirty_files = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True).splitlines()
        if git_dirty_files:
            git_diff_sha256 = hashlib.sha256(subprocess.check_output(
                ["git", "diff", "--binary", "HEAD"])).hexdigest()
    except Exception:
        git_hash = None
    run_config = dict(
        purpose="non-learned baseline/diagnostic evaluation",
        arguments=vars(a), git_hash=git_hash,
        git_dirty=bool(git_dirty_files), git_dirty_files=git_dirty_files,
        git_diff_sha256=git_diff_sha256,
        manifest_hash=hashlib.sha256(
            Path(a.rain_dir, "data_manifest.json").read_bytes()).hexdigest(),
        research_status=status["research_status"],
        hydraulic_gate_passed=status["hydraulic_gate_passed"],
    )
    (out / "run_config.json").write_text(
        json.dumps(run_config, indent=1, default=str))

    requested = [x.strip().lower() for x in a.which.split(",") if x.strip()]
    hybrid = "hybridgate2" in requested
    if hybrid and len(requested) != 1:
        raise ValueError("hybridgate2 must run alone because it uses different actuator ownership")
    hybrid_kwargs = {}
    if hybrid:
        hybrid_kwargs = dict(
            gate2_rule_prior=True, policy_dim=1,
            native_managed_gates=("1360", "1360_B", "35281_B", "35291_B", "3530", "3530_B"),
            external_gate_indices=(2,),
        )
    env, _, _ = A.build_v8(
        0, complete_overflow=True, native_pumps=True,
        control_time_step=a.control_step, **hybrid_kwargs)
    baseline_tag = (EXPLORATORY_BASELINE_TAG if a.exploratory
                    else COMPLETE_BASELINE_TAG)
    if a.control_step != 900:
        baseline_tag += f"|ctrl{a.control_step}"
    if hybrid:
        baseline_tag += "|hybridgate2"
    bstore = BaselineStore(a.baseline_cache or out / "baseline_cache.json", "7MPF_CSO_08.inp",
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
                           tag=baseline_tag)

    class _Const:
        def __init__(self, a):
            self.a = np.asarray(a, np.float32)
        def select_action(self, obs, deterministic=True):
            return self.a

    for name in requested:
        if name == "b0":
            env.kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo)
            env.use_projection = False
            agent = _Const(np.full(7, 0.5))
        elif name == "b2":
            env.kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo, theta=DEFAULT_THETA)
            env.use_projection = True
            agent = _Const(np.full(7, 0.5))
            env.policy_dim = 7
        elif name == "b3":
            if theta is None or not theta_blob.get("b3_beats_b2_on_val", False):
                raise RuntimeError("B3 requires a validation-approved runs/theta.json")
            if not a.exploratory and theta_blob.get("full_protocol_budget") is not True:
                raise RuntimeError("Official B3 requires a full-budget theta calibration")
            env.kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo, theta=theta)
            env.use_projection = True
            agent = _Const(np.full(7, 0.5))
            env.policy_dim = 7
        elif name == "nativeprior":
            env.kb = CompleteOverflowKB(
                full, list(nodes[nodes.junction].id), topo,
                theta=theta or DEFAULT_THETA, native_rule_prior=True)
            env.use_projection = True
            agent = _Const(np.full(3, 0.5))
            env.policy_dim = 3
        elif name == "hybridgate2":
            if not 0.0 <= a.hybrid_action <= 1.0:
                raise ValueError("--hybrid-action must be in [0, 1]")
            env.kb = CompleteOverflowKB(
                full, list(nodes[nodes.junction].id), topo,
                theta=theta or DEFAULT_THETA, gate2_rule_prior=True)
            env.use_projection = True
            agent = _Const(np.full(1, a.hybrid_action))
            env.policy_dim = 1
        elif name == "b1":
            from multistorm.metrics_v8 import enrich
            # native reference already in cache — materialise rows from native records
            rows = []
            for st in pool:
                rec = bstore.get(st)
                n = rec.get("native") or rec["static"]
                row = dict(storm_id=st.storm_id, split=st.split, phase="b1",
                           family=(st.meta or {}).get("family"),
                           rung=(st.meta or {}).get("rung"),
                           k=(st.meta or {}).get("k"),
                           T_anchor=(st.meta or {}).get("T_anchor"),
                           parent=(st.meta or {}).get("parent", st.storm_id))
                row.update(n)
                row.update(enrich(n, n))
                rows.append(row)
            frame = pd.DataFrame(rows)
            frame["research_status"] = status["research_status"]
            frame["hydraulic_gate_passed"] = status["hydraulic_gate_passed"]
            frame.to_csv(out / f"{name}_eval.csv", index=False)
            print(f"wrote {name}", len(rows), flush=True)
            continue
        else:
            raise SystemExit(f"unknown baseline {name}")

        print(f"evaluating {name} on {len(pool)} storms...", flush=True)
        df = evaluate(agent, env, pool, bstore, name, None)
        df["research_status"] = status["research_status"]
        df["hydraulic_gate_passed"] = status["hydraulic_gate_passed"]
        df.to_csv(out / f"{name}_eval.csv", index=False)
        print(f"wrote {name}", len(df), flush=True)

    env.close()


if __name__ == "__main__":
    main()

"""Evaluate non-learned Tier-1 baselines B0/B1/B2/B3 on test splits (lazy baselines)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.guard import assert_provenance, assert_v8_scenario_manifest
from research.readiness import assert_hydraulic_training_ready


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", default="data/useful/rain_scenarios")
    ap.add_argument("--split-manifest", default=None)
    ap.add_argument("--theta-path", default="runs/theta.json")
    ap.add_argument("--out-dir", default="runs/baselines_tier1")
    ap.add_argument("--which", default="b0,b2,b3",
                    help="comma list among b0,b1,b2,b3 (b1=native is already in cache)")
    ap.add_argument("--max-storms", type=int, default=0)
    ap.add_argument("--splits", default="test")
    ap.add_argument("--protocol-tag", default="protocol-v1")
    a = ap.parse_args(argv)
    assert_hydraulic_training_ready()

    from multistorm import adapters as A
    from multistorm.baselines import BaselineStore
    from multistorm.complete_overflow import CompleteOverflowKB, COMPLETE_BASELINE_TAG
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
    assert_v8_scenario_manifest(a.rain_dir)
    pool = [s for s in storms if s.split in want]
    if a.max_storms:
        pool = pool[: a.max_storms]

    nodes = pd.read_csv("configs/v8_diag_nodes.csv")
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}
    topo = to_kb_dict(pd.read_csv("configs/v8_gate_topology.csv"))
    theta = None
    if Path(a.theta_path).exists():
        theta_blob = json.loads(Path(a.theta_path).read_text())
        theta = theta_blob.get("theta")

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    env, _, _ = A.build_v8(0, complete_overflow=True, native_pumps=True)
    bstore = BaselineStore(out / "baseline_cache.json", "7MPF_CSO_08.inp",
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
                           tag=COMPLETE_BASELINE_TAG)

    class _Const:
        def __init__(self, a):
            self.a = np.asarray(a, np.float32)
        def select_action(self, obs, deterministic=True):
            return self.a

    for name in a.which.split(","):
        name = name.strip().lower()
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
            env.kb = CompleteOverflowKB(full, list(nodes[nodes.junction].id), topo, theta=theta)
            env.use_projection = True
            agent = _Const(np.full(7, 0.5))
            env.policy_dim = 7
        elif name == "b1":
            from multistorm.metrics_v8 import enrich
            # native reference already in cache — materialise rows from native records
            rows = []
            for st in pool:
                rec = bstore.get(st)
                n = rec.get("native") or rec["static"]
                rows.append(dict(storm_id=st.storm_id, split=st.split, phase="b1",
                                 family=(st.meta or {}).get("family"),
                                 rung=(st.meta or {}).get("rung"),
                                 k=(st.meta or {}).get("k"),
                                 T_anchor=(st.meta or {}).get("T_anchor"),
                                 parent=(st.meta or {}).get("parent", st.storm_id),
                                 **n, **enrich(n, n)))
            pd.DataFrame(rows).to_csv(out / f"{name}_eval.csv", index=False)
            print(f"wrote {name}", len(rows), flush=True)
            continue
        else:
            raise SystemExit(f"unknown baseline {name}")

        print(f"evaluating {name} on {len(pool)} storms...", flush=True)
        df = evaluate(agent, env, pool, bstore, name, None)
        df.to_csv(out / f"{name}_eval.csv", index=False)
        print(f"wrote {name}", len(df), flush=True)

    env.close()


if __name__ == "__main__":
    main()

"""One-gate-at-a-time train-only hydraulic diagnostic, never policy selection."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time
import argparse

import numpy as np
import pandas as pd
from multistorm import adapters as A
from multistorm.complete_overflow import COMPLETE_BASELINE_TAG
from multistorm.storms import load_storms
from research.guard import assert_provenance

GATES = ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runs/hydraulic_validation_20261011/owned_gates")
    parser.add_argument("--max-parents", type=int, default=3)
    args = parser.parse_args()
    root = Path(args.out)
    if (root / "gate_sensitivity.csv").exists():
        raise FileExistsError("Choose a new output directory; preserve earlier diagnostics")
    root.mkdir(parents=True, exist_ok=True)
    rain = Path("data/useful/rain_scenarios")
    manifest = json.loads((rain / "data_manifest.json").read_text())["storms"]
    ids = sorted(s for s,m in manifest.items() if m["split"] == "train" and m["rung"] == "T10")[:args.max_parents]
    storms = load_storms(rain, "none", storm_ids=ids)
    assert_provenance(storms, rain)
    config = dict(storm_ids=ids, selection="first three sorted train T10 IDs", split="train",
                  physical_rain=True, real_only=True, scaling="none", seed=0, processes=1,
                  budget_s=1800, baseline_tag=COMPLETE_BASELINE_TAG, theta_hash=None, git_hash=None,
                  use_projection=False, policy_dim=7, pumps="ON commands for controlled runs; INP rules for native",
                  manifest_hash=hashlib.sha256((rain / "data_manifest.json").read_bytes()).hexdigest(),
                  code_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                               ("app.py", "multistorm/complete_overflow.py", "research/gate_sensitivity.py")},
                  versions={p:importlib.metadata.version(p) for p in ("pyswmm", "swmm-toolkit", "torch", "numpy")})
    (root / "gate_run_config.json").write_text(json.dumps(config, indent=2))
    cases = [("native", None, None), ("static_half", None, None)]
    cases += [(f"{gate}={setting}", i, setting) for i,gate in enumerate(GATES) for setting in (0.0, 1.0)]
    env, _, _ = A.build_v8(0, complete_overflow=True, use_projection=False)
    rows, nodes = [], []
    started = time.monotonic()
    try:
        for storm in storms:
            for name, gate, setting in cases:
                env.reset(options=dict(storm=storm, physical_rain=True, native=name == "native",
                                       use_projection=False, baseline_flooding=0.0))
                action = np.full(7, 0.5)
                if gate is not None:
                    action[gate] = setting
                done = False
                while not done:
                    _,_,term,trunc,_ = env.step(action)
                    done = term or trunc
                log = env.get_episode_log()
                actual = log["actions_actual"][:, :7]
                row = dict(storm_id=storm.storm_id, parent=storm.meta["parent"], split="train",
                           case=name, **log["accounting_summary"],
                           target_vs_command_max_error=float(np.abs(log["actions_target"][:, :7]-action).max()) if name != "native" else 0.0,
                           actual_vs_command_max_error=float(np.abs(actual-action).max()) if name != "native" else 0.0)
                rows.append(row)
                for node, volume in log["node_flood_volumes_m3"].items():
                    if volume > 0:
                        nodes.append(dict(storm_id=storm.storm_id, case=name, node=node, flood_m3=volume,
                                          max_depth_ft=log["node_peak_depth_ft"][node]))
                pd.DataFrame(rows).to_csv(root / "gate_sensitivity.csv", index=False)
                pd.DataFrame(nodes).to_csv(root / "gate_flood_nodes.csv", index=False)
                print(storm.storm_id, name, f"flood={row['flood_total']:.2f} cso={row['cso_total']:.2f} command_error={row['actual_vs_command_max_error']:.3g}", flush=True)
                if row["target_vs_command_max_error"] > 1e-6:
                    raise RuntimeError("Gate ownership check failed; commanded actions were not applied")
                if time.monotonic()-started > 1800:
                    raise RuntimeError("Gate diagnostic budget reached; output is incomplete")
    finally:
        env.close()


if __name__ == "__main__":
    main()

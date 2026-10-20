"""Fixed train/validation diagnostic, not a trained-agent superiority claim."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from multistorm import adapters as A
from multistorm.storms import load_storms, Storm
from multistorm.metrics import episode_summary
from multistorm.metrics_ext import extended_summary
from multistorm.metrics_v8 import enrich
from research.guard import assert_provenance
from multistorm.complete_overflow import COMPLETE_BASELINE_TAG
from multistorm.kb_v8 import DEFAULT_THETA


def main():
    root = Path("data/useful/rain_scenarios")
    output = Path("runs/complete_overflow_check_20261010")
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / "data_manifest.json").read_text())["storms"]
    ids = []
    for split in ("train", "val"):
        ids += sorted(sid for sid, m in manifest.items() if m["split"] == split and m["rung"] == "T10")[:3]
    storms = [s.with_split(manifest[s.storm_id]["split"]) for s in load_storms(root, "none", storm_ids=ids)]
    assert_provenance(storms, root)
    config = dict(purpose="accounting and reactive shield diagnostic; no training or test evaluation",
                  seed=0, processes=1, budget_hours=0.5, physical_rain=True, real_only=True, scaling="none",
                  storms=ids, selection="first three sorted T10 IDs in each train/val split",
                  manifest_hash=hashlib.sha256((root / "data_manifest.json").read_bytes()).hexdigest(),
                  theta_hash=None, git_hash=None, full_horizon=True,
                  baseline_tag=COMPLETE_BASELINE_TAG, theta=DEFAULT_THETA,
                  code_hashes={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                               ("app.py", "multistorm/complete_overflow.py", "research/complete_overflow_check.py")},
                  outfalls=["54", "65", "54_B", "65_B"],
                  lib_versions={p: importlib.metadata.version(p) for p in ("numpy", "torch", "pyswmm", "swmm-toolkit")})
    (output / "run_config.json").write_text(json.dumps(config, indent=2))
    gates = ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B"]
    from pyswmm import Simulation, Links
    with Simulation("7MPF_CSO_08.inp") as native_sim:
        native_sim.start()
        native_initial = {g: float(Links(native_sim)[g].target_setting) for g in gates}
    env, _, kb = A.build_v8(0, complete_overflow=True)
    rows, traces, hydro = [], [], []

    def run(storm, policy):
        env.reset(options=dict(storm=storm, physical_rain=True, native=policy == "native",
                               use_projection=policy == "candidate_rules", baseline_flooding=0.0))
        initial = {g: float(env._link_obj[g].target_setting) for g in gates}
        depths, done = [], False
        while not done:
            action = np.full(7, 0.5)
            if policy == "bypass_closed":
                action[3:5] = 0
            _, _, term, trunc, _ = env.step(action)
            depths.append(dict(env._obs_dict["node_depths"]))
            done = term or trunc
        log = env.get_episode_log()
        result = {**episode_summary(log, 0.0), **extended_summary(log)}
        outflow = result["cso_total"] + result["treated_outfall_vol_m3"]
        result["outflow_balance_difference_m3"] = outflow - result["system_outflow_vol_m3"]
        result["flood_balance_difference_m3"] = result["flood_total"] - result["system_flood_vol_m3"]
        for step, explanations in enumerate(log["rule_explanations"]):
            traces.extend(dict(storm_id=storm.storm_id, policy=policy, step=step, **r) for r in explanations)
        for step, (cso, flood, fill) in enumerate(zip(log["cso_flow"], log["flooding"], log["usable_store_fill_ratio"])):
            hydro.append(dict(storm_id=storm.storm_id, policy=policy, hour=(step+1)/4,
                              cso_cfs=cso, flood_cfs=flood, usable_fill=fill))
        return result, pd.DataFrame(depths), initial

    try:
        dry = Storm("dry_diagnostic", "zero rainfall diagnostic only", np.zeros(288), np.zeros(288), "train", {"scaling": "none"})
        _, dry_depth, _ = run(dry, "native")
        wet, wet_depth, wet_initial = run(storms[0], "native")
        responsive = (wet_depth[env.storage_ids] - dry_depth[env.storage_ids]).abs().max()
        g0 = dict(storage_nodes=list(env.storage_ids), max_wet_dry_depth_difference_ft=responsive.to_dict(),
                  native_initial=native_initial, native_reset_initial=wet_initial, flow_units="CFS",
                  pass_gate=bool((responsive > 0.01).all() and native_initial == wet_initial))
        (output / "g0.json").write_text(json.dumps(g0, indent=2))
        if not g0["pass_gate"]:
            raise RuntimeError(f"G0 failed: {g0}")
        started = time.monotonic()
        for storm in storms:
            ref = wet if storm.storm_id == storms[0].storm_id else run(storm, "native")[0]
            for policy in ("native", "static_half", "bypass_closed", "candidate_rules"):
                s = ref if policy == "native" else run(storm, policy)[0]
                rows.append(dict(storm_id=storm.storm_id, split=storm.split, policy=policy,
                                 **{**{k:storm.meta[k] for k in ("parent", "family", "rung", "k", "T_anchor")},
                                    **s, **enrich(s, ref)}))
                pd.DataFrame(rows).to_csv(output / "diagnostic.csv", index=False)
                print(storm.storm_id, policy, "flood", round(s["flood_total"], 2),
                      "CSO", round(s["cso_total"], 2), flush=True)
            if time.monotonic() - started > 1800:
                raise RuntimeError("Diagnostic time budget reached")
    finally:
        env.close()
        pd.DataFrame(traces).to_csv(output / "rule_explanations.csv", index=False)
        pd.DataFrame(hydro).to_csv(output / "hydrographs.csv", index=False)


if __name__ == "__main__":
    main()

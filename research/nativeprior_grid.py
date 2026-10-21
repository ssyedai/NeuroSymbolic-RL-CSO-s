"""Small TRAIN-only safety grid for the causal native-rule prior.

This is an exploratory calibration diagnostic. It never reads test storms and
does not promote a controller unless every selected training storm satisfies
flood and total-overflow non-regression.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from research.guard import assert_provenance, assert_v8_scenario_manifest
from research.readiness import experiment_status, isolated_output


def _pick(storms, rungs):
    selected = []
    for rung in rungs:
        candidates = sorted(
            (s for s in storms if (s.meta or {}).get("rung") == rung),
            key=lambda s: s.storm_id,
        )
        if candidates:
            selected.append(candidates[0])
    return selected


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rain-dir", required=True)
    ap.add_argument("--split-manifest", required=True)
    ap.add_argument("--baseline-cache", required=True)
    ap.add_argument("--out", default="runs/exploratory/nativeprior_grid")
    ap.add_argument("--rungs", default="C1,C1.5,C2,C3")
    ap.add_argument("--control-step", type=int, default=900, choices=[300, 900])
    ap.add_argument("--exploratory", action="store_true")
    args = ap.parse_args(argv)

    status = experiment_status(args.exploratory)
    out = isolated_output(args.out, args.exploratory,
                          "runs/exploratory/nativeprior_grid")
    out.mkdir(parents=True, exist_ok=True)

    from multistorm import adapters as A
    from multistorm.baselines import BaselineStore
    from multistorm.complete_overflow import (CompleteOverflowKB,
                                               COMPLETE_BASELINE_TAG,
                                               EXPLORATORY_BASELINE_TAG)
    from multistorm.kb_v8 import DEFAULT_THETA
    from multistorm.metrics import episode_summary
    from multistorm.metrics_v8 import enrich
    from multistorm.storms import load_storms
    from research.topology import to_kb_dict

    split_map = json.loads(Path(args.split_manifest).read_text())
    train_ids = sorted(sid for sid, split in split_map.items() if split == "train")
    storms = load_storms(args.rain_dir, "none", storm_ids=train_ids)
    storms = [s.with_split("train") for s in storms]
    storms = _pick(storms, [x.strip() for x in args.rungs.split(",") if x.strip()])
    if not storms:
        raise RuntimeError("No requested training rungs were found")
    assert_provenance(storms, args.rain_dir)
    manifest = assert_v8_scenario_manifest(
        args.rain_dir, allow_exploratory=args.exploratory)

    nodes = pd.read_csv("configs/v8_diag_nodes.csv")
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}
    topo = to_kb_dict(pd.read_csv("configs/v8_gate_topology.csv"))
    baseline_tag = (EXPLORATORY_BASELINE_TAG if args.exploratory
                    else COMPLETE_BASELINE_TAG)
    if args.control_step != 900:
        baseline_tag += f"|ctrl{args.control_step}"

    candidates = [
        (theta_f, theta_f_open)
        for theta_f in (0.50, 0.70, 0.90)
        for theta_f_open in (0.50, 1.00)
    ]
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
    config = dict(
        purpose="TRAIN-only native-rule-prior safety grid",
        storms=[s.storm_id for s in storms], split="train", candidates=candidates,
        control_time_step_s=args.control_step,
        selection="safety lexicographic; no test access", theta=None,
        train_safety_feasible=None,
        manifest_hash=hashlib.sha256(
            Path(args.rain_dir, "data_manifest.json").read_bytes()).hexdigest(),
        manifest_schema=manifest.get("schema_version"), git_hash=git_hash,
        git_dirty=bool(git_dirty_files), git_dirty_files=git_dirty_files,
        git_diff_sha256=git_diff_sha256,
        research_status=status["research_status"],
        hydraulic_gate_passed=status["hydraulic_gate_passed"],
        lib_versions={p: importlib.metadata.version(p)
                      for p in ("numpy", "pandas", "pyswmm", "swmm-toolkit")},
    )
    (out / "run_config.json").write_text(json.dumps(config, indent=1, default=float))
    env, _, _ = A.build_v8(
        0, complete_overflow=True, native_pumps=True,
        native_rule_prior=True, policy_dim=3,
        control_time_step=args.control_step)
    bstore = BaselineStore(
        args.baseline_cache, "7MPF_CSO_08.inp",
        A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
        tag=baseline_tag,
    )
    rows = []
    try:
        for theta_f, theta_f_open in candidates:
            theta = {**DEFAULT_THETA, "theta_f": theta_f,
                     "theta_f_open": theta_f_open}
            env.kb = CompleteOverflowKB(
                full, list(nodes[nodes.junction].id), topo, theta=theta,
                native_rule_prior=True)
            for storm in storms:
                rec = bstore.get(storm)
                ref = rec.get("native") or rec["static"]
                obs, _ = env.reset(options=dict(
                    storm=storm, physical_rain=True, baseline_flooding=0.0,
                    reference_cso=ref["cso_total"], use_projection=True))
                done = False
                while not done:
                    obs, _, term, trunc, _ = env.step(np.full(3, 0.5))
                    done = bool(term or trunc)
                summary = episode_summary(env.get_episode_log(), 0.0)
                row = dict(
                    theta_f=theta_f, theta_f_open=theta_f_open,
                    storm_id=storm.storm_id, rung=(storm.meta or {}).get("rung"))
                row.update(summary)
                row.update(enrich(summary, ref))
                rows.append(row)
                pd.DataFrame(rows).to_csv(out / "grid.csv", index=False)
    finally:
        env.close()

    frame = pd.DataFrame(rows)
    grouped = frame.groupby(["theta_f", "theta_f_open"], as_index=False).agg(
        flood_nonregress_rate=("flood_nonregress", "mean"),
        total_overflow_nonregress_rate=("total_overflow_nonregress", "mean"),
        scorecard_pass_rate=("scorecard_pass", "mean"),
        cso_reduction_macro=("cso_reduction_vs_native_pct", "mean"),
        total_overflow_delta_m3=("total_overflow_delta_m3", "sum"),
    )
    grouped["train_safety_feasible"] = (
        grouped.flood_nonregress_rate.eq(1.0)
        & grouped.total_overflow_nonregress_rate.eq(1.0))
    grouped = grouped.sort_values(
        ["train_safety_feasible", "flood_nonregress_rate",
         "total_overflow_nonregress_rate", "cso_reduction_macro"],
        ascending=[False, False, False, False],
    )
    grouped.to_csv(out / "summary.csv", index=False)
    best = grouped.iloc[0].to_dict()
    theta = {**DEFAULT_THETA, "theta_f": float(best["theta_f"]),
             "theta_f_open": float(best["theta_f_open"])}
    config.update(theta=theta,
                  train_safety_feasible=bool(best["train_safety_feasible"]))
    (out / "run_config.json").write_text(json.dumps(config, indent=1, default=float))
    (out / "theta.json").write_text(json.dumps({
        "theta": theta,
        "train_safety_feasible": bool(best["train_safety_feasible"]),
        "selection_summary": best,
        "research_status": status["research_status"],
        "hydraulic_gate_passed": status["hydraulic_gate_passed"],
    }, indent=1, default=float))
    print(grouped.to_string(index=False))
    print(json.dumps({"selected_theta": theta,
                      "train_safety_feasible": bool(best["train_safety_feasible"])},
                     indent=1))


if __name__ == "__main__":
    main()

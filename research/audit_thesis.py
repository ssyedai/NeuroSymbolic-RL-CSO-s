"""Reproduce a validation-only audit of saved v8 logs; never opens final_eval.csv.

Usage: python -m research.audit_thesis --run runs/v8_full_s0
No SWMM runs, checkpoint selection, or scenario modifications are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def audit(run: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(run / "train_log.csv")
    val = pd.read_csv(run / "eval_log.csv")
    if not val.split.isin(["train", "val"]).all():
        raise ValueError("Audit input contains test rows; use validation-only logs")
    val = val[val.split == "val"].copy()
    if val.empty:
        raise ValueError("No validation records")
    rows = []
    for episode, group in val.groupby("episode"):
        scored = group[np.isfinite(group.cso_reduction_vs_native_pct)]
        rows.append(dict(
            episode=int(episode), n_events=len(group), n_parents=group.parent.nunique(),
            native_cso_reduction_macro_pct=scored.cso_reduction_vs_native_pct.mean(),
            native_cso_reduction_rung_macro_pct=scored.groupby("rung").cso_reduction_vs_native_pct.mean().mean(),
            flood_nonregress_rate=group.flood_nonregress.eq(True).mean(),
            zero_when_feasible_rate=group.flood_zero_when_feasible.eq(True).mean(),
            intervention_rate=group.intervention_rate.mean(),
        ))
    checkpoints = pd.DataFrame(rows)
    checkpoints.to_csv(out / "validation_checkpoints.csv", index=False)
    latest = val[val.episode == val.episode.max()]
    # Repeated children are averaged within parent before the descriptive mean.
    parents = latest.groupby(["family", "rung", "parent"], dropna=False).agg(
        native_cso_reduction_pct=("cso_reduction_vs_native_pct", "mean"),
        flood_nonregress_rate=("flood_nonregress", "mean"),
        storage_first_satisfaction_rate=("sat_storage_first", "mean"),
    ).reset_index()
    parents.to_csv(out / "validation_parent_metrics.csv", index=False)
    families = parents.groupby(["family", "rung"], dropna=False).agg(
        n_parents=("parent", "nunique"),
        native_cso_reduction_parent_macro_pct=("native_cso_reduction_pct", "mean"),
        flood_nonregress_rate=("flood_nonregress_rate", "mean"),
    ).reset_index()
    families.to_csv(out / "validation_by_rung.csv", index=False)
    ctrl = pd.read_csv("runs/controllability.csv")
    if not ctrl.split.isin(["train", "val"]).all():
        raise ValueError("Controllability records contain test events")
    unsafe = ctrl[ctrl.best_flood > 1.02 * ctrl.ref_flood + 10]
    unsafe.to_csv(out / "unsafe_hindsight.csv", index=False)
    onset = pd.read_csv("runs/onset_table.csv")
    summary = dict(
        scope="saved train/validation results only; no test evaluation or tuning",
        run=str(run), episodes=len(train), seed=0,
        validation_events_per_checkpoint=int(checkpoints.n_events.min()),
        validation_parent_count=int(latest.parent.nunique()),
        validation_flood_nonregress_min=float(checkpoints.flood_nonregress_rate.min()),
        validation_flood_nonregress_max=float(checkpoints.flood_nonregress_rate.max()),
        validation_checkpoints_meeting_95pct=int((checkpoints.flood_nonregress_rate >= .95).sum()),
        lam_below_50_fraction=float((train.lam < 50).mean()),
        lam_at_least_49_9_fraction=float((train.lam >= 49.9).mean()),
        mean_cost_by_quarter=train.groupby(np.arange(len(train)) * 4 // len(train)).ep_cost.mean().tolist(),
        hindsight_unsafe_count=len(unsafe), hindsight_count=len(ctrl),
        onset_median=float(onset.k_onset.median()),
        onset_parent_count=len(onset), observed_parents_with_cso_above_1=int((onset.cso_at_k1 > 1).sum()),
        missing_routing_error=int(latest.routing_error_pct.isna().sum()),
        missing_runoff_error=int(latest.runoff_error_pct.isna().sum()),
        validation_rungs_below_3_parents=families.loc[families.n_parents < 3, "rung"].tolist(),
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [run / "train_log.csv", run / "eval_log.csv",
                                 Path("runs/controllability.csv"), Path("runs/onset_table.csv")]},
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    axes[0, 0].plot(checkpoints.episode, 100 * checkpoints.flood_nonregress_rate, label="V8 validation")
    axes[0, 0].axhline(95, color="black", linestyle="--", label="Required 95%")
    axes[0, 0].set(title="Flood non-regression", ylabel="Passing events (%)", ylim=(0, 105))
    axes[0, 0].legend()
    axes[0, 1].plot(checkpoints.episode, checkpoints.native_cso_reduction_rung_macro_pct)
    axes[0, 1].set(title="CSO reduction vs true native", ylabel="Mean over rung means (%)")
    axes[1, 0].plot(train.episode, train.lam)
    axes[1, 0].set(title="Safety multiplier", ylabel="Lambda (dimensionless)")
    axes[1, 1].plot(train.episode, train.ep_cost.rolling(50, min_periods=1).mean())
    axes[1, 1].set(title="Episode cost: rolling 50-episode mean", ylabel="Normalized cost (dimensionless)")
    for ax in axes.flat:
        ax.set_xlabel("Training episode")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("V8 seed 0: CSO improvement does not establish flood safety\n"
                 "Source: saved train_log.csv / eval_log.csv; episodes 1–1000; validation only", fontsize=12)
    fig.savefig(out / "validation_audit.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != "source_sha256"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("runs/v8_full_s0"))
    parser.add_argument("--out", type=Path, default=Path("runs/thesis_audit_20261010"))
    args = parser.parse_args()
    audit(args.run, args.out)

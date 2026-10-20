"""Verify the candidate on matched inputs, retaining all failed cases."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research.weir_reproduction import discharge


def validate_pair(baseline, candidate):
    if baseline.index.duplicated().any() or candidate.index.duplicated().any():
        raise ValueError("Duplicate case")
    if set(baseline.index) != set(candidate.index):
        raise ValueError("Unmatched cases")
    if not baseline.sort_index().input_sha256.equals(candidate.sort_index().input_sha256):
        raise ValueError("Different hydraulic inputs")
    numeric = ["max_late_flow_error_cfs", "outflow_error_pct", "routing_error_pct", "flooding_ft3"]
    if not np.isfinite(candidate[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite candidate results")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", default="Weir-flow check", help="Explicit candidate name for figures")
    args = parser.parse_args()
    baseline = pd.read_csv(args.baseline/"results.csv").set_index("case")
    candidate = pd.read_csv(args.candidate/"results.csv").set_index("case")
    validate_pair(baseline, candidate)
    for root, df in ((args.baseline, baseline), (args.candidate, candidate)):
        cfg = json.loads((root/"run_config.json").read_text())
        expected = {f"{regime}_{method}_{profile}_{step:g}" for regime in ("free", "submerged")
                    for method in cfg["methods"] for profile in cfg["profiles"] for step in cfg["steps_s"]}
        if len(df) != cfg["expected_runs"] or set(df.index) != expected:
            raise ValueError("Incomplete experiment")
    # Recompute the original verification decision rather than trusting a stored Boolean.
    verified = ((candidate.max_late_flow_error_cfs <= .65) &
                (candidate.outflow_error_pct.abs() <= 1) &
                (candidate.routing_error_pct.abs() <= 1) & (candidate.flooding_ft3 == 0))
    if not verified.equals(candidate.equilibrium_verified):
        raise ValueError("Stored verification result disagrees with original criteria")
    candidate["baseline_verified"] = baseline.equilibrium_verified
    candidate["baseline_flow_range_cfs"] = baseline.late_flow_range_cfs
    for name in candidate.index:
        data = pd.read_csv(args.candidate/(name+".csv.gz"))
        late = data[data.seconds >= 300]
        residuals = np.array([discharge(h, t)-q for h, t, q in zip(
            late.storage_head_ft, late.outfall_head_ft, late.flow_cfs)])
        candidate.loc[name, "max_late_final_head_constitutive_residual_cfs"] = np.abs(residuals).max()
    summary = dict(candidate_label=args.label, matched_inputs=True, expected_runs=len(candidate),
                   all_cases_verified=bool(verified.all()), production_adoption=False,
                   hashes={str(root/"results.csv"):hashlib.sha256((root/"results.csv").read_bytes()).hexdigest()
                           for root in (args.baseline, args.candidate)}, groups={})
    for regime in ("free", "submerged"):
        group = candidate[candidate.index.str.startswith(regime+"_")]
        summary["groups"][regime] = dict(cases=len(group), baseline_verified=int(group.baseline_verified.sum()),
            candidate_verified=int(group.equilibrium_verified.sum()),
            max_late_flow_range_cfs=float(group.late_flow_range_cfs.max()),
            max_final_head_constitutive_residual_cfs=float(group.max_late_final_head_constitutive_residual_cfs.max()),
            failures=group[~group.equilibrium_verified].index.tolist())
    args.out.mkdir(parents=True, exist_ok=True)
    candidate.to_csv(args.out/"comparison.csv")
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2))
    (args.out/"report_source.py").write_bytes(Path(__file__).read_bytes())
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey="row")
    for row, step in enumerate((1, .5)):
        for col, root in enumerate((args.baseline, args.candidate)):
            name = f"submerged_EXTRAN_tight_{step:g}"
            data = pd.read_csv(root/(name+".csv.gz"))
            data = data[data.seconds.between(300, 320)]
            axes[row, col].plot(data.seconds, data.flow_cfs, linewidth=1.3, label="Computed flow")
            axes[row, col].axhline(65, color="black", linestyle="--", label="Exact equilibrium: 65 CFS")
            axes[row, col].set_title(f"{'Original' if col == 0 else args.label} — {step:g} s routing")
            axes[row, col].set_ylabel("Weir flow (CFS)")
            axes[row, col].set_xlabel("Elapsed time (s)")
            axes[row, col].grid(alpha=.25)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle(f"Matched isolated submerged-weir test: {args.label}\n40 trials, 1e-4 ft head tolerance, original damping 0.5; EXTRAN shown")
    fig.tight_layout(rect=(0,0,1,.93))
    fig.savefig(args.out/"flow_guard.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

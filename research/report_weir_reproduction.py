"""Compare isolated numerical experiments; preserve failures and source hashes."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root
    folders = ["weir_isolated", "weir_source_baseline", "weir_source_damped"]
    frames = {}
    hashes = {}
    for folder in folders:
        path = root/folder/"results.csv"
        cfg = json.loads((root/folder/"run_config.json").read_text())
        df = pd.read_csv(path).set_index("case")
        if len(df) != cfg["expected_runs"] or df.index.duplicated().any():
            raise ValueError("Incomplete or duplicate experiment")
        expected = {f"{regime}_{method}_{profile}_{step:g}" for regime in ("free", "submerged")
                    for method in cfg["methods"] for profile in cfg["profiles"] for step in cfg["steps_s"]}
        if set(df.index) != expected:
            raise ValueError("Unexpected case coverage")
        df["net_balance_relative_to_inflow_pct"] = 100*(df.inflow_ft3-df.outflow_ft3+
            df.initial_storage_ft3-df.final_storage_ft3)/df.inflow_ft3
        frames[folder] = df
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    original, rebuilt = (frames[k].sort_index() for k in folders[:2])
    if not original.input_sha256.equals(rebuilt.input_sha256):
        raise ValueError("Engine comparison used different input files")
    columns = ["outflow_ft3", "mean_late_flow_cfs", "late_flow_range_cfs", "routing_error_pct"]
    differences = {key: float((original[key]-rebuilt[key]).abs().max()) for key in columns}
    summary = dict(input_result_hashes=hashes, installed_vs_source_max_absolute_difference=differences,
                   source_matches_installed=bool(all(np.isfinite(v) and v <= 1e-8 for v in differences.values())),
                   groups={}, production_adoption=False)
    for folder, frame in frames.items():
        summary["groups"][folder] = {}
        for regime in ("free", "submerged"):
            group = frame[frame.index.str.startswith(regime+"_")]
            summary["groups"][folder][regime] = dict(
                cases=len(group), verified=int(group.equilibrium_verified.sum()),
                max_flow_range_cfs=float(group.late_flow_range_cfs.max()),
                max_abs_volume_error_pct=float(group.outflow_error_pct.abs().max()),
                max_abs_balance_inflow_pct=float(group.net_balance_relative_to_inflow_pct.abs().max()))
    output = root/"weir_comparison"
    output.mkdir(exist_ok=True)
    pd.concat([df.assign(engine=k) for k, df in frames.items()]).to_csv(output/"comparison.csv")
    (output/"summary.json").write_text(json.dumps(summary, indent=2))
    (output/"report_source.py").write_bytes(Path(__file__).read_bytes())
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey="row")
    for column, folder in enumerate((folders[0], folders[2])):
        for row, profile in enumerate(("tight", "extra_tight")):
            name = f"submerged_EXTRAN_{profile}_0.5"
            data = pd.read_csv(root/folder/(name+".csv.gz"))
            data = data[data.seconds.between(300, 320)]
            axes[row, column].plot(data.seconds, data.flow_cfs, label="Computed flow", linewidth=1.3)
            axes[row, column].axhline(65, color="black", linestyle="--", label="Exact equilibrium: 65 CFS")
            axes[row, column].set_title(("Installed: damping 0.5" if column == 0 else "Experimental: damping 0.1")+
                                       ("\n40 trials, head tolerance 1e-4 ft" if row == 0 else "\n100 trials, head tolerance 1e-7 ft"))
            axes[row, column].set_xlabel("Elapsed time (s)")
            axes[row, column].set_ylabel("Weir flow (CFS)")
            axes[row, column].grid(alpha=.25)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Isolated submerged weir: constant inflow and tailwater, 0.5 s routing\nEXTRAN shown; SLOT gives identical results in this isolated model")
    fig.tight_layout(rect=(0, 0, 1, .93))
    fig.savefig(output/"flow_verification.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

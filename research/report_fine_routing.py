"""Static thesis-diagnostic figure; all profiles shown, no favorable selection."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folders", nargs="+")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    frames, summaries = [], {}
    for folder in args.folders:
        folder = Path(folder)
        cfg = json.loads((folder / "run_config.json").read_text())
        summary = json.loads((folder / "summary.json").read_text())
        if not summary["complete"]:
            raise ValueError(f"Incomplete experiment: {folder}")
        df = pd.read_csv(folder / "results.csv")
        if len(df) != cfg["expected_runs"] or not df.split.eq("train").all():
            raise ValueError(f"Invalid experiment: {folder}")
        label = ("40 trials, head tol. 0.0001 ft" if cfg.get("max_trials") == 40 else
                 "8 trials, head tol. 0.005 ft")
        label += "; rules each step" if cfg["rule_seconds"] == 0 else "; rules each 1 s"
        label = str(cfg.get("surcharge_method", "EXTRAN")) + ": " + label
        df["profile"] = label
        frames.append(df)
        summaries[folder.name] = dict(passed=summary["passed"], n_runs=len(df),
            comparisons_passed=sum(c["passed"] for c in summary["comparisons"]),
            comparisons_total=len(summary["comparisons"]),
            maximum_absolute_continuity_pct=float(df.routing_error_pct.abs().max()))
    df = pd.concat(frames, ignore_index=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "combined_results.csv", index=False)
    (out / "comparison_summary.json").write_text(json.dumps(summaries, indent=2))
    (out / "run_config.json").write_text(json.dumps(dict(
        purpose="Descriptive convergence comparison; no controller selection",
        inputs={str(Path(f) / "results.csv"): hashlib.sha256((Path(f) / "results.csv").read_bytes()).hexdigest()
                for f in args.folders},
        code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        split="train", thresholds_changed=False), indent=2))
    parents = sorted(df.storm_id.unique())
    fig, axes = plt.subplots(2, 3, figsize=(14, 7), squeeze=False)
    for col, parent in enumerate(parents):
        for row, metric in enumerate(("cso_total", "flood_total")):
            ax = axes[row, col]
            subset = df[(df.storm_id == parent) & df.case.isin(["native", "static_half"])]
            for (profile, case), group in subset.groupby(["profile", "case"]):
                g = group.sort_values("routing_seconds", ascending=False)
                ax.plot(g.routing_seconds, g[metric], marker="o", linestyle="-" if case == "native" else "--",
                        label=f"{case}: {profile}")
            ax.set_xscale("log", base=2)
            ax.set_xticks([1, 0.5, 0.25], ["1", "0.5", "0.25"])
            ax.invert_xaxis()
            ax.grid(alpha=0.25)
            ax.set_ylabel("CSO (m³)" if row == 0 else "Nodal flooding (m³)")
            if row == 0:
                ax.set_title(parent.split("_")[1][:8] + " — TRAIN T10")
            else:
                ax.set_xlabel("Maximum routing step (seconds)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, fontsize=8)
    fig.suptitle("Hydraulic convergence diagnostics — native pump safeguards retained\nSame rainfall; original gate travel times; no TEST data", fontsize=13)
    fig.tight_layout(rect=(0, 0.12, 1, 0.91))
    fig.savefig(out / "routing_convergence.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()

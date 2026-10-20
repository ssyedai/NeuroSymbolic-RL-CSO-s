"""Compare identical recorded times and axes; no independently chosen zooms."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    root = Path("runs/hydraulic_validation_20261011")
    folders = ("routing_trace", "slot_routing_trace")
    summary = json.loads((root / folders[0] / "trace_summary.json").read_text())
    centre = next(r["jump_time_seconds"] for r in summary if r["routing_seconds"] == .25)
    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=True, sharey="row")
    for col, (folder, method) in enumerate(zip(folders, ("EXTRAN", "SLOT"))):
        d = pd.read_csv(root / folder / "step_0.25.csv.gz")
        d = d[d.seconds.between(centre-15, centre+15)]
        if len(d) < 100:
            raise ValueError("Matched trace window incomplete")
        x = d.seconds-centre
        axes[0,col].plot(x, d["3529_A.head_ft"], label="3529_A")
        axes[0,col].plot(x, d["3530.head_ft"], label="3530")
        axes[0,col].axhline(603.49, color="grey", linestyle=":", label="3529_A pipe crown")
        axes[0,col].set_title(method)
        axes[1,col].plot(x, d["35291_B.flow_cfs"], color="tab:orange")
        axes[1,col].set_xlabel(f"Seconds relative to {centre:g} s of simulation")
        for ax in axes[:,col]:
            ax.grid(alpha=.25)
    axes[0,0].set_ylabel("Head (ft)")
    axes[1,0].set_ylabel("Bypass flow (CFS)")
    axes[0,1].legend(fontsize=8)
    fig.suptitle("Same TRAIN storm, 0.25 s routing, fixed half-open gates, native pump rules\nIdentical 30-second window and axis scales; numerical diagnostic only")
    fig.tight_layout(rect=(0,0,1,.9))
    fig.savefig(root / "surcharge_comparison" / "matched_trace.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()

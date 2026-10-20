"""Summarize routing-step oscillations without treating disjoint windows as steps."""
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
    parser.add_argument("folder")
    args = parser.parse_args()
    root = Path(args.folder)
    config = json.loads((root / "run_config.json").read_text())
    method = "SLOT" if config.get("surcharge_method") == "SLOT" else "EXTRAN"
    results = json.loads((root / "results.json").read_text())
    if len(results) != config["expected_runs"]:
        raise ValueError("Trace experiment incomplete")
    summary = []
    fig, axes = plt.subplots(len(results), 2, figsize=(13, 3*len(results)), squeeze=False)
    for i, result in enumerate(results):
        dt = result["routing_seconds"]
        d = pd.read_csv(root / f"step_{dt:g}.csv.gz")
        contiguous = d.seconds.diff().le(1.01*dt)
        jump = d["3529_A.head_ft"].diff().abs().where(contiguous)
        index = jump.idxmax()
        centre = float(d.seconds[index])
        window = d[d.seconds.between(centre-15, centre+15)]
        pump_changes = {}
        for pump in ("PUMP27@35395-3535", "PUMP28@35390-3535"):
            pump_changes[pump] = int((window[pump+".setting"].diff().abs()>1e-8).sum())
        summary.append(dict(routing_seconds=dt, cso_total=result["cso_total"], flood_total=result["flood_total"],
            routing_error_pct=result["routing_error_pct"], max_3529A_head_jump_ft=float(jump[index]),
            jump_time_seconds=centre, pump_changes_within_15_seconds=pump_changes,
            bypass_target_changes_in_trace=int((d["35291_B.target"].diff().abs()>1e-8).sum()),
            max_bypass_flow_jump_cfs=float(d["35291_B.flow_cfs"].diff().abs().where(contiguous).max()),
            source_sha256=hashlib.sha256((root / f"step_{dt:g}.csv.gz").read_bytes()).hexdigest()))
        x = window.seconds-centre
        axes[i, 0].plot(x, window["3529_A.head_ft"], label="3529_A")
        axes[i, 0].plot(x, window["3530.head_ft"], label="3530")
        axes[i, 0].axhline(603.49, color="grey", linestyle=":", label="3529_A pipe crown")
        axes[i, 0].set_ylabel(f"dt={dt:g} s\nHead (ft)")
        axes[i, 1].plot(x, window["35291_B.flow_cfs"], color="tab:orange")
        axes[i, 1].set_ylabel("Bypass flow (CFS)")
        for ax in axes[i]:
            ax.grid(alpha=.25)
            ax.set_xlabel("Seconds relative to largest head jump in recorded windows")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle(f"{method} routing-step trace: fixed half-open gates, native pumps — TRAIN 2010-07-19 T10\nEach row shows its own largest head jump; direct stepping, not 900-second stride")
    fig.tight_layout(rect=(0, 0, 1, .91))
    fig.savefig(root / "head_flow_jumps.png", dpi=180)
    plt.close(fig)
    (root / "trace_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

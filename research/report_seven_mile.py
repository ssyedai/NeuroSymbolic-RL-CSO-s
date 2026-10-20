"""Describe recorded weir oscillations; never infer controller performance."""
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
    cfg = json.loads((root / "run_config.json").read_text())
    results = json.loads((root / "results.json").read_text())
    if len(results) != cfg["expected_runs"]:
        raise ValueError("Incomplete trace")
    summaries = []
    for result in results:
        step = result["routing_seconds"]
        source = root / f"step_{step:g}.csv.gz"
        data = pd.read_csv(source)
        dt = data.seconds.diff()
        contiguous = (dt > 0) & (dt <= 1.01 * step)
        jumps = data["35444.flow_cfs"].diff().abs().where(contiguous)
        centre = float(data.loc[jumps.idxmax(), "seconds"])
        selected = data[data.seconds.between(centre-10, centre+10)]
        changes = {name: int((data[name].diff().abs().where(contiguous) > 1e-8).sum())
                   for name in data if name.endswith(".target")}
        balance = {}
        for node in ("35440", "35442"):
            net = data[f"{node}.inflow_cfs"] - data[f"{node}.outflow_cfs"]
            residual = (data[f"{node}.volume_ft3"].diff() - .5*(net+net.shift())*dt).where(contiguous)
            balance[node] = dict(signed_ft3=float(residual.sum()),
                                 absolute_ft3=float(residual.abs().sum()))
        summary = dict(routing_seconds=step, max_weir_flow_jump_cfs=float(jumps.max()),
                       centre_seconds=centre, target_changes_recorded_windows=changes,
                       storage_volume_balance_proxy=balance,
                       caveat="Recorded windows only. Storage-volume proxy omits computational storage in connected links.",
                       source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        summaries.append(summary)
        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        x = selected.seconds-centre
        axes[0].plot(x, (selected["35440.head_ft"]-selected["65.head_ft"])*1e4)
        axes[0].axhline(0, color="grey", linewidth=.7)
        axes[0].set_ylabel("Upstream minus downstream\nhead (10⁻⁴ ft)")
        axes[1].plot(x, selected["35444.flow_cfs"], color="tab:orange")
        axes[1].set_ylabel("Weir 35444 flow (CFS)")
        axes[2].plot(x, selected["1360_B.setting"], label="Gate 1360_B actual")
        axes[2].plot(x, selected["1360_B.target"], linestyle="--", label="Gate target")
        axes[2].set_ylabel("Gate setting")
        axes[2].set_ylim(-.05, 1.05)
        axes[2].legend()
        axes[2].set_xlabel(f"Seconds relative to t={centre:g} s")
        for ax in axes:
            ax.grid(alpha=.25)
        fig.suptitle(f"{cfg['cases']} — {cfg['storm_ids'][0]}: submerged outfall weir\n"
                     f"{cfg['surcharge_method']}, {step:g} s routing, {cfg['max_trials']} trials, "
                     f"{cfg['head_tolerance_ft']:g} ft head tolerance")
        fig.tight_layout()
        fig.savefig(root / f"weir_trace_{step:g}.png", dpi=180)
        plt.close(fig)
    (root / "weir_summary.json").write_text(json.dumps(summaries, indent=2))
    (root / "report_source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()

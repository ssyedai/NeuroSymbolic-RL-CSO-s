"""Descriptive scientific figure for the fixed diagnostic (no test data)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    root = Path("runs/complete_overflow_check_20261010")
    df = pd.read_csv(root / "diagnostic.csv")
    assert set(df.split) <= {"train", "val"}
    assert len(df) == 24 and df.groupby(["split", "policy"]).parent.nunique().eq(3).all()
    policies = ["native", "static_half", "bypass_closed", "candidate_rules"]
    val = df[df.split == "val"]
    summary = {}
    for (split, policy), rows in df.groupby(["split", "policy"]):
        summary[f"{split}/{policy}"] = dict(
            events=len(rows), parents=rows.parent.nunique(),
            cso_m3=rows.cso_total.sum(), flood_m3=rows.flood_total.sum(),
            total_overflow_m3=rows.total_overflow_vol_m3.sum(),
            flood_nonregress_rate=rows.flood_nonregress.mean(),
            zero_when_feasible_rate=rows.flood_zero_when_feasible.mean(),
            scorecard_pass_rate=rows.scorecard_pass.mean(),
            intervention_rate=rows.intervention_rate.mean())
    relative_outlet_error = np.abs(df.outflow_balance_difference_m3) / df.system_outflow_vol_m3
    summary["validity"] = dict(
        max_outlet_accounting_difference_pct=100 * relative_outlet_error.max(),
        max_flood_accounting_difference_m3=np.abs(df.flood_balance_difference_m3).max(),
        routing_error_range_pct=[df.routing_error_pct.min(), df.routing_error_pct.max()],
        runoff_error_range_pct=[df.runoff_error_pct.min(), df.runoff_error_pct.max()],
        steps=sorted(df.simulated_steps.unique().tolist()),
        interpretation="Descriptive six-event diagnostic; not trained RL, no test evaluation, no confidence intervals")
    (root / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    plt.rcParams.update({"font.size": 10})
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), constrained_layout=True)
    colors = ["#4c5866", "#8098af", "#b99a62", "#317e87"]
    for col, storm in enumerate(sorted(val.storm_id.unique())):
        rows = val[val.storm_id == storm].set_index("policy").loc[policies]
        for r, (metric, label) in enumerate((("flood_total", "Nodal flooding (m³)"), ("cso_total", "All four CSO outfalls (m³)"))):
            ax = axes[r, col]
            values = rows[metric].to_numpy()
            bars = ax.bar(range(4), values, color=colors)
            ax.bar_label(bars, labels=[f"{v:,.0f}" for v in values], fontsize=9, padding=3)
            ax.set_ylim(0, max(values.max() * 1.25, 1))
            ax.set_xticks(range(4), ["Native", "Half-open", "Bypass shut", "Rules"], rotation=20)
            ax.set_ylabel(label)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_title(storm.removeprefix("USC00200230_") + " (amplified)")
    fig.suptitle("Complete overflow diagnostic: lower CSO can hide worse flooding\nThree fixed validation parents · rules prototype, not trained RL", fontsize=15)
    fig.savefig(root / "validation_diagnostic.png", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()

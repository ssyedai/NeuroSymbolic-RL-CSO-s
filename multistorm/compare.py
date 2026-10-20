"""Aggregate several seeds / experiment runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


METRICS = [
    "cso_red_macro", "cso_red_median", "cso_red_worst", "cso_red_micro",
    "frac_improved", "flood_ratio_mean", "r6_excess_mean", "score_adv_mean",
]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--out", default="runs/compare")
    args = p.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in args.runs:
        path = Path(r) / "final_agg.json"
        if not path.exists():
            print(f"skip missing {path}")
            continue
        agg = json.loads(path.read_text())
        for sp in ("train", "val", "test"):
            if sp not in agg or not isinstance(agg[sp], dict):
                continue
            row = {"run": r, "split": sp}
            row.update({m: agg[sp].get(m, np.nan) for m in METRICS})
            rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        print("No data")
        return
    summary = (df.groupby("split")[METRICS]
               .agg(["mean", "std"])
               .reset_index())
    # flatten columns
    summary.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c
                       for c in summary.columns.to_flat_index()]
    summary.to_csv(out / "compare.csv", index=False)
    print(summary.to_string(index=False))

    # plot macro CSO reduction mean±std
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, sp in enumerate(["train", "val", "test"]):
        sub = df[df.split == sp]
        if sub.empty:
            continue
        m = sub.cso_red_macro.mean()
        s = sub.cso_red_macro.std(ddof=0)
        ax.bar(i, m, yerr=s, capsize=5, label=sp)
    ax.set_xticks(range(3))
    ax.set_xticklabels(["train", "val", "test"])
    ax.set_ylabel("CSO reduction % (macro)")
    ax.set_title("Seed aggregation")
    ax.axhline(0, color="gray", ls=":")
    fig.tight_layout()
    fig.savefig(out / "compare.png", dpi=140)
    plt.close(fig)
    print(f"Wrote {out / 'compare.csv'} and compare.png")


if __name__ == "__main__":
    main()

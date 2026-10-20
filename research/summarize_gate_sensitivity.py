"""Summarise a completed train-only gate diagnostic without selecting a policy."""
import json
from pathlib import Path

import pandas as pd

from multistorm.metrics_v8 import enrich


def main():
    root = Path("runs/hydraulic_validation_20261011/owned_gates")
    df = pd.read_csv(root / "gate_sensitivity.csv")
    assert len(df) == 48 and df.groupby("storm_id").size().eq(16).all()
    assert df.split.eq("train").all()
    assert df.target_vs_command_max_error.max() <= 1e-6
    comparisons, parents = [], []
    for storm_id, group in df.groupby("storm_id"):
        ref = group[group.case == "native"].iloc[0].to_dict()
        static = group[group.case == "static_half"].iloc[0]
        for row in group.to_dict("records"):
            metrics = enrich(row, ref)
            comparisons.append({**row, **metrics,
                                "cso_delta_vs_static_m3": row["cso_total"]-static.cso_total,
                                "flood_delta_vs_static_m3": row["flood_total"]-static.flood_total})
        candidate = pd.DataFrame(comparisons)
        candidate = candidate[(candidate.storm_id == storm_id) & (candidate.case != "native")]
        feasible = candidate[candidate.scorecard_pass]
        best = feasible.sort_values(["cso_total", "flood_total"]).iloc[0] if len(feasible) else None
        parents.append(dict(storm_id=storm_id, native_cso_m3=ref["cso_total"],
                            native_flood_m3=ref["flood_total"], candidates=len(candidate),
                            feasible_candidates=len(feasible),
                            best_feasible_case=None if best is None else best.case,
                            best_feasible_cso_m3=None if best is None else best.cso_total,
                            best_feasible_flood_m3=None if best is None else best.flood_total))
    pd.DataFrame(comparisons).to_csv(root / "comparisons.csv", index=False)
    summary = dict(scope="Descriptive TRAIN-only sensitivity; not G1/G2 certification or policy selection",
                   parents=parents, simulations=len(df),
                   max_target_error=df.target_vs_command_max_error.max(),
                   max_actual_position_lag=df.actual_vs_command_max_error.max(),
                   routing_error_range_pct=[df.routing_error_pct.min(), df.routing_error_pct.max()])
    (root / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

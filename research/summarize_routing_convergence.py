"""Describe routing-resolution sensitivity; do not select a flattering resolution."""
import json
from pathlib import Path
import pandas as pd


def main():
    root = Path("runs/hydraulic_validation_20261011")
    result = {}
    for folder, expected in (("convergence", 12), ("controlled_convergence", 16)):
        df = pd.read_csv(root / folder / "results.csv")
        if "case" not in df:
            df["case"] = "native"
        assert len(df) == expected and df.split.eq("train").all()
        rows = []
        for (storm, case), group in df.groupby(["storm_id", "case"]):
            indexed = group.set_index("routing_seconds")
            assert set(indexed.index) == {10, 5, 2, 1}
            rows.append(dict(storm_id=storm, case=case,
                             cso_10s_m3=indexed.loc[10, "cso_total"],
                             cso_1s_m3=indexed.loc[1, "cso_total"],
                             flood_10s_m3=indexed.loc[10, "flood_total"],
                             flood_1s_m3=indexed.loc[1, "flood_total"],
                             cso_change_2s_to_1s_m3=indexed.loc[1,"cso_total"]-indexed.loc[2,"cso_total"],
                             flood_change_2s_to_1s_m3=indexed.loc[1,"flood_total"]-indexed.loc[2,"flood_total"],
                             continuity_10s_pct=indexed.loc[10,"routing_error_pct"],
                             continuity_1s_pct=indexed.loc[1,"routing_error_pct"]))
        result[folder] = rows
    result["decision"] = "Not certified converged. Do not rebuild production onset/training references until routing and native rule cadence are fixed and verified. No thresholds relaxed."
    (root / "convergence_summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

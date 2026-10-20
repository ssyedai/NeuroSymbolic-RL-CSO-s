"""Recheck matched synthetic orifice results against the original criteria."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def validate_results(frame):
    expected = {f"{node}_{method}_{flow}_{step:g}" for node in ("junction", "storage")
                for method in ("SLOT", "EXTRAN") for flow in (5, 65) for step in (1, .5, .25)}
    if frame.index.duplicated().any() or set(frame.index) != expected:
        raise ValueError("Incomplete or duplicate case matrix")
    columns = ["inflow_cfs", "max_late_flow_error_cfs", "volume_error_pct",
               "routing_error_pct", "flooding_ft3", "late_flow_range_cfs"]
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite verification result")
    for name, row in frame.iterrows():
        if row.inflow_cfs != float(name.split("_")[2]):
            raise ValueError("Unexpected reference flow")
    passed = ((frame.max_late_flow_error_cfs <= .01*frame.inflow_cfs) &
              (frame.volume_error_pct.abs() <= 1) & (frame.routing_error_pct.abs() <= 1) &
              (frame.flooding_ft3 == 0))
    if not passed.equals(frame.verified):
        raise ValueError("Stored decision disagrees with original criteria")
    return passed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    frames = [pd.read_csv(root/"results.csv").set_index("case").sort_index()
              for root in (args.baseline, args.candidate)]
    decisions = [validate_results(frame) for frame in frames]
    if not frames[0].input_sha256.equals(frames[1].input_sha256):
        raise ValueError("Different hydraulic inputs")
    summary = dict(matched_inputs=True, cases=24, production_adoption=False,
                   baseline_passed=int(decisions[0].sum()), candidate_passed=int(decisions[1].sum()),
                   baseline_failures=decisions[0][~decisions[0]].index.tolist(),
                   candidate_failures=decisions[1][~decisions[1]].index.tolist(),
                   hashes={str(root/"results.csv"): hashlib.sha256((root/"results.csv").read_bytes()).hexdigest()
                           for root in (args.baseline, args.candidate)})
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/"summary.json").write_text(json.dumps(summary, indent=2))
    (args.out/"report_source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

"""Audit read-only iteration logs and retain per-step exit evidence."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research.reversing_orifice import reference_flow


def analyze(trace, samples):
    trace = trace.copy()
    if trace.duplicated(["seconds", "iteration"]).any():
        raise ValueError("Duplicate iteration")
    if not np.isfinite(trace[["seconds","iteration","new_depth","q_used"]]).all().all():
        raise ValueError("Non-finite state")
    for _, group in trace.groupby("seconds"):
        if not np.array_equal(group.iteration, np.arange(len(group))):
            raise ValueError("Missing or reordered iterations")
    # Seconds differ only by floating-point conversion through SWMM days.
    times = samples.seconds.to_numpy()
    for t in trace.seconds.unique():
        if np.min(abs(times-t)) > 1e-7:
            raise ValueError("Iteration time not present in routing samples")
    trace["pre_gap_ft"] = trace.pre_head_s-trace.pre_head_o
    trace["post_gap_ft"] = trace.new_depth+601.292-np.interp(trace.seconds,times,samples.outfall_head_ft)
    trace["post_residual_cfs"] = abs(trace.q_used-reference_flow(trace.post_gap_ft))
    trace["branch"] = np.where(trace.computed == 0, "bypassed",
        np.where(trace.q_raw == 0, "zero", np.where(trace.q_raw > 0, "forward", "reverse")))
    last=trace.groupby("seconds").tail(1).copy()
    converged=last[last.combined_converged == 1]
    return trace,last,dict(traced_steps=len(last),traced_iterations=len(trace),
        capped_steps=int(((last.iteration==39)&(last.combined_converged==0)).sum()),
        declared_converged_steps=len(converged),
        max_residual_at_declared_convergence_cfs=float(converged.post_residual_cfs.max()),
        orifice_area_range_ft2=[float(trace.orifice_area.min()),float(trace.orifice_area.max())],
        effective_node_area_range_ft2=[float(trace.node_effective_area.min()),float(trace.node_effective_area.max())])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--run",type=Path,required=True)
    args=parser.parse_args()
    equivalence=pd.read_csv(args.run/"equivalence.csv")
    if len(equivalence)!=4 or not equivalence[["sampled_outputs_exactly_identical","system_totals_exactly_identical"]].all().all():
        raise ValueError("Instrumentation equivalence not verified")
    summaries={}
    for path in args.run.glob("*_iterations.csv"):
        name=path.name.removesuffix("_iterations.csv")
        trace=pd.read_csv(path,na_values=["nan(ind)"])
        samples=pd.read_csv(args.run/(name+".csv.gz"))
        augmented,exits,summary=analyze(trace,samples)
        augmented.to_csv(args.run/(name+"_annotated.csv"),index=False)
        exits.to_csv(args.run/(name+"_exits.csv"),index=False)
        summaries[name]=summary
    if len(summaries)!=4:
        raise ValueError("Missing trace")
    (args.run/"analysis.json").write_text(json.dumps(summaries,indent=2))
    (args.run/"report_source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summaries,indent=2))


if __name__ == "__main__":
    main()

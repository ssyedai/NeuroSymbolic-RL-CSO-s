"""Four isolated 0.25-second runs; verify logging leaves hydraulic outputs intact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from research.isolated_swmm_dll import run_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    prior = pd.read_csv(args.prior/"results.csv", float_precision="round_trip")
    cfg = json.loads((args.prior/"run_config.json").read_text())
    cfg.update(purpose="Read-only iteration tracing of existing cutoff-crossing cases",
        expected_runs=4, steps_s=[.25], amplitudes_ft=[.001], trace_windows_s=[[0,5],[60,62]],
        prior_directory=str(args.prior.resolve()),
        prior_config_sha256=hashlib.sha256((args.prior/"run_config.json").read_bytes()).hexdigest(),
        trace_engines={key:dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                       for key,path in (("baseline",args.baseline),("candidate",args.candidate))},
        trace_source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                            (Path(__file__),Path("research/prepare_transition_trace.py"),Path("research/isolated_swmm_dll.py"))})
    (args.out/"run_config.json").write_text(json.dumps(cfg,indent=2))
    for name in ("run_transition_trace.py","prepare_transition_trace.py","isolated_swmm_dll.py"):
        (args.out/name).write_bytes((Path("research")/name).read_bytes())
    started = time.monotonic()
    rows=[]
    old = os.environ.get("SWMM_TRANSITION_TRACE")
    try:
        for node in ("junction","storage"):
            case=f"{node}_0.001_0.25"
            for engine,dll in (("baseline",args.baseline),("candidate",args.candidate)):
                name=f"{engine}_{case}"
                path=args.out/(name+".inp")
                path.write_bytes((args.prior/engine/(case+".inp")).read_bytes())
                os.environ["SWMM_TRANSITION_TRACE"]=str((args.out/(name+"_iterations.csv")).resolve())
                samples,final=run_model(dll,path,started)
                reference=pd.read_csv(args.prior/engine/(case+".csv.gz"),float_precision="round_trip")
                data=pd.DataFrame(samples,columns=reference.columns)
                data.to_csv(args.out/(name+".csv.gz"),index=False,compression="gzip")
                original=prior[(prior.case==case)&(prior.engine==engine)].iloc[0]
                identical=np.array_equal(data.to_numpy(),reference.to_numpy())
                totals_identical=all(final[k]==original[k] for k in final)
                if not identical or not totals_identical:
                    raise ValueError(f"Instrumentation changed hydraulic outputs: {name}")
                iterations=pd.read_csv(args.out/(name+"_iterations.csv"))
                if iterations.empty:
                    raise ValueError("No iteration log")
                rows.append(dict(case=case,engine=engine,samples=len(data),iterations=len(iterations),
                    input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    sampled_outputs_exactly_identical=identical,system_totals_exactly_identical=totals_identical))
                pd.DataFrame(rows).to_csv(args.out/"equivalence.csv",index=False)
    finally:
        if old is None:
            os.environ.pop("SWMM_TRANSITION_TRACE",None)
        else:
            os.environ["SWMM_TRANSITION_TRACE"]=old
    (args.out/"summary.json").write_text(json.dumps(dict(complete=len(rows)==4,
        exact_equivalence=True,production_adoption=False,wall_seconds=time.monotonic()-started),indent=2))
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()

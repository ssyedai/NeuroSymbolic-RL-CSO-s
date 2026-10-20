"""Inspect cutoff-crossing results without changing predeclared criteria."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research.reversing_orifice import CUTOFF, reference_flow, summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    frame = pd.read_csv(args.run/"results.csv")
    expected = {(f"{node}_{amp:g}_{step:g}", engine) for node in ("junction", "storage")
                for amp in (.00005, .001) for step in (1, .5, .25) for engine in ("baseline", "candidate")}
    if len(frame) != 24 or set(zip(frame.case, frame.engine)) != expected:
        raise ValueError("Incomplete or duplicate matrix")
    paired = frame.pivot(index="case", columns="engine", values="input_sha256")
    if not paired.baseline.equals(paired.candidate):
        raise ValueError("Unmatched hydraulic inputs")
    extra = []
    for _, row in frame.iterrows():
        path = args.run/row.engine/(row.case+".inp")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row.input_sha256:
            raise ValueError("Changed hydraulic input")
        data = pd.read_csv(args.run/row.engine/(row.case+".csv.gz"))
        decision = summarize(data, row.to_dict(), row.amplitude_ft)
        if decision["verified"] != row.verified:
            raise ValueError("Stored decision differs from recomputation")
        gap = data.storage_head_ft-data.outfall_head_ft
        late = data.seconds >= 60
        wrong = late & (gap.abs() > CUTOFF) & (data.flow_cfs.abs() > .05) & (gap*data.flow_cfs < 0)
        extra.append(dict(case=row.case,engine=row.engine,wrong_direction_samples=int(wrong.sum()),
                          late_samples=int(late.sum())))
    pd.DataFrame(extra).to_csv(args.run/"direction_checks.csv",index=False)
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharex=True)
    for i,node in enumerate(("junction","storage")):
        for engine in ("baseline","candidate"):
            data=pd.read_csv(args.run/engine/(f"{node}_0.001_0.25.csv.gz"))
            data=data[data.seconds.between(60,75)]
            axes[i,0].plot(data.seconds,data.flow_cfs,label=engine,lw=1)
            gap=data.storage_head_ft-data.outfall_head_ft
            axes[i,1].plot(data.seconds,gap,label=engine,lw=1)
        axes[i,0].set_ylabel(f"{node.title()}: flow (CFS)")
        axes[i,1].set_ylabel("Head difference S − O (ft)")
        for cutoff in (-CUTOFF,CUTOFF):
            axes[i,1].axhline(cutoff,color="black",ls="--",lw=.7)
        for ax in axes[i]:
            ax.grid(alpha=.25)
            ax.set_xlabel("Time (s)")
            ax.legend()
    fig.suptitle("Synthetic cutoff crossing: fully open orifice, 0.25 s routing\nBoundary amplitude ±0.001 ft; dashed lines mark ±0.0001 ft cutoff")
    fig.tight_layout(rect=(0,0,1,.92))
    fig.savefig(args.run/"cutoff_crossing.png",dpi=180)
    plt.close(fig)
    summary=dict(matched_inputs=True, decisions_recomputed=True, production_adoption=False,
                 cutoff_jump_limit_cfs=float(reference_flow(CUTOFF+1e-12)),
                 results_sha256=hashlib.sha256((args.run/"results.csv").read_bytes()).hexdigest(),
                 groups=[dict(engine=engine,amplitude_ft=amp,passed=int(group.verified.sum()),cases=len(group))
                         for (engine,amp),group in frame.groupby(["engine","amplitude_ft"])])
    (args.run/"verification.json").write_text(json.dumps(summary,indent=2))
    (args.run/"report_source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()

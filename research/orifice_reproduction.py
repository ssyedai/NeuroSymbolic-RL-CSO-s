"""Analytical fully submerged orifice equilibria for storage/junction endpoints."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import numpy as np
import pandas as pd
from research.weir_reproduction import model_text, TAIL
from research.isolated_swmm_dll import run_model


def orifice_head(flow):
    # SWMM CFS convention: gravity 32.2 ft/s², Cd=.4, full area=7*14.14.
    if not np.isfinite(flow) or flow <= 0:
        raise ValueError("Positive finite inflow required")
    gap = (flow/(.4*7*14.14))**2/64.4
    if gap <= .0001:
        raise ValueError("Analytical reference must be above SWMM's small-head cutoff")
    return TAIL+gap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.out
    root.mkdir(parents=True, exist_ok=False)
    cfg = dict(purpose="Synthetic steady orifice verification, not rainfall", expected_runs=24,
               flows_cfs=[5,65], endpoints=["junction","storage"], methods=["SLOT","EXTRAN"],
               steps_s=[1,.5,.25], head_tolerance_ft=.0001, max_trials=40, duration_s=600,
               processes=1,budget_s=600,seed=None,git_hash=None,manifest_hash=None,theta_hash=None,
               engine=str(args.dll.resolve()),dll_sha256=hashlib.sha256(args.dll.read_bytes()).hexdigest(),
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               criteria=dict(max_late_flow_relative_error=.01,volume_relative_error=.01,
                             abs_routing_error_pct=1,zero_flood=True))
    (root/"run_config.json").write_text(json.dumps(cfg,indent=2))
    (root/"runner_source.py").write_bytes(Path(__file__).read_bytes())
    rows=[]
    began=time.monotonic()
    for flow in cfg["flows_cfs"]:
        head=orifice_head(flow)
        for endpoint in cfg["endpoints"]:
            for method in cfg["methods"]:
                for dt in cfg["steps_s"]:
                    name=f"{endpoint}_{method}_{flow:g}_{dt:g}"
                    text=model_text(dt,method,40,.0001,TAIL)
                    node=(f"[JUNCTIONS]\nS 601.292 28 {head-601.292:.12f} 0 0\n" if endpoint=="junction" else
                          f"[STORAGE]\nS 601.292 28 {head-601.292:.12f} FUNCTIONAL 0 0 24231.285 0 0\n")
                    text=re.sub(r"\[STORAGE\].*?(?=\[OUTFALLS\])",node,text,flags=re.S)
                    text=text.replace("[WEIRS]\nW S O TRANSVERSE 26.48 3 NO 0 0 YES", "[ORIFICES]\nW S O SIDE 0 0.4 NO 0.117")
                    text=text.replace("W RECT_OPEN 10 95 0 0","W RECT_CLOSED 7 14.14 0 0")
                    text=text.replace('S FLOW "" FLOW 1 1 65.0',f'S FLOW "" FLOW 1 1 {flow}')
                    path=root/(name+".inp")
                    path.write_text(text)
                    samples, final=run_model(args.dll,path,began)
                    d=pd.DataFrame(samples,columns=["seconds","storage_head_ft","outfall_head_ft","flow_cfs","volume_ft3"])
                    d.to_csv(root/(name+".csv.gz"),index=False,compression="gzip")
                    late=d[d.seconds>=300]
                    error=float((late.flow_cfs-flow).abs().max())
                    volume_error=100*(final["outflow_ft3"]/(flow*600)-1)
                    passed=bool(np.isfinite([error,volume_error,final["routing_error_pct"]]).all() and
                                error<=.01*flow and abs(volume_error)<=1 and
                                abs(final["routing_error_pct"])<=1 and final["flooding_ft3"]==0)
                    rows.append(dict(case=name,endpoint=endpoint,method=method,inflow_cfs=flow,step=dt,
                        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),equilibrium_head_ft=head,
                        max_late_flow_error_cfs=error,late_flow_range_cfs=float(late.flow_cfs.max()-late.flow_cfs.min()),
                        volume_error_pct=volume_error,verified=passed,**final))
                    pd.DataFrame(rows).to_csv(root/"results.csv",index=False)
    summary=dict(complete=len(rows)==cfg["expected_runs"],verified=sum(r["verified"] for r in rows),runs=len(rows))
    (root/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

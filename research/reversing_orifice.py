"""Bounded synthetic cutoff/reversal diagnostic; no rainfall or policy data."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import time

import numpy as np
import pandas as pd

from research.isolated_swmm_dll import run_model
from research.weir_reproduction import model_text, TAIL

CUTOFF = .0001


def reference_flow(gap):
    """Pinned SWMM fully submerged, fully open side-orifice branch, CFS."""
    gap = np.asarray(gap, dtype=float)
    if not np.isfinite(gap).all():
        raise ValueError("Non-finite head gap")
    return np.where(np.abs(gap) <= CUTOFF, 0.,
                    np.sign(gap)*.4*7*14.14*np.sqrt(64.4*np.abs(gap)))


def boundary_points(amplitude):
    if amplitude not in (.00005, .001):
        raise ValueError("Use the predeclared boundary amplitudes")
    # Piecewise-linear stage: centre, alternating peaks every 30 s, centre.
    return [(0, TAIL)] + [(t, TAIL+amplitude*(1 if i % 2 == 0 else -1))
                         for i, t in enumerate(range(15, 600, 30))] + [(600, TAIL)]


def reversing_model(step, endpoint, amplitude):
    if step not in (1, .5, .25) or endpoint not in ("junction", "storage"):
        raise ValueError("Outside diagnostic matrix")
    text = model_text(step, "SLOT", 40, .0001, TAIL)
    node = (f"[JUNCTIONS]\nS 601.292 28 {TAIL-601.292:.12f} 0 0\n" if endpoint == "junction" else
            f"[STORAGE]\nS 601.292 28 {TAIL-601.292:.12f} FUNCTIONAL 0 0 24231.285 0 0\n")
    text = re.sub(r"\[STORAGE\].*?(?=\[OUTFALLS\])", node, text, flags=re.S)
    text = text.replace(f"O 602.797 FIXED {TAIL} YES", "O 602.797 TIMESERIES STAGE NO")
    text = text.replace("[WEIRS]\nW S O TRANSVERSE 26.48 3 NO 0 0 YES",
                        "[ORIFICES]\nW S O SIDE 0 0.4 NO 0.117")
    text = text.replace("W RECT_OPEN 10 95 0 0", "W RECT_CLOSED 7 14.14 0 0")
    series = "[TIMESERIES]\n" + "\n".join(
        f"STAGE 01/01/2020 00:{t//60:02d}:{t%60:02d} {h:.12f}" for t, h in boundary_points(amplitude))+"\n"
    text = re.sub(r"\[INFLOWS\].*?(?=\[REPORT\])", series, text, flags=re.S)
    return text.replace("Synthetic isolated weir verification", "Synthetic reversing orifice verification")


def summarize(data, final, amplitude, flow_law=reference_flow):
    values = data.to_numpy(dtype=float)
    if len(data) < 2 or not np.isfinite(values).all() or not (np.diff(data.seconds) > 0).all():
        raise ValueError("Incomplete or invalid routing trace")
    points = np.array(boundary_points(amplitude))
    boundary_error = float(np.max(np.abs(data.outfall_head_ft-np.interp(data.seconds, *points.T))))
    if boundary_error > 1e-8 or data.seconds.iloc[-1] < 599:
        raise ValueError("Boundary timing or simulation duration not verified")
    if min(data.storage_head_ft.min(), data.outfall_head_ft.min()) <= 608.292:
        raise ValueError("Analytical branch requires fully submerged orifice")
    gap = data.storage_head_ft-data.outfall_head_ft
    expected = flow_law(gap)
    residual = np.abs(data.flow_cfs-expected)
    late = data.seconds >= 60
    dt = np.diff(np.r_[0., data.seconds.to_numpy()])
    throughput = float(np.sum(np.abs(data.flow_cfs)*dt))
    inflow = sum(final["system_"+k] for k in ("dwInflow", "wwInflow", "gwInflow", "iiInflow", "exInflow"))
    balance = (final["system_initStorage"]+inflow-final["system_finalStorage"]-
               sum(final["system_"+k] for k in ("outflow", "flooding", "evapLoss", "seepLoss")))
    # An absolute floor protects the quiescent test; report the raw balance too.
    balance_pass = abs(balance) <= max(.01, .01*throughput)
    flow_pass = bool((residual[late] <= .05).all())
    nonzero_sign = np.sign(data.loc[late & (data.flow_cfs.abs() > .001), "flow_cfs"].to_numpy())
    return dict(boundary_error_ft=boundary_error, max_late_residual_cfs=float(residual[late].max()),
                fraction_late_residual_above_005=float((residual[late] > .05).mean()),
                max_late_cutoff_flow_cfs=float(data.loc[late & (gap.abs() <= CUTOFF), "flow_cfs"].abs().max())
                    if (late & (gap.abs() <= CUTOFF)).any() else None,
                late_flow_reversals=int(np.sum(nonzero_sign[1:] != nonzero_sign[:-1])),
                late_gap_min_ft=float(gap[late].min()), late_gap_max_ft=float(gap[late].max()),
                gross_link_volume_rectangular_ft3=throughput, system_balance_residual_ft3=balance,
                flow_residual_pass=flow_pass, balance_pass=bool(balance_pass),
                verified=bool(flow_pass and balance_pass and abs(final["routing_error_pct"]) <= 1
                              and final["flooding_ft3"] == 0))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cfg = dict(purpose="Synthetic unsteady numerical verification; not a thesis storm", seed=None,
        git_hash=None, manifest_hash=None, theta_hash=None, processes=1, budget_s=600,
        steps_s=[1,.5,.25], endpoints=["junction","storage"], amplitudes_ft=[.00005,.001],
        expected_runs=24, duration_s=600, warmup_s=60, surcharge="SLOT", max_trials=40,
        head_tolerance_ft=.0001, gate="fully open, no controls or flap gates", external_inflow=0,
        criteria=dict(max_final_head_flow_residual_cfs=.05, abs_routing_error_pct=1,
                      abs_system_balance_ft3="max(0.01, 1% gross link volume)", zero_flood=True),
        interpretation="Final-head constitutive consistency diagnostic, not an exact unsteady trajectory",
        versions={k:importlib.metadata.version(k) for k in ("numpy","pandas","pyswmm","swmm-toolkit")},
        python=platform.python_version(),
        engines={name:dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                 for name,p in (("baseline",args.baseline),("candidate",args.candidate))},
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__),Path("research/isolated_swmm_dll.py"),Path("research/weir_reproduction.py"))})
    (args.out/"run_config.json").write_text(json.dumps(cfg,indent=2))
    (args.out/"runner_source.py").write_bytes(Path(__file__).read_bytes())
    (args.out/"binding_source.py").write_bytes(Path("research/isolated_swmm_dll.py").read_bytes())
    started=time.monotonic()
    rows=[]
    for endpoint in cfg["endpoints"]:
        for amplitude in cfg["amplitudes_ft"]:
            for step in cfg["steps_s"]:
                case=f"{endpoint}_{amplitude:g}_{step:g}"
                content=reversing_model(step,endpoint,amplitude)
                for engine,dll in (("baseline",args.baseline),("candidate",args.candidate)):
                    root=args.out/engine
                    root.mkdir(exist_ok=True)
                    path=root/(case+".inp")
                    path.write_text(content)
                    samples,final=run_model(dll,path,started)
                    data=pd.DataFrame(samples,columns=["seconds","storage_head_ft","outfall_head_ft","flow_cfs","volume_ft3"])
                    data.to_csv(root/(case+".csv.gz"),index=False,compression="gzip")
                    row=dict(case=case,engine=engine,endpoint=endpoint,amplitude_ft=amplitude,step=step,
                             input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                             **summarize(data,final,amplitude),**final)
                    rows.append(row)
                    pd.DataFrame(rows).to_csv(args.out/"results.csv",index=False)
    summary=dict(complete=len(rows)==24,production_adoption=False,
                 passed={name:sum(r["verified"] for r in rows if r["engine"]==name)
                         for name in ("baseline","candidate")}, wall_seconds=time.monotonic()-started)
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

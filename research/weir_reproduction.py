"""Isolated hydraulic verification, NOT a rainfall scenario or controller trial.

One storage, one transverse weir, fixed tailwater and constant inflow. Exact
equilibrium from the same discharge formula provides an independent reference.
No production model or rainfall file is edited or loaded.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import time

import numpy as np
import pandas as pd
from pyswmm import Simulation, Nodes, Links, SystemStats

CREST = 609.272
TAIL = 616.56779
INVERT = 582.792
AREA = 24231.285
INFLOW = 65.0
DURATION = 600


def discharge(head, tail=TAIL):
    """Forward transverse weir flow, below crown, with outfall flap gate."""
    if head <= max(CREST, tail):
        return 0.0
    h = head-CREST
    submergence = max(0.0, tail-CREST)/h
    return 285*h**1.5 * (1-submergence**1.5)**.385


def equilibrium(tail=TAIL, inflow=INFLOW):
    low, high = max(CREST, tail), CREST+9.99
    if not 0 < inflow < discharge(high, tail):
        raise ValueError("Equilibrium must be inside the below-crown forward-flow branch")
    for _ in range(80):
        mid = (low+high)/2
        if discharge(mid, tail) < inflow:
            low = mid
        else:
            high = mid
    return (low+high)/2


def model_text(step, method, trials, tolerance, tail):
    head = equilibrium(tail)
    return f"""[TITLE]
Synthetic isolated weir verification - not a Detroit rainfall experiment
[OPTIONS]
FLOW_UNITS CFS
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2020
START_TIME 00:00:00
REPORT_START_DATE 01/01/2020
REPORT_START_TIME 00:00:00
END_DATE 01/01/2020
END_TIME 00:10:00
ROUTING_STEP {step:g}
VARIABLE_STEP 0
MINIMUM_STEP {step:g}
REPORT_STEP 00:00:01
SURCHARGE_METHOD {method}
MAX_TRIALS {trials}
HEAD_TOLERANCE {tolerance:.10f}
ALLOW_PONDING NO
LINK_OFFSETS DEPTH
[STORAGE]
S {INVERT} 46.5 {head-INVERT:.12f} FUNCTIONAL 0 0 {AREA} 0 0
[OUTFALLS]
O 602.797 FIXED {tail} YES
[WEIRS]
W S O TRANSVERSE 26.48 3 NO 0 0 YES
[XSECTIONS]
W RECT_OPEN 10 95 0 0
[INFLOWS]
S FLOW "" FLOW 1 1 {INFLOW}
[REPORT]
INPUT NO
CONTROLS NO
NODES ALL
LINKS ALL
"""


def run_case(root, step, method, profile, tail, started, dll=None):
    trials, tolerance = {"tight": (40, .0001), "extra_tight": (100, 1e-7)}[profile]
    name = f"{'submerged' if tail > CREST else 'free'}_{method}_{profile}_{step:g}"
    path = root / (name+".inp")
    path.write_text(model_text(step, method, trials, tolerance, tail))
    samples, final = (run_installed(path, started) if dll is None else
                      __import__("research.isolated_swmm_dll", fromlist=["run_model"]).run_model(dll, path, started))
    return summarize_case(root, name, path, samples, final, step, method, profile, tail)


def run_installed(path, started):
    samples, final = [], {}
    with Simulation(str(path)) as sim:
        nodes, links = Nodes(sim), Links(sim)
        node, outlet, weir = nodes["S"], nodes["O"], links["W"]
        def ended():
            final["routing_error_pct"] = sim.flow_routing_error
            sim.report()
        sim.add_after_end(ended)
        sim.start()
        initial_volume = node.volume
        while True:
            days = sim._model.swmm_step()
            if days <= 0:
                break
            seconds = days*86400
            samples.append((seconds, node.head, outlet.head, weir.flow, node.volume))
            if time.monotonic()-started > 600:
                raise TimeoutError("Ten-minute isolated verification budget exhausted")
        stats = SystemStats(sim).routing_stats
        final.update(outflow_ft3=stats["outflow"], inflow_ft3=stats["external_inflow"],
                     flooding_ft3=stats["flooding"], initial_storage_ft3=initial_volume,
                     final_storage_ft3=node.volume)
    return samples, final


def summarize_case(root, name, path, samples, final, step, method, profile, tail):
    data = pd.DataFrame(samples, columns=["seconds", "storage_head_ft", "outfall_head_ft", "flow_cfs", "volume_ft3"])
    data.to_csv(root / (name+".csv.gz"), index=False, compression="gzip")
    late = data[data.seconds >= 300]
    expected = equilibrium(tail)
    report = path.with_suffix(".rpt").read_text()
    match = re.search(r"% of Steps Not Converging\s*:\s*([\d.]+)", report)
    if not match or late.empty:
        raise ValueError("Missing verification outputs")
    final.update(case=name, method=method, profile=profile, step=step, tail_ft=tail,
                 input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 equilibrium_head_ft=expected, expected_outflow_ft3=INFLOW*DURATION,
                 mean_late_flow_cfs=float(late.flow_cfs.mean()),
                 late_flow_range_cfs=float(late.flow_cfs.max()-late.flow_cfs.min()),
                 max_late_flow_error_cfs=float((late.flow_cfs-INFLOW).abs().max()),
                 max_late_head_error_ft=float((late.storage_head_ft-expected).abs().max()),
                 nonconverging_pct=float(match.group(1)))
    final["outflow_error_pct"] = 100*(final["outflow_ft3"]/(INFLOW*DURATION)-1)
    # Predeclared verification tolerances, not thesis performance gates.
    final["equilibrium_verified"] = bool(np.isfinite(list(final[k] for k in
        ("mean_late_flow_cfs", "late_flow_range_cfs", "outflow_error_pct", "routing_error_pct"))).all()
        and final["max_late_flow_error_cfs"] <= .65
        and abs(final["outflow_error_pct"]) <= 1
        and abs(final["routing_error_pct"]) <= 1
        and final["flooding_ft3"] == 0)
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--dll", type=Path, help="Explicit separate diagnostic engine; installed solver is untouched")
    args = parser.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=False)
    cfg = dict(purpose="Synthetic hydraulic unit verification, no rainfall and no research split",
               seed=None, git_hash=None, theta_hash=None, manifest_hash=None,
               processes=1, budget_s=600, duration_s=DURATION, inflow_cfs=INFLOW,
               storage_area_ft2=AREA, weir_width_ft=95, weir_coefficient=3,
               tailwaters_ft=[TAIL, 604.0], steps_s=[1, .5, .25], methods=["EXTRAN", "SLOT"],
               profiles={"tight":dict(max_trials=40, head_tolerance_ft=.0001),
                         "extra_tight":dict(max_trials=100, head_tolerance_ft=1e-7)},
               expected_runs=24, initial_state="analytical equilibrium",
               verification=dict(late_flow_max_relative_error=.01, volume_relative_error=.01,
                                 abs_routing_continuity_pct=1, flooding_ft3=0, late_start_s=300),
               versions={p:importlib.metadata.version(p) for p in ("pyswmm", "swmm-toolkit", "numpy", "pandas")},
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    cfg["engine"] = "installed" if args.dll is None else str(args.dll.resolve())
    cfg["dll_sha256"] = None if args.dll is None else hashlib.sha256(args.dll.read_bytes()).hexdigest()
    if args.dll is not None:
        helper = Path("research/isolated_swmm_dll.py")
        cfg["binding_sha256"] = hashlib.sha256(helper.read_bytes()).hexdigest()
        (root/"binding_source.py").write_bytes(helper.read_bytes())
    (root/"run_config.json").write_text(json.dumps(cfg, indent=2))
    (root/"runner_source.py").write_bytes(Path(__file__).read_bytes())
    rows = []
    started = time.monotonic()
    for tail in cfg["tailwaters_ft"]:
        for method in cfg["methods"]:
            for profile in cfg["profiles"]:
                for step in cfg["steps_s"]:
                    row = run_case(root, step, method, profile, tail, started, args.dll)
                    rows.append(row)
                    pd.DataFrame(rows).to_csv(root/"results.csv", index=False)
                    print(row["case"], f"range={row['late_flow_range_cfs']:.3f} CFS volume_error={row['outflow_error_pct']:.3f}% verified={row['equilibrium_verified']}", flush=True)
    (root/"summary.json").write_text(json.dumps(dict(complete=len(rows)==cfg["expected_runs"],
        verified=sum(r["equilibrium_verified"] for r in rows), runs=len(rows),
        wall_seconds=time.monotonic()-started), indent=2))


if __name__ == "__main__":
    main()

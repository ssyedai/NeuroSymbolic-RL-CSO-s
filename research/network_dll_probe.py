"""Bounded native-control TRAIN probe using an explicit separate SWMM DLL.

Build physical-rain inputs with the existing guarded environment, close it,
then run one DLL simulation at a time. Never install a diagnostic engine.
"""
import argparse
import csv
import ctypes as C
import gzip
import hashlib
import json
from pathlib import Path
import re
import time

import pandas as pd
from multistorm import adapters as A
from multistorm.complete_overflow import CSO_OUTFALLS, FT3_TO_M3
from multistorm.storms import load_storms
from research.fine_routing import FineRoutingEnv, summarize
from research.guard import assert_provenance
from research.isolated_swmm_dll import RoutingTotals


class NodeStats(C.Structure):
    # Exact layout from pinned toolkit_structs.h, including the aligned int.
    _fields_ = [(key, C.c_double) for key in (
        "avgDepth", "maxDepth", "maxDepthDate", "maxRptDepth", "volFlooded", "timeFlooded",
        "timeSurcharged", "timeCourantCritical", "totLatFlow", "maxLatFlow", "maxInflow",
        "maxOverflow", "maxPondedVol")] + [("nonConvergedCount", C.c_int),
                                          ("maxInflowDate", C.c_double), ("maxOverflowDate", C.c_double)]


def run_native(dll, path, deadline, trace=False, stride_observer=None):
    lib = C.CDLL(str(dll.resolve()))
    signatures = {
        "swmm_open": [C.c_char_p]*3, "swmm_start": [C.c_int],
        "swmm_stride": [C.c_int, C.POINTER(C.c_double)], "swmm_end": [],
        "swmm_step": [C.POINTER(C.c_double)],
        "swmm_getNodeResult": [C.c_int, C.c_int, C.POINTER(C.c_double)],
        "swmm_getLinkResult": [C.c_int, C.c_int, C.POINTER(C.c_double)],
        "swmm_report": [], "swmm_close": [], "swmm_getCount": [C.c_int],
        "swmm_getIndex": [C.c_int, C.c_char_p],
        "swmm_getNodeType": [C.c_int, C.POINTER(C.c_int)],
        "swmm_getNodeTotalInflow": [C.c_int, C.POINTER(C.c_double)],
        "swmm_getNodeStats": [C.c_int, C.POINTER(NodeStats)],
        "swmm_getSystemRoutingTotals": [C.POINTER(RoutingTotals)],
        "swmm_getMassBalErr": [C.POINTER(C.c_float)]*3,
    }
    for name, types in signatures.items():
        getattr(lib, name).argtypes = types
        getattr(lib, name).restype = C.c_int
    def call(name, *args):
        code = getattr(lib, name)(*args)
        if code:
            raise RuntimeError(f"{name} error {code}; see {path.with_suffix('.rpt')}")
    opened = running = False
    stream = None
    try:
        call("swmm_open", *(str(p.resolve()).encode("ascii") for p in
                            (path, path.with_suffix(".rpt"), path.with_suffix(".out"))))
        opened = True
        call("swmm_start", 1)
        running = True
        elapsed = C.c_double()
        strides = 0
        if trace:
            node_names = ("1360", "35440", "35442", "35441", "3545", "65")
            link_names = ("1360_B", "1360", "35444", "W1", "PUMP29@35445-3565")
            nodes = {n:lib.swmm_getIndex(2, n.encode("ascii")) for n in node_names}
            links = {n:lib.swmm_getIndex(3, n.encode("ascii")) for n in link_names}
            if min(list(nodes.values())+list(links.values())) < 0:
                raise ValueError("Trace element missing")
            stream = gzip.open(path.with_suffix(".csv.gz"), "wt", newline="")
            writer = csv.writer(stream)
            writer.writerow(["seconds"]+[n+".head_ft" for n in nodes]+
                            [n+suffix for n in links for suffix in (".flow_cfs", ".setting", ".target")])
            def result(fn, index, field):
                value = C.c_double()
                call(fn, index, field, C.byref(value))
                return value.value
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("Native diagnostic budget exhausted")
            if trace:
                call("swmm_step", C.byref(elapsed))
            else:
                call("swmm_stride", 900, C.byref(elapsed))
            strides += 1
            if stride_observer is not None:
                if trace:
                    raise ValueError("Stride observer requires unchanged stride scheduling")
                stride_observer(lib, call, strides * 900)
            if elapsed.value <= 0:
                break
            seconds = elapsed.value*86400
            if trace and (57600 <= seconds <= 61200 or 81000 <= seconds <= 104400):
                writer.writerow([seconds]+[result("swmm_getNodeResult", n, 6) for n in nodes.values()]+
                                [result("swmm_getLinkResult", n, field) for n in links.values() for field in (0,5,6)])
        if not trace and strides != 288:
            raise ValueError(f"Expected 288 strides, got {strides}")
        outfalls = {}
        for name in CSO_OUTFALLS:
            idx = lib.swmm_getIndex(2, name.encode("ascii"))
            if idx < 0:
                raise ValueError("Missing confirmed CSO outfall")
            value = C.c_double()
            call("swmm_getNodeTotalInflow", idx, C.byref(value))
            outfalls[name] = value.value*FT3_TO_M3
        flood = 0.
        count = lib.swmm_getCount(2)
        if count <= 0:
            raise ValueError("No nodes found")
        for i in range(count):
            kind = C.c_int()
            call("swmm_getNodeType", i, C.byref(kind))
            if kind.value == 1:
                continue
            stats = NodeStats()
            call("swmm_getNodeStats", i, C.byref(stats))
            flood += stats.volFlooded*FT3_TO_M3
        totals = RoutingTotals()
        call("swmm_getSystemRoutingTotals", C.byref(totals))
        call("swmm_end")
        running = False
        runoff, routing, quality = C.c_float(), C.c_float(), C.c_float()
        call("swmm_getMassBalErr", C.byref(runoff), C.byref(routing), C.byref(quality))
        call("swmm_report")
        return dict(cso_total=sum(outfalls.values()), flood_total=flood,
                    total_overflow_vol_m3=sum(outfalls.values())+flood,
                    routing_error_pct=routing.value, runoff_error_pct=runoff.value,
                    system_flood_m3=totals.flooding*FT3_TO_M3,
                    simulated_steps=strides, stepping="direct" if trace else "900-second stride",
                    **{f"cso_{name}_m3":v for name,v in outfalls.items()})
    finally:
        if stream is not None:
            stream.close()
        try:
            if running:
                call("swmm_end")
        finally:
            if opened:
                call("swmm_close")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--trace", action="store_true", help="Direct routing-step trace; distinct scheduling diagnostic")
    parser.add_argument("--fixed-rule-second", action="store_true", help="Diagnostic only: evaluate native rules every second at all routing resolutions")
    parser.add_argument("--max-trials", type=int, choices=[40, 100, 200], default=40,
                        help="Bounded iteration-budget ablation; default preserves the established 40-trial profile")
    parser.add_argument("--routing-seconds", nargs="+", type=float, choices=[1,.5,.25], default=[1,.5,.25])
    args = parser.parse_args()
    root = args.out
    root.mkdir(parents=True, exist_ok=False)
    rain = Path("data/useful/rain_scenarios")
    sid = "USC00200230_20100719__T10"
    splits = json.loads((rain/"splits.json").read_text())
    if splits[sid] != "train":
        raise ValueError("Select TRAIN before reading rainfall")
    storms = load_storms(rain, "none", storm_ids=[sid])
    assert_provenance(storms, rain)
    cfg = json.loads(Path("runs/hydraulic_validation_20261011/slot_tight_convergence/run_config.json").read_text())
    cfg.update(purpose="Separate-engine native TRAIN convergence probe", storm_ids=[sid],
               selection="fixed previously failing third TRAIN parent", cases="native only",
               expected_runs=len(args.routing_seconds), routing_seconds=args.routing_seconds, budget_s=900, processes=1,
               engine_dll=str(args.dll.resolve()), dll_sha256=hashlib.sha256(args.dll.read_bytes()).hexdigest(),
               max_trials=args.max_trials,
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               rule_seconds=1 if args.fixed_rule_second else 0,
               stepping="swmm_step direct" if args.trace else "288 swmm_stride(900) calls; native gates and pumps",
               trace_windows_seconds=[[57600,61200],[81000,104400]] if args.trace else [])
    (root/"run_config.json").write_text(json.dumps(cfg, indent=2))
    (root/"runner_source.py").write_bytes(Path(__file__).read_bytes())
    old, _, kb = A.build_v8(0, complete_overflow=True)
    old.close()
    rows = []
    deadline = time.monotonic()+cfg["budget_s"]
    for dt in cfg["routing_seconds"]:
        path = root/f"native_{dt:g}.inp"
        env = FineRoutingEnv(kb, policy_dim=7, real_only=True, time_limit_truncation=True, native_pumps=True)
        env.physical_rain, env.surcharge_method, env.tight_solver = True, "SLOT", True
        env.routing_seconds = dt
        env.rule_seconds = 1 if args.fixed_rule_second else None
        env.max_trials = args.max_trials
        try:
            env.reset(options=dict(storm=storms[0], native=True, physical_rain=True, use_projection=False))
            model = Path(env.input_file).read_text()
            if not re.search(r"(?m)^FLOW_UNITS\s+CFS\s*$", model):
                raise ValueError("This diagnostic binding requires CFS/feet input units")
            path.write_bytes(Path(env.input_file).read_bytes())
        finally:
            env.close()
        began = time.monotonic()
        row = dict(storm_id=sid, split="train", case="native", routing_seconds=dt,
                   input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   **run_native(args.dll, path, deadline, args.trace))
        row["wall_seconds"] = time.monotonic()-began
        report = path.with_suffix(".rpt").read_text()
        row["nonconverging_pct"] = float(re.search(r"% of Steps Not Converging\s*:\s*([\d.]+)", report).group(1))
        rows.append(row)
        pd.DataFrame(rows).to_csv(root/"results.csv", index=False)
        summary = summarize(rows, cfg) if len(cfg["routing_seconds"]) >= 2 else dict(
            complete=True, passed=False, decision="Single-resolution trace cannot certify convergence")
        (root/"summary.json").write_text(json.dumps(summary, indent=2))
        print(f"dt={dt} CSO={row['cso_total']:.6f} flood={row['flood_total']:.6f} continuity={row['routing_error_pct']:.6f}% runtime={row['wall_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()

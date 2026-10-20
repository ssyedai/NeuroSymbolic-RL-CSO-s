"""Routing-step diagnostic around flood peaks on a preselected TRAIN parent.

Direct swmm_step replaces stride(900) here; this scheduling difference is
explicitly compared against previous stride results, never silently substituted.
"""
import csv
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

from pyswmm import SystemStats

from multistorm import adapters as A
from multistorm.complete_overflow import FT3_TO_M3, CSO_OUTFALLS
from multistorm.storms import load_storms
from research.fine_routing import FineRoutingEnv
from research.guard import assert_provenance

NODES = ("3528_A", "3529", "3529_A", "3530", "35390", "35391", "JCT-2114", "JCT-2112")
LINKS = ("35291", "35291_A", "35291_B", "3530", "3530_B", "Connection", "51698",
         "PUMP27@35395-3535", "PUMP28@35390-3535")
WINDOWS = ((16*3600, 17*3600), (22.5*3600, 29*3600))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runs/hydraulic_validation_20261011/routing_trace")
    parser.add_argument("--surcharge-method", choices=["EXTRAN", "SLOT"], default=None)
    parser.add_argument("--routing-seconds", nargs="+", type=float, choices=[1., .5, .25], default=[1., .5, .25])
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--tight-solver", action="store_true")
    parser.add_argument("--seven-mile", action="store_true")
    args = parser.parse_args()
    nodes = (("1360", "35441", "3545", "35440", "35442", "65", "JCT-3090")
             if args.seven_mile else NODES)
    links = (("1360", "1360_B", "Connection_2", "W1", "35444", "PUMP29@35445-3565")
             if args.seven_mile else LINKS)
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "run_config.json").exists():
        raise FileExistsError("Preserve previous trace")
    rain = Path("data/useful/rain_scenarios")
    sid = "USC00200230_20100719__T10"
    splits = json.loads((rain / "splits.json").read_text())
    if splits[sid] != "train":
        raise ValueError("TRAIN only")
    storm = load_storms(rain, "none", storm_ids=[sid])[0]
    assert_provenance([storm], rain)
    cfg = json.loads(Path("runs/hydraulic_validation_20261011/fine_routing_v2/run_config.json").read_text())
    cfg.update(storm_ids=[sid], selection="Fixed third TRAIN T10 parent from convergence study",
               purpose="Direct-routing-step hydraulic diagnosis with original pump rules",
               cases="native" if args.native else "static_half", native=args.native,
               max_trials=40 if args.tight_solver else 8, head_tolerance_ft=.0001 if args.tight_solver else .005,
               surcharge_method=args.surcharge_method or "original (EXTRAN default)",
               expected_runs=len(args.routing_seconds), routing_seconds=args.routing_seconds,
               stepping="swmm_step; no 900-second stride partition",
               trace_windows_seconds=WINDOWS, nodes=nodes, links=links, budget_s=1800,
               input_model_hash=hashlib.sha256(Path("7MPF_CSO_08.inp").read_bytes()).hexdigest(),
               code_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                            (__file__, "research/fine_routing.py", "multistorm/complete_overflow.py", "app.py")})
    (root / "run_config.json").write_text(json.dumps(cfg, indent=2))
    (root / "runner_source.py").write_bytes(Path(__file__).read_bytes())
    (root / "fine_routing_source.py").write_bytes(Path("research/fine_routing.py").read_bytes())
    old, _, kb = A.build_v8(0, complete_overflow=True)
    old.close()
    env = FineRoutingEnv(kb, policy_dim=7, real_only=True, time_limit_truncation=True, native_pumps=True)
    env.physical_rain = True
    env.surcharge_method = args.surcharge_method
    env.tight_solver = args.tight_solver
    results = []
    started = time.monotonic()
    try:
        for routing in cfg["routing_seconds"]:
            began = time.monotonic()
            env.routing_seconds = routing
            env.report_path = root / f"step_{routing:g}.rpt"
            env.reset(options=dict(storm=storm, native=args.native, physical_rain=True, use_projection=False))
            columns = ["seconds", "dt"]
            for n in nodes:
                columns += [f"{n}.{k}" for k in ("head_ft", "volume_ft3", "inflow_cfs", "outflow_cfs", "flood_cfs")]
            for link in links:
                columns += [f"{link}.{k}" for k in ("flow_cfs", "setting", "target")]
            elapsed = 0.
            steps = saved = 0
            duration = (env.sim.end_time-env.sim.start_time).total_seconds()
            with gzip.open(root / f"step_{routing:g}.csv.gz", "wt", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(columns)
                while True:
                    days = env.sim._model.swmm_step()
                    now = days*86400 if days > 0 else duration
                    dt = now-elapsed
                    if any(a <= now <= b for a,b in WINDOWS):
                        row = [now, dt]
                        for n in nodes:
                            node = env._node_obj[n]
                            row += [node.head, node.volume, node.total_inflow, node.total_outflow, node.flooding]
                        for name in links:
                            link = env._link_obj[name]
                            row += [link.flow, link.current_setting, link.target_setting]
                        writer.writerow(row)
                        saved += 1
                    elapsed = now
                    steps += 1
                    if steps % 10000 == 0 and time.monotonic()-started > cfg["budget_s"]:
                        raise TimeoutError("Trace budget exhausted")
                    if days <= 0:
                        break
            flooding = {n:float(env._node_obj[n].statistics["flooding_volume"])*FT3_TO_M3
                        for n in env.list_nodes if not env._node_obj[n].is_outfall()}
            cso = {n:float(env._node_obj[n].cumulative_inflow)*FT3_TO_M3 for n in CSO_OUTFALLS}
            stats = SystemStats(env.sim).routing_stats
            env.close()
            result = dict(routing_seconds=routing, elapsed_s=elapsed, routing_steps=steps, saved_steps=saved,
                          cso_total=sum(cso.values()), flood_total=sum(flooding.values()),
                          routing_error_pct=env._accounting["routing_error_pct"],
                          system_flood_m3=stats["flooding"]*FT3_TO_M3,
                          cso_by_outfall_m3=cso, node_flood_m3=flooding, wall_seconds=time.monotonic()-began)
            results.append(result)
            (root / "results.json").write_text(json.dumps(results, indent=2))
            print(f"dt={routing} CSO={result['cso_total']:.4f} flood={result['flood_total']:.4f} continuity={result['routing_error_pct']:.4f}% rows={saved} runtime={result['wall_seconds']:.1f}s", flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()

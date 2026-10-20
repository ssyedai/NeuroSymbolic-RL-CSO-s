"""Verify cumulative-volume semantics at each SWMM routing step, native only."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from pyswmm import Simulation, Nodes, SystemStats
from swmm.toolkit import solver

from multistorm.complete_overflow import FT3_TO_M3, CompleteOverflowEnv
from multistorm.physical_inp import write_physical_storm_inp
from multistorm.storms import load_storms
from research.guard import assert_provenance


def main():
    root = Path("runs/hydraulic_validation_20261011")
    root.mkdir(parents=True, exist_ok=True)
    rain = Path("data/useful/rain_scenarios")
    ids = ["USC00200230_20100719__T10"]
    storms = load_storms(rain, "none", storm_ids=ids)
    assert_provenance(storms, rain)
    config = dict(storm_ids=ids, split="train", physical_rain=True, real_only=True, scaling="none",
                  seed=0, processes=1, native=True, control="INP rules", git_hash=None, theta_hash=None,
                  engine=solver.swmm_version_info(),
                  manifest_hash=hashlib.sha256((rain / "data_manifest.json").read_bytes()).hexdigest(),
                  code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  source_commit="27dc6990cda8bce21f6c16ddae631b37e7510ffc",
                  versions={p:importlib.metadata.version(p) for p in ("pyswmm", "swmm-toolkit", "numpy")})
    (root / "run_config.json").write_text(json.dumps(config, indent=2))
    inp = write_physical_storm_inp(storms[0].depth)
    try:
        with Simulation(str(inp)) as sim:
            nodes = list(Nodes(sim))
            outlets = [n for n in nodes if n.is_outfall()]
            interior = [n for n in nodes if not n.is_outfall()]
            sim.start()
            duration = (sim.end_time - sim.start_time).total_seconds()
            def rates():
                # Mirrors node_getSystemOutflow; cumulative_inflow loses direction.
                out = []
                for n in outlets:
                    incoming, outgoing = n.total_inflow, n.total_outflow
                    out.append(-outgoing if outgoing > 0 else incoming)
                return np.asarray(out), sum(n.flooding for n in interior)
            prev_out, prev_flood = rates()
            positive = np.zeros(len(outlets)); reverse = positive.copy()
            flood_trap = flood_right = elapsed = 0.0
            count = 0
            while True:
                # Installed public PySWMM wrapper returns elapsed days, or zero at end.
                days = sim._model.swmm_step()
                now = days * 86400 if days > 0 else duration
                dt = now - elapsed
                out, flood = rates()
                positive += (np.maximum(prev_out, 0) + np.maximum(out, 0)) * 0.5 * dt
                reverse += (np.maximum(-prev_out, 0) + np.maximum(-out, 0)) * 0.5 * dt
                flood_trap += (prev_flood + flood) * 0.5 * dt
                flood_right += flood * dt
                prev_out, prev_flood, elapsed = out, flood, now
                count += 1
                if days <= 0:
                    break
            stats = SystemStats(sim).routing_stats
            cumulative = np.asarray([n.cumulative_inflow for n in outlets])
            node_flood = sum(n.statistics["flooding_volume"] for n in interior)
            result = dict(storm_id=ids[0], routing_steps=count, elapsed_s=elapsed,
                          system_outflow_m3=stats["outflow"]*FT3_TO_M3,
                          integrated_outward_m3=float(positive.sum()*FT3_TO_M3),
                          integrated_reverse_m3=float(reverse.sum()*FT3_TO_M3),
                          cumulative_outfall_inflow_m3=float(cumulative.sum()*FT3_TO_M3),
                          system_flood_m3=stats["flooding"]*FT3_TO_M3,
                          integrated_flood_trapezoid_m3=flood_trap*FT3_TO_M3,
                          integrated_flood_right_endpoint_m3=flood_right*FT3_TO_M3,
                          node_flood_statistics_m3=node_flood*FT3_TO_M3,
                          outlets={n.nodeid:dict(cumulative_inflow_m3=cumulative[i]*FT3_TO_M3,
                                     outward_m3=positive[i]*FT3_TO_M3, reverse_m3=reverse[i]*FT3_TO_M3)
                                   for i,n in enumerate(outlets)})
        (root / "accounting_check.json").write_text(json.dumps(result, indent=2))
        # Arithmetic cross-checks, not a relaxed hydraulic acceptance threshold.
        assert abs(result["integrated_outward_m3"]-result["system_outflow_m3"]) < 1e-6
        assert abs(result["cumulative_outfall_inflow_m3"]-result["integrated_outward_m3"]-result["integrated_reverse_m3"]) < 1e-6
        assert abs(result["integrated_flood_right_endpoint_m3"]-result["node_flood_statistics_m3"]) < 1e-6
        print(json.dumps(result, indent=2))
    finally:
        CompleteOverflowEnv._cleanup_owned(inp)


if __name__ == "__main__":
    main()

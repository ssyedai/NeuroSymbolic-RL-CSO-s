"""TRAIN-only native routing-step sensitivity; no tuning against held-out data."""
import hashlib
import json
from pathlib import Path
import re
import argparse

import numpy as np
import pandas as pd
from multistorm import adapters as A
from multistorm.complete_overflow import CompleteOverflowEnv
from multistorm.storms import load_storms
from research.guard import assert_provenance


class RoutingStepEnv(CompleteOverflowEnv):
    routing_seconds = 10

    def _init_sim(self):
        if self.physical_rain:
            path = Path(self.input_file).resolve()
            if path.parent != Path("runs/_physical_inp").resolve():
                raise ValueError("Refuse to edit a non-generated model")
            text, count = re.subn(r"(?m)^ROUTING_STEP\s+\S+", f"ROUTING_STEP 0:00:{self.routing_seconds:02d}", path.read_text())
            if count != 1:
                raise ValueError("ROUTING_STEP not found")
            path.write_text(text)
        super()._init_sim()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--controlled", action="store_true")
    parser.add_argument("--native-pumps", action="store_true")
    args = parser.parse_args()
    root = Path("runs/hydraulic_validation_20261011") / ("pump_interlocks" if args.native_pumps else "controlled_convergence" if args.controlled else "convergence")
    if args.native_pumps and not args.controlled:
        parser.error("--native-pumps requires --controlled")
    root.mkdir(parents=True, exist_ok=True)
    if (root / "results.csv").exists():
        raise FileExistsError("Preserve previous convergence evidence")
    cfg = json.loads(Path("runs/hydraulic_validation_20261011/owned_gates/gate_run_config.json").read_text())
    cfg.update(purpose="Native routing convergence; control/report intervals stay 900 s", routing_seconds=[10, 5, 2, 1],
               native=True, pumps="INP rules", use_projection=False,
               code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.controlled:
        cfg.update(purpose="Fixed-command convergence separates hydraulics from native rule timing",
                   native=False, pumps="ON", cases="all three parents static_half; first parent also 3530=0")
    if args.native_pumps:
        cfg.update(pumps="INP native", native_pumps=True, routing_seconds=[10, 1],
                   baseline_tag=cfg["baseline_tag"] + "|native_pumps",
                   storm_ids=cfg["storm_ids"][:1], cases="first train parent; static_half and 3530=0",
                   code_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                                ("app.py", "multistorm/complete_overflow.py")})
    (root / "run_config.json").write_text(json.dumps(cfg, indent=2))
    rain = Path("data/useful/rain_scenarios")
    storms = load_storms(rain, "none", storm_ids=cfg["storm_ids"])
    assert_provenance(storms, rain)
    old, _, kb = A.build_v8(0, complete_overflow=True)
    old.close()
    env = RoutingStepEnv(kb, policy_dim=7, real_only=True, time_limit_truncation=True, native_pumps=args.native_pumps)
    env.physical_rain = True
    rows = []
    try:
        for storm in storms:
            cases = ["static_half"] if args.controlled else ["native"]
            if args.controlled and storm is storms[0]:
                cases.append("3530_closed")
            for case in cases:
                for dt in cfg["routing_seconds"]:
                    env.routing_seconds = dt
                    env.reset(options=dict(storm=storm, native=not args.controlled, physical_rain=True, use_projection=False))
                    action = np.full(7, 0.5)
                    if case == "3530_closed":
                        action[5] = 0
                    done = False
                    while not done:
                        _, _, term, trunc, _ = env.step(action)
                        done = term or trunc
                    row = dict(storm_id=storm.storm_id, split="train", case=case, routing_seconds=dt,
                               **env.get_episode_log()["accounting_summary"])
                    rows.append(row)
                    pd.DataFrame(rows).to_csv(root / "results.csv", index=False)
                    print(storm.storm_id, case, dt, f"flood={row['flood_total']:.4f} CSO={row['cso_total']:.4f} continuity={row['routing_error_pct']:.4f}%", flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()

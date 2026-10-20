"""Bounded TRAIN-only convergence experiment, with native pump safeguards.

No result from this diagnostic changes the production simulation profile.
ROUTING_STEP accepts numeric seconds (SWMM 5.2.4 project.c ROUTE_STEP).
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np
import pandas as pd

from multistorm import adapters as A
from multistorm.complete_overflow import CompleteOverflowEnv
from multistorm.storms import load_storms
from research.guard import assert_provenance


def patch_options(text, seconds, rule_seconds=None, tight_solver=False, surcharge_method=None,
                  max_trials=None, head_tolerance=None):
    if not 0.001 <= seconds <= 1:
        raise ValueError("Diagnostic routing step must be 0.001..1 seconds")
    options = {"ROUTING_STEP": f"{seconds:g}", "MINIMUM_STEP": f"{min(0.5, seconds):g}"}
    if tight_solver:
        options.update(MAX_TRIALS="40", HEAD_TOLERANCE="0.0001")
    if max_trials is not None:
        if not isinstance(max_trials, int) or not 8 <= max_trials <= 200:
            raise ValueError("Diagnostic max_trials must be an integer in 8..200")
        options["MAX_TRIALS"] = str(max_trials)
    if head_tolerance is not None:
        if not 1e-9 <= head_tolerance <= 0.005:
            raise ValueError("Diagnostic head_tolerance must be 1e-9..0.005 ft")
        options["HEAD_TOLERANCE"] = f"{head_tolerance:.10f}"
    if rule_seconds is not None:
        if rule_seconds != 1:
            raise ValueError("Only the explicit 1-second rule-timing diagnostic is supported")
        options["RULE_STEP"] = "00:00:01"
    parts = re.split(r"(?m)^(\[[^\]\r\n]+\].*)$", text)
    sections = [i for i in range(1, len(parts), 2) if parts[i].strip().upper() == "[OPTIONS]"]
    if len(sections) != 1:
        raise ValueError("Expected exactly one OPTIONS section")
    i = sections[0] + 1
    if surcharge_method is not None:
        if surcharge_method not in {"EXTRAN", "SLOT"}:
            raise ValueError("Unsupported surcharge method")
        if not re.search(r"(?m)^SURCHARGE_METHOD\s", parts[i]):
            parts[i] += f"SURCHARGE_METHOD {surcharge_method}\n"
        else:
            options["SURCHARGE_METHOD"] = surcharge_method
    for key, value in options.items():
        parts[i], count = re.subn(rf"(?m)^({key}\s+)\S+", rf"\g<1>{value}", parts[i])
        if count != 1:
            raise ValueError(f"Expected exactly one {key}")
    return "".join(parts)


class FineRoutingEnv(CompleteOverflowEnv):
    routing_seconds = 1.0
    rule_seconds = None
    tight_solver = False
    report_path = None
    surcharge_method = None
    max_trials = None
    head_tolerance = None

    def _finalize_accounting(self):
        super()._finalize_accounting()
        if self.report_path is not None:
            self.sim.report()

    def _cleanup_owned(self, path):
        path = Path(path).resolve()
        report = path.with_suffix(".rpt")
        if (self.report_path is not None and path.parent == Path("runs/_physical_inp").resolve()
                and report.exists()):
            self.report_path.write_bytes(report.read_bytes())
        CompleteOverflowEnv._cleanup_owned(path)

    def _init_sim(self):
        if not self.physical_rain:
            # Base constructor opens the original model before reset injects rain.
            return super()._init_sim()
        path = Path(self.input_file).resolve()
        if path.parent != Path("runs/_physical_inp").resolve():
            raise ValueError("Refuse to edit a non-generated model")
        path.write_text(patch_options(path.read_text(), self.routing_seconds, self.rule_seconds,
                                     self.tight_solver, self.surcharge_method,
                                     self.max_trials, self.head_tolerance))
        super()._init_sim()


def summarize(rows, cfg):
    comparisons = []
    df = pd.DataFrame(rows)
    if not len(df):
        return {"complete": False, "passed": False, "comparisons": []}
    if df.duplicated(["storm_id", "case", "routing_seconds"]).any():
        raise ValueError("Duplicate convergence run; cannot certify completeness")
    complete_groups = True
    for (storm, case), group in df.groupby(["storm_id", "case"]):
        group = group.set_index("routing_seconds")
        complete_groups = complete_groups and set(group.index) == set(cfg["routing_seconds"])
        for coarse, fine in zip(cfg["routing_seconds"][:-1], cfg["routing_seconds"][1:]):
            if coarse not in group.index or fine not in group.index:
                continue
            a, b = group.loc[coarse], group.loc[fine]
            delta = {k: abs(float(a[k]) - float(b[k])) for k in
                     ("cso_total", "flood_total", "total_overflow_vol_m3")}
            finite = np.isfinite([float(row[k]) for row in (a, b) for k in
                                 ("cso_total", "flood_total", "total_overflow_vol_m3", "routing_error_pct")]).all()
            passes = (finite and delta["flood_total"] <= 1.0 and
                      all(delta[k] <= max(1.0, 0.01 * abs(float(b[k]))) for k in
                          ("cso_total", "total_overflow_vol_m3")) and
                      max(abs(a.routing_error_pct), abs(b.routing_error_pct)) <= 1.0)
            comparisons.append(dict(storm_id=storm, case=case, coarse=coarse, fine=fine,
                                    absolute_deltas_m3=delta, passed=bool(passes)))
    complete = len(rows) == cfg["expected_runs"] and complete_groups
    # Require BOTH adjacent refinements for every case; do not select favorable rows.
    return dict(complete=complete, passed=complete and all(c["passed"] for c in comparisons),
                comparisons=comparisons,
                decision="Diagnostic only; a limited TRAIN sample cannot certify full G0-G3")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="runs/hydraulic_validation_20261011/fine_routing")
    parser.add_argument("--fixed-rule-second", action="store_true",
                        help="Changed-controller timing diagnostic, NOT original native reference")
    parser.add_argument("--tight-solver", action="store_true",
                        help="40 iterations and 0.0001 ft head tolerance; preserve rule cadence")
    parser.add_argument("--max-trials", type=int)
    parser.add_argument("--head-tolerance", type=float)
    parser.add_argument("--native-probe", action="store_true",
                        help="Three routing resolutions on the third TRAIN parent, native only")
    parser.add_argument("--timing-probe", action="store_true",
                        help="Six-run probe: first parent native, third parent static_half")
    parser.add_argument("--surcharge-method", choices=["EXTRAN", "SLOT"], default=None,
                        help="Explicit experimental hydraulic formulation; original model remains intact")
    args = parser.parse_args()
    if args.native_probe and args.timing_probe:
        parser.error("Choose only one probe")
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "run_config.json").exists():
        raise FileExistsError("Use a fresh output directory; preserve prior evidence")
    cfg = json.loads(Path("runs/hydraulic_validation_20261011/owned_gates/gate_run_config.json").read_text())
    cfg.update(purpose="Fine hydraulic convergence with original native pump interlocks",
               routing_seconds=[1.0, 0.5, 0.25], minimum_step="min(0.5, routing_seconds)",
               rule_seconds=1 if args.fixed_rule_second else 0,
               native_reference_unchanged_rules=not args.fixed_rule_second,
               max_trials=40 if args.tight_solver else 8,
               surcharge_method=args.surcharge_method or "original (EXTRAN default)",
               head_tolerance_ft=0.0001 if args.tight_solver else 0.005,
               pumps="INP native", native_pumps=True, budget_s=1800, expected_runs=21,
               cases="native and static_half on three train parents; 3530_closed on first parent",
               convergence_criteria=dict(flood_absolute_m3=1.0, cso_and_total_absolute_m3=1.0,
                                         cso_and_total_relative=0.01, continuity_absolute_pct=1.0,
                                         require_both_adjacent_refinements=True),
               baseline_tag=cfg["baseline_tag"] + "|native_pumps|fine_diagnostic",
               code_hashes={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                            (__file__, "app.py", "multistorm/complete_overflow.py")})
    cfg["input_model_hash"] = hashlib.sha256(Path("7MPF_CSO_08.inp").read_bytes()).hexdigest()
    if args.max_trials is not None:
        cfg["max_trials"] = args.max_trials
    if args.head_tolerance is not None:
        cfg["head_tolerance_ft"] = args.head_tolerance
    # Validate numerical overrides before allocating a simulation or writing a run.
    patch_options(Path("7MPF_CSO_08.inp").read_text(), 1, max_trials=args.max_trials,
                  head_tolerance=args.head_tolerance)
    if args.native_probe:
        cfg.update(expected_runs=3, storm_ids=[cfg["storm_ids"][2]],
                   cases="third TRAIN parent native only", selection="fixed failing TRAIN case")
    if args.timing_probe:
        if not args.fixed_rule_second:
            parser.error("--timing-probe requires --fixed-rule-second")
        cfg.update(expected_runs=6, storm_ids=[cfg["storm_ids"][0], cfg["storm_ids"][2]],
                   cases="first parent native; third parent static_half", selection="fixed timing probe TRAIN cases")
    (root / "run_config.json").write_text(json.dumps(cfg, indent=2))
    (root / "runner_source.py").write_bytes(Path(__file__).read_bytes())
    rain = Path("data/useful/rain_scenarios")
    split_map = json.loads((rain / "splits.json").read_text())
    if any(split_map.get(sid) != "train" for sid in cfg["storm_ids"]):
        raise ValueError("Diagnostic must select TRAIN only, before opening rainfall")
    storms = load_storms(rain, "none", storm_ids=cfg["storm_ids"])
    assert_provenance(storms, rain)
    old, _, kb = A.build_v8(0, complete_overflow=True)
    old.close()
    env = FineRoutingEnv(kb, policy_dim=7, real_only=True, time_limit_truncation=True, native_pumps=True)
    env.physical_rain = True
    env.rule_seconds = 1 if args.fixed_rule_second else None
    env.tight_solver = args.tight_solver
    env.surcharge_method = args.surcharge_method
    env.max_trials = args.max_trials
    env.head_tolerance = args.head_tolerance
    rows = []
    start = time.monotonic()
    try:
        for index, storm in enumerate(storms):
            cases = (["native"] if index == 0 else ["static_half"]) if args.timing_probe else (
                ["native", "static_half"] + (["3530_closed"] if index == 0 else []))
            if args.native_probe:
                cases = ["native"]
            for case in cases:
                for dt in cfg["routing_seconds"]:
                    if time.monotonic() - start >= cfg["budget_s"]:
                        raise TimeoutError("Bounded diagnostic budget exhausted")
                    began = time.monotonic()
                    env.routing_seconds = dt
                    env.report_path = root / f"{storm.storm_id}_{case}_{dt:g}.rpt"
                    env.reset(options=dict(storm=storm, native=case == "native", physical_rain=True,
                                           use_projection=False))
                    action = np.full(7, 0.5)
                    if case == "3530_closed":
                        action[5] = 0
                    done = False
                    while not done:
                        if time.monotonic() - start >= cfg["budget_s"]:
                            raise TimeoutError("Bounded diagnostic budget exhausted")
                        _, _, term, trunc, _ = env.step(action)
                        done = term or trunc
                    log = env.get_episode_log()
                    row = dict(storm_id=storm.storm_id, split="train", case=case,
                               routing_seconds=dt, wall_seconds=time.monotonic()-began,
                               **log["accounting_summary"])
                    rows.append(row)
                    pd.DataFrame(rows).to_csv(root / "results.csv", index=False)
                    (root / "summary.json").write_text(json.dumps(summarize(rows, cfg), indent=2))
                    np.savez_compressed(root / f"{storm.storm_id}_{case}_{dt:g}.npz",
                                        actions_actual=log["actions_actual"], actions_target=log["actions_target"],
                                        flooding=log["flooding"], cso_flow=log["cso_flow"])
                    (root / f"{storm.storm_id}_{case}_{dt:g}_nodes.json").write_text(json.dumps(dict(
                        node_flood_volumes_m3=log["node_flood_volumes_m3"],
                        node_peak_depth_ft=log["node_peak_depth_ft"]), indent=2))
                    print(storm.storm_id, case, dt, f"flood={row['flood_total']:.4f} CSO={row['cso_total']:.4f} continuity={row['routing_error_pct']:.4f}% seconds={row['wall_seconds']:.1f}", flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()

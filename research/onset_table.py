"""Compute k_onset per real event with TRUE native control. Needs the project env (pyswmm). ~8 s per simulation."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from research.build_scaled_storms import load_parents
from research.onset import find_onset_factor
from research.readiness import experiment_status, isolated_output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", required=True); ap.add_argument("--events", required=True)
    ap.add_argument("--min-year", type=int, default=2010); ap.add_argument("--out", default="runs/onset_table.csv")
    ap.add_argument("--floor", type=float, default=1.0); ap.add_argument("--max-parents", type=int, default=0)
    ap.add_argument("--exploratory", action="store_true")
    a = ap.parse_args()
    status = experiment_status(a.exploratory)
    out = isolated_output(a.out, a.exploratory, "runs/onset_table.csv")
    from multistorm import adapters as A                    # project modules (import here so tests need no pyswmm)
    from multistorm.storms import Storm
    env, agent, kb = A.build_v8(0, complete_overflow=True, native_pumps=True)
    native = A.native_fn(env)                               # storm -> summary dict with 'cso_total'  [VERIFY signature]
    parents = load_parents(a.rain_dir, a.events, a.min_year)
    n_source_parents = len(parents)
    if a.max_parents:
        parents = parents[: a.max_parents]
    rows = []
    for p in parents:
        def run_cso(depth, pid=p["storm_id"]):
            st = Storm(pid, "onset", np.asarray(depth) * 4.0, np.asarray(depth), "train", {"scaling": "none"})
            return native(st)["cso_total"]
        ko, ev = find_onset_factor(run_cso, p["depth"], floor=a.floor)
        rows.append(dict(storm_id=p["storm_id"], year=p["year"], k_onset=ko if ko is not None else np.nan,
                         n_runs=len(ev), cso_at_k1=ev.get(1.0, np.nan),
                         volume_units="m3", complete_four_outfall_objective=True,
                         research_status=status["research_status"],
                         hydraulic_gate_passed=status["hydraulic_gate_passed"]))
        pd.DataFrame(rows).to_csv(out, index=False)       # incremental save
    df = pd.DataFrame(rows)
    print(df.k_onset.describe()); print("no onset within cap:", int(df.k_onset.isna().sum()), "of", len(df))
    median = float(df.k_onset.median()) if df.k_onset.notna().any() else float("nan")
    fraction = float(df.k_onset.isna().mean()) if len(df) else 1.0
    passed = bool(len(df) == n_source_parents and np.isfinite(median)
                  and median <= 4.0 and fraction < 0.30)
    summary = dict(
        n_storms=len(df), n_expected_parents=n_source_parents,
        complete_table=bool(len(df) == n_source_parents),
        median_k_onset=median, frac_no_onset=fraction, n_errors=0,
        volume_units="m3", complete_four_outfall_objective=True,
        research_status=status["research_status"],
        hydraulic_gate_passed=status["hydraulic_gate_passed"],
        G1_pass=passed,
    )
    Path(str(out) + ".summary.json").write_text(json.dumps(summary, indent=1))
    print("PLAUSIBILITY GATE:", {"median_k_onset": median,
                                  "frac_no_onset": fraction, "G1_pass": passed})
    env.close()
    if not passed:
        raise RuntimeError("G1 failed; stop before scenario rebuilding")


if __name__ == "__main__":
    main()

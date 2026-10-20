"""Compute k_onset per real event with TRUE native control. Needs the project env (pyswmm). ~8 s per simulation."""
from __future__ import annotations
import argparse
import numpy as np
import pandas as pd
from research.build_scaled_storms import load_parents
from research.onset import find_onset_factor
from research.readiness import assert_hydraulic_training_ready


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", required=True); ap.add_argument("--events", required=True)
    ap.add_argument("--min-year", type=int, default=2010); ap.add_argument("--out", default="runs/onset_table.csv")
    ap.add_argument("--floor", type=float, default=1.0); ap.add_argument("--max-parents", type=int, default=0)
    a = ap.parse_args()
    assert_hydraulic_training_ready()
    from multistorm import adapters as A                    # project modules (import here so tests need no pyswmm)
    from multistorm.storms import Storm
    env, agent, kb = A.build_v8(0, complete_overflow=True, native_pumps=True)
    native = A.native_fn(env)                               # storm -> summary dict with 'cso_total'  [VERIFY signature]
    parents = load_parents(a.rain_dir, a.events, a.min_year)
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
                         volume_units="m3", complete_four_outfall_objective=True))
        pd.DataFrame(rows).to_csv(a.out, index=False)       # incremental save
    df = pd.DataFrame(rows)
    print(df.k_onset.describe()); print("no onset within cap:", int(df.k_onset.isna().sum()), "of", len(df))
    median = float(df.k_onset.median()) if df.k_onset.notna().any() else float("nan")
    fraction = float(df.k_onset.isna().mean()) if len(df) else 1.0
    passed = bool(np.isfinite(median) and median <= 4.0 and fraction < 0.30)
    print("PLAUSIBILITY GATE:", {"median_k_onset": median,
                                  "frac_no_onset": fraction, "G1_pass": passed})
    env.close()
    if not passed:
        raise RuntimeError("G1 failed; stop before scenario rebuilding")


if __name__ == "__main__":
    main()

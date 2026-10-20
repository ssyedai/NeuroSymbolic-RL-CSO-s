"""T09 — Controllability screen on train+val storms (never test). Writes runs/controllability.csv."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.controllability import cma_search, static_search
from research.guard import assert_provenance, assert_v8_scenario_manifest
from research.readiness import experiment_status, isolated_output


def _balanced_cap(storms, limit):
    """Deterministically spread a diagnostic cap across severity rungs."""
    if not limit or len(storms) <= limit:
        return list(storms)
    groups = {}
    for storm in sorted(storms, key=lambda s: s.storm_id):
        key = str((storm.meta or {}).get("rung", "unknown"))
        groups.setdefault(key, []).append(storm)
    chosen = []
    while len(chosen) < limit and groups:
        for key in sorted(list(groups)):
            if groups[key] and len(chosen) < limit:
                chosen.append(groups[key].pop(0))
            if not groups[key]:
                del groups[key]
    return chosen


def make_evaluate_fn(env, bstore):
    from multistorm.metrics import episode_summary

    def evaluate_fn(policy, storm, use_projection):
        policy.reset()
        rec = bstore.get(storm)
        prev = env.use_projection
        env.use_projection = bool(use_projection)
        obs, _ = env.reset(options=dict(
            storm=storm, physical_rain=True,
            baseline_flooding=rec["baseline_flooding"],
            reference_cso=(rec.get("native") or {}).get("cso_total", 1.0),
            use_projection=bool(use_projection),
        ))
        done = False
        while not done:
            a = policy.select_action(obs, deterministic=True)
            obs, _, term, trunc, _ = env.step(a)
            done = bool(term or trunc)
        env.use_projection = prev
        return episode_summary(env.get_episode_log(), rec["baseline_flooding"])

    return evaluate_fn


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", required=True)
    ap.add_argument("--split-manifest", default=None)
    ap.add_argument("--out", default="runs/controllability.csv")
    ap.add_argument("--cache", default="runs/baseline_cache.json")
    ap.add_argument("--max-storms", type=int, default=0)
    ap.add_argument("--static-n", type=int, default=64)
    ap.add_argument("--cma-iters", type=int, default=25)
    ap.add_argument("--cma-pop", type=int, default=12)
    ap.add_argument("--skip-cma", action="store_true")
    ap.add_argument("--exploratory", action="store_true")
    a = ap.parse_args(argv)
    status = experiment_status(a.exploratory)
    out = isolated_output(a.out, a.exploratory, "runs/controllability.csv")
    cache = isolated_output(a.cache, a.exploratory, "runs/baseline_cache.json")
    full_budget = bool(not a.max_storms and a.static_n == 64
                       and a.cma_iters == 25 and a.cma_pop == 12
                       and not a.skip_cma)
    run_config = dict(
        research_status=status["research_status"], rain_dir=str(Path(a.rain_dir)),
        split_manifest=str(Path(a.split_manifest) if a.split_manifest else
                           Path(a.rain_dir) / "splits.json"),
        max_storms=a.max_storms, static_n=a.static_n,
        cma_iters=a.cma_iters, cma_pop=a.cma_pop,
        skip_cma=bool(a.skip_cma), full_protocol_budget=full_budget,
    )
    run_config_path = Path(str(out) + ".run_config.json")
    if out.exists():
        if not run_config_path.exists():
            raise RuntimeError("Existing controllability output has no search-budget record")
        if json.loads(run_config_path.read_text()) != run_config:
            raise RuntimeError(
                "Existing controllability output used a different search budget or catalog")
    else:
        run_config_path.write_text(json.dumps(run_config, indent=1))

    from multistorm import adapters as A
    from multistorm.baselines import BaselineStore
    from multistorm.complete_overflow import COMPLETE_BASELINE_TAG, EXPLORATORY_BASELINE_TAG
    from multistorm.storms import assign_splits, load_storms

    split_path = Path(a.split_manifest or Path(a.rain_dir) / "splits.json")
    split_map = json.loads(split_path.read_text())
    selected = [sid for sid, split in split_map.items() if split in ("train", "val")]
    storms = load_storms(a.rain_dir, scaling="none", storm_ids=selected)
    storms, _ = assign_splits(storms, manifest_path=a.split_manifest or
                              str(Path(a.rain_dir) / "splits.json"))
    assert_provenance(storms, a.rain_dir)
    assert_v8_scenario_manifest(a.rain_dir, allow_exploratory=a.exploratory)
    pool = [s for s in storms if s.split in ("train", "val")]
    if a.max_storms:
        pool = _balanced_cap(pool, a.max_storms)

    env, _, _ = A.build_v8(0, complete_overflow=True, native_pumps=True,
                           input_file="7MPF_CSO_08.inp")
    bstore = BaselineStore(cache, "7MPF_CSO_08.inp",
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
                           tag=(EXPLORATORY_BASELINE_TAG if a.exploratory
                                else COMPLETE_BASELINE_TAG))
    evaluate_fn = make_evaluate_fn(env, bstore)

    rows = []
    if out.exists():
        prev = pd.read_csv(out)
        required = {"safety_first", "complete_four_outfall_objective", "hind_feasible"}
        if not required <= set(prev.columns):
            raise RuntimeError("Existing controllability output uses an obsolete objective")
        if not prev.get("research_status", pd.Series(index=prev.index, dtype=object)).eq(
                status["research_status"]).all():
            raise RuntimeError("Existing controllability output has a different research status")
        done = set(prev["storm_id"])
        rows = prev.to_dict("records")
        pool = [s for s in pool if s.storm_id not in done]

    for st in pool:
        rec = bstore.get(st)
        ref = rec.get("native") or rec["static"]
        ref_cso = float(ref["cso_total"])
        ref_flood = float(ref["flood_total"])
        c_stat, x_stat, s_stat = static_search(
            evaluate_fn, st, ref, n=a.static_n, use_projection=False, safety_first=True)
        best_hind_cso = float(s_stat["cso_total"])
        best_flood = float(s_stat["flood_total"])
        best_params = x_stat
        best_summary = s_stat
        if (not a.skip_cma) and ref_cso > 0 and best_hind_cso <= 1.05 * ref_cso:
            _, x_cma, s_cma = cma_search(
                evaluate_fn, st, ref, n_seg=4, iters=a.cma_iters, pop=a.cma_pop,
                x0=np.tile(x_stat, 4), use_projection=False, safety_first=True)
            from research.controllability import safety_objective
            if safety_objective(s_cma, ref) < safety_objective(s_stat, ref):
                best_hind_cso = float(s_cma["cso_total"])
                best_flood = float(s_cma["flood_total"])
                best_params = x_cma
                best_summary = s_cma
        # also once with projection for diagnostics
        _, _, s_proj = static_search(
            evaluate_fn, st, ref, n=min(16, a.static_n), use_projection=True,
            safety_first=True)

        from research.controllability import safety_objective
        static_feasible = safety_objective(s_stat, ref) < 1.0
        hind_feasible = safety_objective(best_summary, ref) < 1.0
        ach_s = (100 * (ref_cso - float(s_stat["cso_total"])) / ref_cso
                 if ref_cso > 1 and static_feasible else -float("inf"))
        ach_h = (100 * (ref_cso - best_hind_cso) / ref_cso
                 if ref_cso > 1 and hind_feasible else -float("inf"))
        rows.append(dict(
            storm_id=st.storm_id, split=st.split,
            rung=(st.meta or {}).get("rung"),
            parent=(st.meta or {}).get("parent", st.storm_id),
            family=(st.meta or {}).get("family"),
            ref_cso=ref_cso, best_static_cso=float(s_stat["cso_total"]),
            best_hind_cso=best_hind_cso,
            achievable_pct_static=ach_s, achievable_pct_hind=ach_h,
            ref_flood=ref_flood, best_flood=best_flood,
            static_feasible=static_feasible, hind_feasible=hind_feasible,
            best_static_proj_cso=float(s_proj["cso_total"]),
            best_params_json=json.dumps(np.asarray(best_params).tolist()),
            safety_first=True, complete_four_outfall_objective=True,
            research_status=status["research_status"],
            hydraulic_gate_passed=status["hydraulic_gate_passed"],
            uncontrollable=bool(not np.isfinite(ach_h) or ach_h < 5.0),
        ))
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"{st.storm_id} rung={rows[-1]['rung']} ach_hind={ach_h:.1f}%", flush=True)

    df = pd.DataFrame(rows)
    if len(df) and "rung" in df:
        medians = df.groupby("rung")["achievable_pct_hind"].median()
        print(medians.to_string())
        uncontrollable = medians[medians < 5.0].index.astype(str).tolist()
        gate_fail = medians[medians < 10.0].index.astype(str).tolist()
        summary = dict(
            n_storms=len(df), splits=sorted(df.split.unique().tolist()),
            median_achievable_pct_hind={str(k): float(v) for k, v in medians.items()},
            uncontrollable_rungs=uncontrollable, g2_failed_rungs=gate_fail,
            sample_threshold_pass=not gate_fail,
            g2_pass=bool(full_budget and not gate_fail), safety_first=True,
            diagnostic_budget=dict(max_storms=a.max_storms, static_n=a.static_n,
                                   cma_iters=a.cma_iters, cma_pop=a.cma_pop,
                                   skip_cma=bool(a.skip_cma)),
            full_protocol_budget=full_budget,
            research_status=status["research_status"],
            hydraulic_gate_passed=status["hydraulic_gate_passed"],
        )
        Path(str(out) + ".summary.json").write_text(json.dumps(summary, indent=1))
        if not full_budget and not a.exploratory:
            env.close()
            raise RuntimeError("Official G2 requires the complete search budget")
        if gate_fail and not a.exploratory:
            env.close()
            raise RuntimeError(f"G2 failed for rungs {gate_fail}; stop without training")
    env.close()


if __name__ == "__main__":
    main()

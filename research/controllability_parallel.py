"""Parallel, safety-first G2 controllability screen (one SWMM sim per process)."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import traceback

import numpy as np
import pandas as pd

from research.readiness import assert_hydraulic_training_ready


def _worker(payload: dict, queue: mp.Queue) -> None:
    try:
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        import torch
        torch.set_num_threads(1)

        from multistorm import adapters as A
        from multistorm.baselines import BaselineStore
        from multistorm.complete_overflow import COMPLETE_BASELINE_TAG
        from multistorm.metrics import episode_summary
        from multistorm.storms import Storm
        from research.controllability import cma_search, safety_objective, static_search

        storm = Storm(
            payload["storm_id"], payload["source"],
            np.asarray(payload["depth"], float) * 4.0,
            np.asarray(payload["depth"], float), payload["split"], payload["meta"])
        env, _, _ = A.build_v8(
            payload["seed"], complete_overflow=True, native_pumps=True,
            input_file=payload["inp"])
        cache_name = hashlib.sha256(storm.storm_id.encode()).hexdigest()[:16] + ".json"
        cache_path = Path(payload["cache_dir"]) / cache_name
        bstore = BaselineStore(
            cache_path, payload["inp"], A.calibrate_fn(env), A.static_fn(env),
            A.native_fn(env), tag=COMPLETE_BASELINE_TAG)

        def evaluate_fn(policy, st, use_projection):
            policy.reset()
            rec = bstore.get(st)
            previous = env.use_projection
            obs, _ = env.reset(options=dict(
                storm=st, physical_rain=True,
                baseline_flooding=rec["baseline_flooding"],
                reference_cso=rec["native"]["cso_total"],
                use_projection=bool(use_projection)))
            done = False
            while not done:
                action = policy.select_action(obs, deterministic=True)
                obs, _, terminated, truncated, _ = env.step(action)
                done = bool(terminated or truncated)
            summary = episode_summary(env.get_episode_log(), rec["baseline_flooding"])
            env.use_projection = previous
            return summary

        rec = bstore.get(storm)
        ref = rec["native"]
        ref_cso = float(ref["cso_total"])
        _, x_static, s_static = static_search(
            evaluate_fn, storm, ref, n=payload["static_n"], seed=payload["seed"],
            use_projection=False, safety_first=True)
        best_params, best = x_static, s_static
        if (not payload["skip_cma"] and ref_cso > 0
                and float(s_static["cso_total"]) <= 1.05 * ref_cso):
            _, x_cma, s_cma = cma_search(
                evaluate_fn, storm, ref, n_seg=4, iters=payload["cma_iters"],
                pop=payload["cma_pop"], seed=payload["seed"],
                x0=np.tile(x_static, 4), use_projection=False, safety_first=True)
            if safety_objective(s_cma, ref) < safety_objective(best, ref):
                best_params, best = x_cma, s_cma
        _, _, projected = static_search(
            evaluate_fn, storm, ref, n=min(16, payload["static_n"]),
            seed=payload["seed"], use_projection=True, safety_first=True)

        static_feasible = safety_objective(s_static, ref) < 1.0
        hind_feasible = safety_objective(best, ref) < 1.0
        achievable_static = (
            100.0 * (ref_cso - float(s_static["cso_total"])) / ref_cso
            if ref_cso > 1.0 and static_feasible else -float("inf"))
        achievable_hind = (
            100.0 * (ref_cso - float(best["cso_total"])) / ref_cso
            if ref_cso > 1.0 and hind_feasible else -float("inf"))
        env.close()
        queue.put(dict(
            storm_id=storm.storm_id, split=storm.split,
            rung=(storm.meta or {}).get("rung"),
            parent=(storm.meta or {}).get("parent", storm.storm_id),
            family=(storm.meta or {}).get("family"),
            ref_cso=ref_cso, best_static_cso=float(s_static["cso_total"]),
            best_hind_cso=float(best["cso_total"]),
            achievable_pct_static=achievable_static,
            achievable_pct_hind=achievable_hind,
            ref_flood=float(ref["flood_total"]), best_flood=float(best["flood_total"]),
            static_feasible=static_feasible, hind_feasible=hind_feasible,
            best_static_proj_cso=float(projected["cso_total"]),
            best_params_json=json.dumps(np.asarray(best_params).tolist()),
            uncontrollable=bool(not np.isfinite(achievable_hind) or achievable_hind < 5.0),
            safety_first=True, complete_four_outfall_objective=True,
        ))
    except Exception as exc:
        queue.put(dict(
            storm_id=payload.get("storm_id"), split=payload.get("split"),
            rung=(payload.get("meta") or {}).get("rung"),
            error=f"{exc}\n{traceback.format_exc()}", uncontrollable=True,
            safety_first=True, complete_four_outfall_objective=True))


def _run_one(payload: dict, timeout: int) -> dict:
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_worker, args=(payload, queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(15)
        return dict(storm_id=payload["storm_id"], split=payload["split"],
                    rung=(payload.get("meta") or {}).get("rung"),
                    error="timeout", uncontrollable=True,
                    safety_first=True, complete_four_outfall_objective=True)
    if queue.empty():
        return dict(storm_id=payload["storm_id"], split=payload["split"],
                    rung=(payload.get("meta") or {}).get("rung"),
                    error="no-result", uncontrollable=True,
                    safety_first=True, complete_four_outfall_objective=True)
    return queue.get()


def _sample_pool(storms, per_rung: int, seed: int):
    if not per_rung:
        return list(storms)
    rng = np.random.default_rng(seed)
    selected = []
    for _, group in sorted(pd.Series(storms).groupby(
            lambda i: str((storms[i].meta or {}).get("rung", "R")))):
        values = group.tolist()
        indices = rng.choice(len(values), size=min(per_rung, len(values)), replace=False)
        selected.extend(values[i] for i in indices)
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rain-dir", required=True)
    parser.add_argument("--split-manifest", default=None)
    parser.add_argument("--inp", default="7MPF_CSO_08.inp")
    parser.add_argument("--out", default="runs/controllability.csv")
    parser.add_argument("--cache-dir", default="runs/baseline_cache_ctrl")
    parser.add_argument("--per-rung", type=int, default=0,
                        help="Diagnostic sample only; official G2 requires 0")
    parser.add_argument("--static-n", type=int, default=64)
    parser.add_argument("--cma-iters", type=int, default=25)
    parser.add_argument("--cma-pop", type=int, default=12)
    parser.add_argument("--skip-cma", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    assert_hydraulic_training_ready()
    if args.per_rung and Path(args.out) == Path("runs/controllability.csv"):
        raise ValueError("Diagnostic samples require a non-official --out path")

    from multistorm.storms import assign_splits, load_storms
    from research.guard import assert_provenance, assert_v8_scenario_manifest
    split_path = Path(args.split_manifest or Path(args.rain_dir) / "splits.json")
    split_map = json.loads(split_path.read_text())
    selected_ids = [sid for sid, split in split_map.items() if split in ("train", "val")]
    storms = load_storms(args.rain_dir, "none", storm_ids=selected_ids)
    storms, _ = assign_splits(storms, manifest_path=str(split_path))
    assert_provenance(storms, args.rain_dir)
    assert_v8_scenario_manifest(args.rain_dir)
    full_pool = sorted(
        (storm for storm in storms if storm.split in ("train", "val")),
        key=lambda storm: storm.storm_id)
    pool = _sample_pool(full_pool, args.per_rung, args.seed)
    expected_rungs = sorted({str((s.meta or {}).get("rung", "R")) for s in pool})

    output = Path(args.out)
    rows, done = [], set()
    if output.exists():
        previous = pd.read_csv(output)
        required = {"safety_first", "complete_four_outfall_objective", "hind_feasible"}
        if not required <= set(previous.columns):
            raise RuntimeError("Existing controllability output uses an obsolete objective")
        rows = previous.to_dict("records")
        done = set(previous.storm_id.astype(str))
        pool = [storm for storm in pool if storm.storm_id not in done]

    payloads = [dict(
        storm_id=s.storm_id, source=s.source, split=s.split,
        depth=s.depth.tolist(), meta=dict(s.meta or {}), inp=args.inp,
        cache_dir=args.cache_dir, static_n=args.static_n,
        cma_iters=args.cma_iters, cma_pop=args.cma_pop,
        skip_cma=args.skip_cma, seed=args.seed,
    ) for s in pool]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run_one, p, args.timeout): p["storm_id"]
                   for p in payloads}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            pd.DataFrame(rows).to_csv(output, index=False)
            print(f"[{len(rows)}] {futures[future]} ach={row.get('achievable_pct_hind')}",
                  flush=True)

    frame = pd.DataFrame(rows)
    errors = frame["error"].notna() if "error" in frame else pd.Series(False, index=frame.index)
    scored = frame.loc[~errors].dropna(subset=["achievable_pct_hind"])
    medians = scored.groupby("rung")["achievable_pct_hind"].median()
    failed = [str(r) for r, value in medians.items()
              if not np.isfinite(value) or float(value) < 10.0]
    uncontrollable = [str(r) for r, value in medians.items()
                      if not np.isfinite(value) or float(value) < 5.0]
    missing = sorted(set(expected_rungs) - set(map(str, medians.index)))
    summary = dict(
        n=len(frame), n_expected=len(full_pool) if not args.per_rung else len(rows),
        n_scored=len(scored), n_errors=int(errors.sum()),
        median_achievable_pct_hind={str(k): float(v) for k, v in medians.items()},
        uncontrollable_rungs=uncontrollable, g2_failed_rungs=failed,
        missing_rungs=missing, diagnostic_sample=bool(args.per_rung),
        safety_first=True, complete_four_outfall_objective=True,
        g2_pass=bool(not args.per_rung and not failed and not missing
                     and not errors.any() and len(frame) == len(full_pool)),
    )
    Path(str(output) + ".summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    if not args.per_rung and not summary["g2_pass"]:
        raise RuntimeError("G2 failed; stop without training")


if __name__ == "__main__":
    main()

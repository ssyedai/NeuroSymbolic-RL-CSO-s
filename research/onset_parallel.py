"""Parallel k_onset table via spawn subprocesses (one SWMM Simulation per process)."""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from research.build_scaled_storms import load_parents
from research.readiness import experiment_status, isolated_output


def _worker(payload: dict, q: mp.Queue):
    env = None
    worker_inp = None
    try:
        import os
        import shutil
        import uuid
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        import torch
        torch.set_num_threads(1)
        from research.onset import find_onset_factor
        from multistorm import adapters as A
        from multistorm.storms import Storm

        # The environment opens an initial Simulation during construction.
        # Parallel workers therefore need separate INP/RPT/OUT basenames even
        # before per-storm physical-rain files are created.
        tmp = Path("runs/_physical_inp")
        tmp.mkdir(parents=True, exist_ok=True)
        worker_inp = tmp / f"onset_worker_{os.getpid()}_{uuid.uuid4().hex[:8]}.inp"
        shutil.copy2(payload["inp"], worker_inp)
        env, _, _ = A.build_v8(
            0, complete_overflow=True, native_pumps=True,
            input_file=str(worker_inp))
        native = A.native_fn(env)
        depth = np.asarray(payload["depth"], float)
        sid = payload["storm_id"]

        def run_cso(d):
            st = Storm(sid, "onset", np.asarray(d) * 4.0, np.asarray(d), "train",
                       {"scaling": "none"})
            return float(native(st)["cso_total"])

        ko, ev = find_onset_factor(run_cso, depth, floor=payload["floor"])
        q.put(dict(
            storm_id=sid, year=payload["year"],
            k_onset=ko if ko is not None else np.nan,
            n_runs=len(ev), cso_at_k1=ev.get(1.0, np.nan),
            volume_units="m3", complete_four_outfall_objective=True,
            research_status=payload["research_status"],
            hydraulic_gate_passed=payload["hydraulic_gate_passed"],
        ))
    except Exception as e:
        q.put(dict(
            storm_id=payload.get("storm_id"), year=payload.get("year"),
            k_onset=np.nan, n_runs=0, cso_at_k1=np.nan,
            error=f"{e}\n{traceback.format_exc()}",
        ))
    finally:
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
        try:
            from multistorm.physical_inp import DEFAULT_DST_DIR
            for f in DEFAULT_DST_DIR.glob(f"storm_{os.getpid()}_*"):
                f.unlink(missing_ok=True)
        except Exception:
            pass
        if worker_inp is not None:
            for suffix in (".inp", ".rpt", ".out"):
                worker_inp.with_suffix(suffix).unlink(missing_ok=True)


def _run_one(payload: dict, timeout: int = 600) -> dict:
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    p = ctx.Process(target=_worker, args=(payload, q))
    p.start()
    p.join(timeout=timeout)
    if p.is_alive():
        p.terminate()
        p.join(10)
        return dict(storm_id=payload["storm_id"], year=payload["year"],
                    k_onset=np.nan, n_runs=0, cso_at_k1=np.nan, error="timeout")
    if q.empty():
        return dict(storm_id=payload["storm_id"], year=payload["year"],
                    k_onset=np.nan, n_runs=0, cso_at_k1=np.nan, error="no-result")
    return q.get()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--min-year", type=int, default=2010)
    ap.add_argument("--inp", default="7MPF_CSO_08.inp")
    ap.add_argument("--out", default="runs/onset_table.csv")
    ap.add_argument("--floor", type=float, default=1.0)
    ap.add_argument("--max-parents", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--exploratory", action="store_true")
    a = ap.parse_args(argv)
    status = experiment_status(a.exploratory)

    parents = load_parents(a.rain_dir, a.events, a.min_year)
    n_source_parents = len(parents)
    if a.offset:
        parents = parents[a.offset:]
    if a.max_parents:
        parents = parents[: a.max_parents]
    payloads = [
        dict(storm_id=p["storm_id"], year=p["year"], depth=p["depth"].tolist(),
             floor=a.floor, inp=a.inp,
             research_status=status["research_status"],
             hydraulic_gate_passed=status["hydraulic_gate_passed"])
        for p in parents
    ]
    out = isolated_output(a.out, a.exploratory, "runs/onset_table.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if out.exists():
        prev = pd.read_csv(out)
        required = {"volume_units", "complete_four_outfall_objective"}
        if not required <= set(prev.columns):
            raise RuntimeError("Existing onset table uses an obsolete objective")
        if not prev.get("research_status", pd.Series(index=prev.index, dtype=object)).eq(
                status["research_status"]).all():
            raise RuntimeError("Existing onset table has a different research status")
        done = set(prev["storm_id"].astype(str))
        rows = prev.to_dict("records")
        payloads = [p for p in payloads if p["storm_id"] not in done]
        print(f"resume: {len(done)} done, {len(payloads)} remaining", flush=True)

    # Simple pool of spawn workers (queue of jobs)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(_run_one, p): p["storm_id"] for p in payloads}
        for fut in as_completed(futs):
            sid = futs[fut]
            row = fut.result()
            if row.get("error"):
                print(f"FAIL {sid}: {str(row['error'])[:200]}", flush=True)
            rows.append(row)
            pd.DataFrame(rows).to_csv(out, index=False)
            print(f"[{len(rows)}] {sid} k_onset={row.get('k_onset')}", flush=True)

    df = pd.DataFrame(rows)
    print(df.k_onset.describe())
    n_errors = int(df.get("error", pd.Series(index=df.index, dtype=object)).notna().sum())
    n_none = int(df.k_onset.isna().sum())
    print("no onset within cap:", n_none, "of", len(df))
    med = float(df.k_onset.median()) if df.k_onset.notna().any() else float("nan")
    frac_none = float(df.k_onset.isna().mean()) if len(df) else 1.0
    summary = {
        "n_storms": len(df), "n_expected_parents": n_source_parents,
        "complete_table": bool(len(df) == n_source_parents),
        "median_k_onset": med, "frac_no_onset": frac_none,
        "n_errors": n_errors, "volume_units": "m3",
        "complete_four_outfall_objective": True,
        "research_status": status["research_status"],
        "hydraulic_gate_passed": status["hydraulic_gate_passed"],
        "G1_pass": bool(len(df) == n_source_parents and not n_errors
                        and np.isfinite(med) and med <= 4 and frac_none < 0.30),
    }
    Path(str(out) + ".summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    if not summary["G1_pass"]:
        raise RuntimeError("G1 failed; stop before scenario rebuilding")


if __name__ == "__main__":
    main()

"""Deterministic post-freeze checkpoint evaluation in a fresh process."""
from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from .baselines import BaselineStore
from .config import MultiStormConfig
from .evaluate import evaluate
from .metrics_v8 import aggregate_native
from .storms import assign_splits, load_storms
from research.guard import assert_provenance, assert_v8_scenario_manifest
from research.readiness import experiment_status


def _protocol_commit(tag: str) -> str:
    try:
        commit = subprocess.check_output(
            ["git", "rev-list", "-n", "1", tag], text=True).strip()
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"Test evaluation requires frozen Git tag {tag!r} on the current history") from exc
    if not commit:
        raise RuntimeError(f"Protocol tag {tag!r} does not resolve to a commit")
    return commit


def _config(blob: dict) -> MultiStormConfig:
    names = {f.name for f in fields(MultiStormConfig)}
    return MultiStormConfig(**{k: v for k, v in blob.items() if k in names})


def _assert_repeatable(first: pd.DataFrame, second: pd.DataFrame) -> None:
    ignored = {"wall_s"}
    cols = [c for c in first.columns if c not in ignored]
    if cols != [c for c in second.columns if c not in ignored] or len(first) != len(second):
        raise RuntimeError("Repeated evaluation changed its schema or row count")
    for col in cols:
        a, b = first[col], second[col]
        if pd.api.types.is_numeric_dtype(a):
            if not np.allclose(a.to_numpy(float), b.to_numpy(float), equal_nan=True,
                               rtol=0.0, atol=1e-9):
                raise RuntimeError(f"Repeated evaluation is nondeterministic in column {col}")
        elif not a.fillna("<NA>").equals(b.fillna("<NA>")):
            raise RuntimeError(f"Repeated evaluation is nondeterministic in column {col}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--splits", default="val", help="Comma-separated: val,test")
    ap.add_argument("--protocol-tag", default="protocol-v1")
    ap.add_argument("--repeat-check", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--exploratory", action="store_true")
    args = ap.parse_args(argv)

    status = experiment_status(args.exploratory)
    run = Path(args.run)
    config_blob = json.loads((run / "run_config.json").read_text())
    if bool(config_blob.get("exploratory")) != bool(args.exploratory):
        raise RuntimeError("Run metadata and --exploratory do not match")
    cfg = _config(config_blob)
    wanted = {x.strip() for x in args.splits.split(",") if x.strip()}
    if not wanted or not wanted <= {"val", "test"}:
        raise ValueError("--splits must contain only val and/or test")
    protocol_commit = _protocol_commit(args.protocol_tag) if "test" in wanted else None

    split_path = Path(cfg.split_manifest or Path(cfg.rain_dir) / "splits.json")
    split_map = json.loads(split_path.read_text())
    selected = sorted(sid for sid, split in split_map.items() if split in wanted)
    storms = load_storms(cfg.rain_dir, "none", length_policy=cfg.length_policy,
                         storm_ids=selected)
    storms, _ = assign_splits(storms, cfg.split_seed, str(split_path),
                               cfg.val_frac, cfg.test_frac)
    assert_provenance(storms, cfg.rain_dir, cfg.data_manifest)
    assert_v8_scenario_manifest(
        cfg.rain_dir, cfg.data_manifest,
        allow_exploratory=args.exploratory)

    from . import adapters as A
    from .train_multi import _build_stack, seed_everything
    seed_everything(cfg.seed)
    env, agent, _ = _build_stack(cfg)
    checkpoint = Path(args.checkpoint or run / "checkpoints" / "best_val.pt")
    extra = A.load_checkpoint(agent, checkpoint)
    for name in ("variant", "manifest_hash", "theta_hash"):
        expected = config_blob.get(name)
        if name in extra and extra[name] != expected:
            env.close()
            raise RuntimeError(
                f"Checkpoint/config mismatch for {name}: {extra[name]!r} != {expected!r}")

    from .complete_overflow import COMPLETE_BASELINE_TAG, EXPLORATORY_BASELINE_TAG
    suffix = "_".join(sorted(wanted))
    bstore = BaselineStore(
        run / f"baseline_cache_eval_{suffix}.json", cfg.inp,
        A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
        tag=(EXPLORATORY_BASELINE_TAG if args.exploratory
             else COMPLETE_BASELINE_TAG),
    )
    result = evaluate(agent, env, storms, bstore, "final", cso_floor=cfg.cso_floor)
    if args.repeat_check:
        repeated = evaluate(agent, env, storms, bstore, "final", cso_floor=cfg.cso_floor)
        _assert_repeatable(result, repeated)
    out = Path(args.out or run / f"final_eval_{suffix}.csv")
    result.to_csv(out, index=False)
    aggregates = {
        f"{split}/{rung}": aggregate_native(group)
        for (split, rung), group in result.groupby(["split", "rung"], dropna=False)
    }
    metadata = dict(
        checkpoint=str(checkpoint), checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        protocol_tag=args.protocol_tag if protocol_commit else None,
        protocol_commit=protocol_commit, splits=sorted(wanted), deterministic=True,
        repeat_checked=bool(args.repeat_check), aggregates=aggregates,
        research_status=status["research_status"],
        hydraulic_gate_passed=status["hydraulic_gate_passed"],
    )
    out.with_suffix(".summary.json").write_text(json.dumps(metadata, indent=1, default=float))
    env.close()
    print(json.dumps(metadata, indent=1, default=float))


if __name__ == "__main__":
    main()

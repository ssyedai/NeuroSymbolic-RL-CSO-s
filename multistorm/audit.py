"""Pre-flight storm audit CLI."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from . import adapters as A
from .baselines import BaselineStore
from .storms import assign_splits, load_storms, storm_table

log = logging.getLogger("audit")


def main(argv=None):
    p = argparse.ArgumentParser(description="Audit rainfall storms for multi-storm training")
    p.add_argument("--rain-dir", default="data/useful/rain_real_stormy_x2")
    p.add_argument("--inp", default="7MPF_CSO_08.inp")
    p.add_argument("--out-dir", default="runs")
    p.add_argument("--run-name", default="audit")
    p.add_argument("--scaling", default="peak")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--split-seed", type=int, default=0)
    p.add_argument("--split-manifest", default="data/useful/splits/splits_stormy_x2.json")
    p.add_argument("--cso-floor", type=float, default=1.0)
    p.add_argument("--skip-provenance", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    out = Path(args.out_dir) / args.run_name
    out.mkdir(parents=True, exist_ok=True)

    storms = load_storms(args.rain_dir, scaling=args.scaling)
    storms, split_info = assign_splits(
        storms, seed=args.split_seed, manifest_path=args.split_manifest)
    if not args.skip_provenance and (Path(args.rain_dir) / "data_manifest.json").exists():
        from research.guard import assert_provenance
        assert_provenance(storms, args.rain_dir)
    log.info("Split info: %s", split_info)

    env, agent, kb = A.build(args.seed)
    from .baselines import DEFAULT_BASELINE_TAG
    bstore = BaselineStore(
        Path(args.out_dir) / "baseline_cache.json",
        args.inp,
        A.calibrate_fn(env),
        A.static_fn(env),
        A.native_fn(env),
        tag=DEFAULT_BASELINE_TAG,
    )

    table = storm_table(storms)
    rows = []
    for s in storms:
        rec = bstore.get(s)
        static = rec["static"]
        native = rec.get("native") or {}
        warnings = []
        if static["cso_total"] <= args.cso_floor:
            warnings.append("NO_CSO")
        if (rec["baseline_flooding"] > 0.9 * 9500
                or static.get("r6_frac", 0) > 0.25):
            warnings.append("R6_DOMINATES")
        if static.get("flood_peak", 0) < 0.5 * 9500:
            warnings.append("R6_NEVER")
        if s.meta.get("padded"):
            warnings.append("PADDED")
        if s.meta.get("truncated"):
            warnings.append("TRUNCATED")
        row = table[table.storm_id == s.storm_id].iloc[0].to_dict()
        row.update({
            "baseline_flooding": rec["baseline_flooding"],
            "static_cso": static["cso_total"],
            "static_r6_frac": static["r6_frac"],
            "native_cso": native.get("cso_total"),
            "baseline_over_9500": rec["baseline_flooding"] / 9500.0,
            "warnings": "|".join(warnings) if warnings else "",
        })
        rows.append(row)

    df = pd.DataFrame(rows)
    path = out / "storm_audit.csv"
    df.to_csv(path, index=False)
    print(df.to_string(index=False))
    print(f"\nSplit counts: {split_info['counts']}")
    print(f"Wrote {path}")
    env.close()


if __name__ == "__main__":
    main()

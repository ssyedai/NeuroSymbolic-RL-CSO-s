# research/splits.py
"""Temporal year-block splits for observed events."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def split_by_year(events: pd.DataFrame, val_years: list[int], test_years: list[int],
                  min_per_split: int = 3) -> dict:
    yr = pd.to_datetime(events["t0"]).dt.year
    sp = pd.Series("train", index=events.index)
    sp[yr.isin(val_years)] = "val"
    sp[yr.isin(test_years)] = "test"
    out = dict(zip(events["storm_id"], sp))
    cnt = sp.value_counts().to_dict()
    missing = {k: cnt.get(k, 0) for k in ("train", "val", "test") if cnt.get(k, 0) < min_per_split}
    if missing:
        raise AssertionError(f"too few events per split: {cnt} (need >= {min_per_split})")
    return out


def auto_year_split(events: pd.DataFrame, min_per_split: int = 3) -> tuple[dict, dict]:
    """
    Choose val/test year blocks from the most recent years so each split has
    at least min_per_split events; train = earlier years.
    """
    ev = events.copy()
    ev["year"] = pd.to_datetime(ev["t0"]).dt.year
    years = sorted(ev["year"].unique())
    if len(years) < 3:
        raise RuntimeError(f"Need >=3 distinct years for temporal split; got {years}")

    # Grow test from the end, then val, remainder train
    test_years, val_years = [], []
    for y in reversed(years):
        n = int((ev["year"] == y).sum())
        if sum((ev["year"].isin(test_years + [y]))) <= max(min_per_split * 2, min_per_split) or len(test_years) == 0:
            if sum(ev["year"].isin(test_years)) < min_per_split:
                test_years.insert(0, int(y))
                continue
        if sum(ev["year"].isin(val_years)) < min_per_split:
            val_years.insert(0, int(y))
            continue
        break
    # Recompute cleanly: last ~25% years test, previous ~15% val
    n_y = len(years)
    n_test = max(1, round(0.25 * n_y))
    n_val = max(1, round(0.15 * n_y))
    test_years = [int(y) for y in years[-n_test:]]
    val_years = [int(y) for y in years[-(n_test + n_val):-n_test]] or [int(years[-(n_test + 1)])]
    # Ensure no overlap
    val_years = [y for y in val_years if y not in test_years]
    mapping = split_by_year(ev, val_years, test_years, min_per_split=min_per_split)
    info = {"val_years": val_years, "test_years": test_years,
            "counts": pd.Series(mapping).value_counts().to_dict()}
    return mapping, info


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="data/useful/rain_real/events.csv")
    ap.add_argument("--config", default="configs/data.json")
    ap.add_argument("--out", default="splits.json")
    ap.add_argument("--auto", action="store_true", help="Auto-select year blocks")
    ap.add_argument("--min-per-split", type=int, default=3)
    args = ap.parse_args(argv)

    ev = pd.read_csv(args.events)
    cfg = json.loads(Path(args.config).read_text())
    if args.auto:
        mapping, info = auto_year_split(ev, min_per_split=args.min_per_split)
        print("Auto split:", info)
    else:
        mapping = split_by_year(
            ev, cfg["split"]["val_years"], cfg["split"]["test_years"],
            min_per_split=args.min_per_split)
        info = {"val_years": cfg["split"]["val_years"], "test_years": cfg["split"]["test_years"]}
    Path(args.out).write_text(json.dumps(mapping, indent=1))
    print(f"Wrote {args.out} ({len(mapping)} storms)")
    print(info)


if __name__ == "__main__":
    main()

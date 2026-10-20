"""Screen observed events by static-baseline CSO (model response only; no agent)."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from pathlib import Path

import pandas as pd

from multistorm import adapters as A
from multistorm.baselines import BaselineStore
from multistorm.metrics_ext import CFS_TO_M3_PER_STEP
from multistorm.storms import load_storms

log = logging.getLogger("screen_events")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Keep only real storms that produce baseline CSO")
    ap.add_argument("--src", default="data/useful/rain_real_full")
    ap.add_argument("--dst", default="data/useful/rain_real_stormy")
    ap.add_argument("--inp", default="7MPF_CSO_08.inp")
    ap.add_argument("--min-cso-m3", type=float, default=1000.0,
                    help="Inspect screening.csv, then fix this in docs/protocol.md")
    ap.add_argument("--cache", default="runs/baseline_cache.json")
    ap.add_argument("--limit", type=int, default=0, help="Optional cap for dry-run / debug")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    storms = load_storms(a.src, scaling="none")
    # Screen largest totals first so we learn early whether any event is stormy
    storms = sorted(storms, key=lambda s: -float(s.depth.sum()))
    if a.limit:
        storms = storms[: a.limit]

    env, agent, kb = A.build(0)
    env.physical_rain = True
    bs = BaselineStore(
        a.cache, a.inp,
        A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
        tag="v3-phys-timeseries",
    )

    rows = []
    t0 = time.time()
    for i, s in enumerate(storms, 1):
        r = bs.get(s)
        st = r["static"]
        n = r.get("native") or {}
        row = dict(
            storm_id=s.storm_id,
            total_mm=float(s.depth.sum()),
            max15_mm=float(s.depth.max()),
            static_cso_m3=float(st["cso_total"]) * CFS_TO_M3_PER_STEP,
            native_cso_m3=(float(n["cso_total"]) * CFS_TO_M3_PER_STEP
                           if n and "cso_total" in n else float("nan")),
            static_flood=float(st["flood_total"]),
            fill_max=float(st["fill_max"]),
            r6_frac=float(st["r6_frac"]),
            baseline_flooding=float(r["baseline_flooding"]),
        )
        rows.append(row)
        if i % 5 == 0 or i == 1 or row["static_cso_m3"] > 0:
            log.info("[%d/%d] %s total=%.1fmm cso_m3=%.1f flood=%.1f (%.0f min)",
                     i, len(storms), s.storm_id, row["total_mm"],
                     row["static_cso_m3"], row["static_flood"],
                     (time.time() - t0) / 60)

    df = pd.DataFrame(rows).sort_values("total_mm")
    df["stormy"] = df.static_cso_m3 >= a.min_cso_m3
    dst = Path(a.dst)
    dst.mkdir(exist_ok=True)
    df.to_csv(dst / "screening.csv", index=False)
    print(df.to_string(index=False))
    print(f"\nstormy: {int(df.stormy.sum())} of {len(df)}  (threshold={a.min_cso_m3} m3)")
    print(f"Wrote {dst / 'screening.csv'}")

    keep = set(df.loc[df.stormy, "storm_id"])
    man_path = Path(a.src) / "data_manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {"storms": {}}
    for sid in keep:
        shutil.copy2(Path(a.src) / f"{sid}.csv", dst / f"{sid}.csv")
    man["storms"] = {k: v for k, v in man.get("storms", {}).items() if k in keep}
    man["screening"] = dict(
        rule=f"static baseline CSO >= {a.min_cso_m3} m3",
        source=a.src,
        n_screened=int(len(df)),
        n_stormy=int(df.stormy.sum()),
        n_rejected_non_stormy=int((~df.stormy).sum()),
    )
    (dst / "data_manifest.json").write_text(json.dumps(man, indent=1))

    ev_path = Path(a.src) / "events.csv"
    if ev_path.exists():
        ev = pd.read_csv(ev_path)
        col = "storm_id" if "storm_id" in ev.columns else "id"
        ev[ev[col].isin(keep)].to_csv(dst / "events.csv", index=False)

    env.close()
    return df


if __name__ == "__main__":
    main()

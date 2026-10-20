"""Stage 11 — Build rain_real/ event CSVs from standardized observed series."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research.events import (
    N,
    ari_class,
    descriptors,
    detect_events,
    empirical_severity,
    extract_window,
    load_standardized,
    select_non_overlapping,
)

log = logging.getLogger("build_real_storms")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pfds(path: Path | None) -> pd.DataFrame | None:
    if path is None or not Path(path).exists():
        log.warning("PFDS table missing at %s — using empirical severity only", path)
        return None
    df = pd.read_csv(path, index_col=0)
    df.index = df.index.astype(int)
    df.columns = df.columns.astype(float)
    return df


def count_other_events(p: pd.Series, w: pd.Series, ietd_h: float, min_depth_mm: float) -> int:
    evs = detect_events(p.loc[w.index[0]:w.index[-1]], ietd_h=ietd_h, min_depth_mm=min_depth_mm)
    return max(0, len(evs) - 1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/data.json")
    ap.add_argument("--out-dir", default="data/useful/rain_real")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cfg = json.loads(Path(args.config).read_text())
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    params = cfg["event_params"]
    raw_man = json.loads(Path("data/raw/raw_manifest.json").read_text())
    src_sha = {g["station_id"]: g["standardized_sha256"] for g in raw_man["gauges"]}
    pfds = load_pfds(Path(cfg.get("pfds_csv", "")))

    kept_rows, rejected = [], []
    candidates = []

    for g in cfg["gauges"]:
        sid = g["station_id"]
        std = Path("data/raw") / f"{sid}_15min_standardized.csv"
        p = load_standardized(std, std_offset_h=cfg.get("std_offset_h", -5))
        events = detect_events(p, params["ietd_h"], params["min_event_depth_mm"])
        log.info("%s: %d candidate events", sid, len(events))
        for ev in events:
            w, reason = extract_window(p, ev, params["tail_margin_h"])
            if reason:
                rejected.append(dict(
                    gauge=sid, start=str(ev["start"]), end=str(ev["end"]),
                    depth_mm=ev["depth_mm"], reject=reason))
                continue
            desc = descriptors(w)
            t0 = w.index[0]
            storm_id = f"{sid}_{t0.strftime('%Y%m%d')}"
            candidates.append(dict(
                storm_id=storm_id, gauge=sid, t0=t0, end=ev["end"],
                window=w, **desc,
                n_other_events=count_other_events(
                    p, w, params["ietd_h"], params["min_event_depth_mm"]),
                source_sha256=src_sha[sid],
            ))

    # Empirical thresholds from candidate totals (before overlap filter)
    totals = np.array([c["total_mm"] for c in candidates]) if candidates else np.array([0.0])
    emp_thr = dict(
        p33=float(np.quantile(totals, 0.33)) if len(totals) else 0.0,
        p66=float(np.quantile(totals, 0.66)) if len(totals) else 0.0,
        p90=float(np.quantile(totals, 0.90)) if len(totals) else 0.0,
    )

    # Non-overlapping within each gauge separately, then allow multi-gauge same day
    by_gauge: dict[str, list] = {}
    for c in candidates:
        by_gauge.setdefault(c["gauge"], []).append(c)
    final = []
    for sid, rows in by_gauge.items():
        keep, drop = select_non_overlapping(rows)
        final.extend(keep)
        for d in drop:
            rejected.append(dict(
                gauge=sid, start=str(d["t0"]), end=str(d.get("end")),
                depth_mm=d["total_mm"], reject=d["reject"]))

    manifest_storms = {}
    for r in sorted(final, key=lambda x: x["t0"]):
        ari = ari_class(r, pfds)
        if ari["severity_class"] == "unknown":
            ari["severity_class"] = empirical_severity(r["total_mm"], emp_thr)
        # intensity mm/h for SWMM INTENSITY gage (= depth_mm_per_15min * 4)
        intensity = r["window"].to_numpy(float) * 4.0
        fpath = out / f"{r['storm_id']}.csv"
        np.savetxt(fpath, intensity, fmt="%.6f")
        file_sha = file_sha256(fpath)
        row = dict(
            storm_id=r["storm_id"], gauge=r["gauge"], t0=str(r["t0"]),
            total_mm=r["total_mm"], max15_mm=r["max15_mm"], max1h_mm=r["max1h_mm"],
            max3h_mm=r["max3h_mm"], max6h_mm=r["max6h_mm"], max24h_mm=r["max24h_mm"],
            wet_steps=r["wet_steps"], peak_pos_frac=r["peak_pos_frac"],
            n_other_events=r["n_other_events"],
            severity_class=ari["severity_class"],
            ari_15min=ari.get("ari_15min"), ari_60min=ari.get("ari_60min"),
            ari_360min=ari.get("ari_360min"), ari_1440min=ari.get("ari_1440min"),
            ari_max=ari.get("ari_max"),
            file=str(fpath.name),
        )
        kept_rows.append(row)
        manifest_storms[r["storm_id"]] = dict(
            provenance="observed",
            gauge=r["gauge"],
            source_sha256=r["source_sha256"],
            file_sha256=file_sha,
            t0=str(r["t0"]),
            scaling="none",
        )

    events_df = pd.DataFrame(kept_rows)
    events_df.to_csv(out / "events.csv", index=False)
    pd.DataFrame(rejected).to_csv(out / "events_rejected.csv", index=False)
    man = dict(storms=manifest_storms, params=params, empirical_thresholds=emp_thr,
               gauges=cfg["gauges"], scaling="none")
    (out / "data_manifest.json").write_text(json.dumps(man, indent=2, default=str))

    # Overview figure
    if len(events_df):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        for sev, sub in events_df.groupby("severity_class"):
            axes[0].scatter(sub.total_mm, sub.max15_mm * 4.0, label=sev, s=40, alpha=0.8)
        axes[0].set_xlabel("total_mm"); axes[0].set_ylabel("peak intensity mm/h")
        axes[0].legend(fontsize=8); axes[0].set_title("Events")
        yr = pd.to_datetime(events_df.t0).dt.year
        yr.value_counts().sort_index().plot(kind="bar", ax=axes[1], color="steelblue")
        axes[1].set_title("Events per year"); axes[1].set_xlabel("year")
        fig.tight_layout()
        fig.savefig(out / "events_overview.png", dpi=140)
        plt.close(fig)

    log.info("Kept %d events; rejected %d", len(events_df), len(rejected))
    print(events_df.head().to_string(index=False) if len(events_df) else "No events")
    print(f"Wrote {out}/events.csv and data_manifest.json")


if __name__ == "__main__":
    main()

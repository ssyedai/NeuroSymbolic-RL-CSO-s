"""Build the full scenario directory from real events: families R (unscaled), T (return-period), C (CSO-onset).

Inputs : <rain-dir>/<storm_id>.csv  (headerless, 288 rows, INTENSITY mm/h)  + events.csv (storm_id, t0, ...)
         optional onset table (storm_id,k_onset)  produced by research/onset_table.py
         optional Atlas 14 table (duration_min + ARI columns, mm) for T > 100 yr
Outputs: <out>/<variant_id>.csv, <out>/data_manifest.json, <out>/scenarios.csv, <out>/rejected.csv, <out>/splits.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research.guard import file_sha256
from research import scenarios as S


def load_parents(rain_dir, events_csv, min_year):
    ev = pd.read_csv(events_csv, parse_dates=["t0"])
    ev = ev[ev["t0"].dt.year >= min_year]
    parents = []
    for r in ev.itertuples():
        f = Path(rain_dir) / f"{r.storm_id}.csv"
        if not f.exists():
            continue
        inten = pd.read_csv(f, header=None).to_numpy(float).ravel()
        if len(inten) != S.N_STEPS:
            continue
        parents.append(dict(storm_id=r.storm_id, year=int(r.t0.year), depth=inten / 4.0, t0=str(r.t0)))
    return parents


def load_atlas(path):
    if not path:
        return None
    df = pd.read_csv(path).set_index("duration_min")
    df.columns = [float(c) for c in df.columns]
    return df


def write_variant(out, vid, depth):
    f = Path(out) / f"{vid}.csv"
    pd.DataFrame(np.asarray(depth) * 4.0).to_csv(f, header=False, index=False)   # intensity mm/h
    return f


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", required=True); ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--onset", default=None)
    ap.add_argument("--atlas", default=None); ap.add_argument("--min-year", type=int, default=2010)
    ap.add_argument("--val-years", required=True); ap.add_argument("--test-years", required=True)
    ap.add_argument("--ladder-train", default="5,10,25,50,100"); ap.add_argument("--ladder-test", default="200,500,1000")
    ap.add_argument("--mults", default="1,1.5,2,3"); ap.add_argument("--k-hi", type=float, default=4.0)
    ap.add_argument("--k-cap", type=float, default=12.0); ap.add_argument("--min-anchor-mm", type=float, default=15.0)
    ap.add_argument("--flat-factors", default="", help="e.g. 2 -> family F (flat multiplier) for the D1 ablation diet")
    ap.add_argument("--max-spread", type=float, default=10.0, help="max ratio between T_eq at 1h/6h/24h after scaling")
    ap.add_argument("--min-R-anchor-mm", type=float, default=15.0, help="min 6h depth for unscaled family R")
    a = ap.parse_args(argv)
    ints = lambda s: [int(x) for x in s.split(",") if x]
    flts = lambda s: [float(x) for x in s.split(",") if x]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    parents = load_parents(a.rain_dir, a.events, a.min_year)
    splits = S.assign_parent_splits(parents, ints(a.val_years), ints(a.test_years))
    atlas = load_atlas(a.atlas)
    onset = {}
    onset_evidence = {}
    if a.onset:
        o = pd.read_csv(a.onset)
        required = {"storm_id", "k_onset", "volume_units", "complete_four_outfall_objective"}
        if not required <= set(o.columns):
            raise RuntimeError("Onset table predates complete four-outfall m3 accounting")
        if not o.volume_units.eq("m3").all() or not o.complete_four_outfall_objective.eq(True).all():
            raise RuntimeError("Onset table does not use the complete four-outfall m3 objective")
        summary_path = Path(str(a.onset) + ".summary.json")
        if summary_path.exists() and not json.loads(summary_path.read_text()).get("G1_pass", False):
            raise RuntimeError("Onset table failed G1")
        onset = {r.storm_id: (None if pd.isna(r.k_onset) else float(r.k_onset)) for r in o.itertuples()}
        onset_evidence = dict(
            onset_sha256=file_sha256(a.onset), onset_volume_units="m3",
            onset_complete_four_outfall_objective=True,
        )

    variants, rej = [], []
    for p in parents:                                   # family R (unscaled, observed)
        if S.roll_max(p["depth"], S.ANCHOR_MIN // 15) >= a.min_R_anchor_mm:
            variants.append(S._variant(p, "R", "R", 1.0, p["depth"], T_target=float("nan"), onset_mult=float("nan")))
    vt, rt = S.build_T_variants(parents, flts(a.ladder_train) + flts(a.ladder_test), k_hi=a.k_hi,
                                min_anchor_mm=a.min_anchor_mm, max_spread=a.max_spread, pfds=atlas)
    variants += vt; rej += rt
    if a.flat_factors:
        vf, rf = S.build_F_variants(parents, flts(a.flat_factors)); variants += vf; rej += rf
    if onset:
        vc, rc = S.build_C_variants(parents, onset, flts(a.mults), a.k_cap)
        variants += vc; rej += rc

    manifest, rows = {}, []
    test_only = set(f"T{x:g}" for x in flts(a.ladder_test))
    for v in variants:
        f = write_variant(out, v["variant_id"], v["depth"])
        split = splits[v["parent"]]
        prov = "observed" if v["family"] == "R" else "scaled_real"
        manifest[v["variant_id"]] = dict(provenance=prov, parent=v["parent"], family=v["family"], rung=v["rung"], k=v["k"],
                                         T_target=v["T_target"], onset_mult=v["onset_mult"], T_by_dur=v["T_by_dur"],
                                         split=split, file_sha256=file_sha256(f), test_only=v["rung"] in test_only)
        rows.append(dict(variant_id=v["variant_id"], parent=v["parent"], year=v["year"], split=split, family=v["family"],
                         rung=v["rung"], k=v["k"], T_anchor=v["T_anchor"], T1h=v["T_by_dur"][60], T24h=v["T_by_dur"][1440],
                         total_mm=float(v["depth"].sum()), max15_mm=float(v["depth"].max()), provenance=prov,
                         test_only=v["rung"] in test_only))
    evidence = dict(**onset_evidence)
    if a.atlas:
        evidence.update(atlas_sha256=file_sha256(a.atlas), atlas_path=str(a.atlas))
    (out / "data_manifest.json").write_text(json.dumps({
        "schema_version": 2,
        "objective": "complete_four_outfall_cumulative_m3",
        "storms": manifest, "params": vars(a), "evidence": evidence,
    }, indent=1, default=str))
    (out / "splits.json").write_text(json.dumps({r["variant_id"]: r["split"] for r in rows}, indent=1))
    pd.DataFrame(rows).to_csv(out / "scenarios.csv", index=False)
    pd.DataFrame(rej).to_csv(out / "rejected.csv", index=False)
    return pd.DataFrame(rows), pd.DataFrame(rej)


if __name__ == "__main__":
    df, rj = main()
    print(df.groupby(["split", "rung"]).size().unstack(fill_value=0).to_string())
    print("rejected:", rj.reason.str.replace(r"\(.*\)", "", regex=True).value_counts().to_dict() if len(rj) else {})

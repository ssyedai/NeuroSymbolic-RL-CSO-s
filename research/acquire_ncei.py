"""
Stage 10 — Acquire / standardize NCEI HPD 15-minute precipitation (v2 beta).

Official format source:
  https://www.ncei.noaa.gov/pub/data/hpd/auto/v2/beta/15min/readme.15min.txt

Ambiguities documented (not guessed):
  - Beta readme says MF/QF are "placeholders", but files contain MF in
    {Z, space, g, a, ., A, E} and QF in {space, M, A, P, D}.
  - We map QF ∈ {M,A,D} and value==-9999 → NaN (missing / accumulated / deleted
    per DSI-3260 semantics). QF=P kept with value (partial daily sum flag is on
    DlySum; on 15-min slots we keep the numeric value if valid).
  - MF 'a'/'A' with sentinel-like values treated as accumulation → NaN.
  - MF 'Z' with 0 is treated as explicit dry (operating zero).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("acquire_ncei")

HUNDREDTHS_INCH_TO_MM = 0.01 * 25.4
MISSING_VAL = -9999
BAD_QF = {"M", "A", "D"}
ACCUM_MF = {"a", "A"}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _slots():
    """96 quarter-hour labels HHMM for a calendar day."""
    return [f"{h:02d}{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]


def parse_station_csv(path: Path) -> pd.DataFrame:
    """Return long-form DataFrame: time_utc, precip_mm (NaN=missing/flagged)."""
    df = pd.read_csv(path)
    required = {"STATION", "DATE", "ELEMENT"}
    if not required.issubset(df.columns):
        raise ValueError(f"{path}: missing columns {required - set(df.columns)}")
    slots = _slots()
    rows = []
    for _, rec in df.iterrows():
        day = pd.Timestamp(rec["DATE"])
        for hhmm in slots:
            vcol, mfcol, qfcol = f"{hhmm}Val", f"{hhmm}MF", f"{hhmm}QF"
            if vcol not in df.columns:
                continue
            raw = rec[vcol]
            mf = str(rec.get(mfcol, "")).strip()
            qf = str(rec.get(qfcol, "")).strip()
            try:
                val = int(raw)
            except (TypeError, ValueError):
                precip = np.nan
            else:
                if val == MISSING_VAL or qf in BAD_QF or mf in ACCUM_MF:
                    precip = np.nan
                elif val < 0:
                    precip = np.nan
                else:
                    precip = float(val) * HUNDREDTHS_INCH_TO_MM
            # End of 15-min period as UTC wall time at station local? 
            # Inventory UTC_Offset for MI is typically -5. Files are in local standard
            # clock of the observing station (COOP convention). We store as naive UTC
            # label = local + offset applied later in load_standardized via std_offset.
            # Here we store station-local time stamped as UTC-naive ISO for consistency
            # with Stage 11 load_standardized which applies STD_OFFSET_H.
            h, m = int(hhmm[:2]), int(hhmm[2:])
            # Interval ending time: slot label is START of interval per readme
            # ("0000Val = precipitation during 00:00-00:15")
            t_local = day + pd.Timedelta(hours=h, minutes=m)
            rows.append((t_local.isoformat(), precip))
    out = pd.DataFrame(rows, columns=["time_utc", "precip_mm"])
    # Deduplicate identical timestamps if any
    out = out.groupby("time_utc", as_index=False)["precip_mm"].sum(min_count=1)
    return out


def coverage_report(series_df: pd.DataFrame) -> pd.DataFrame:
    df = series_df.copy()
    df["time_utc"] = pd.to_datetime(df["time_utc"])
    df["year"] = df["time_utc"].dt.year
    df["month"] = df["time_utc"].dt.month
    g = df.groupby(["year", "month"]).agg(
        n=("precip_mm", "size"),
        n_valid=("precip_mm", lambda s: int(s.notna().sum())),
        n_wet=("precip_mm", lambda s: int((s.fillna(0) > 0).sum())),
        total_mm=("precip_mm", "sum"),
    )
    g["valid_frac"] = g["n_valid"] / g["n"]
    return g.reset_index()


def standardize_gauge(station_id: str, raw_csv: Path, out_dir: Path, meta: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    std_path = out_dir / f"{station_id}_15min_standardized.csv"
    parsed = parse_station_csv(raw_csv)
    parsed.to_csv(std_path, index=False)
    cov = coverage_report(parsed)
    cov_path = out_dir / f"{station_id}_coverage.csv"
    cov.to_csv(cov_path, index=False)
    yearly = cov.groupby("year").agg(valid_frac=("valid_frac", "mean"), months=("month", "count"))
    low = yearly[yearly["valid_frac"] < 0.90]
    entry = {
        "station_id": station_id,
        "name": meta.get("name"),
        "role": meta.get("role"),
        "lat": meta.get("lat"),
        "lon": meta.get("lon"),
        "source_file": str(raw_csv),
        "source_sha256": file_sha256(raw_csv),
        "standardized_file": str(std_path),
        "standardized_sha256": file_sha256(std_path),
        "coverage_file": str(cov_path),
        "unit_conversion": "QPCP hundredths_of_inch * 0.01 * 25.4 → mm",
        "retrieval_date_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": meta.get("source_url_template", "").format(station_id=station_id),
        "years_valid_frac_lt_90": low.index.astype(int).tolist(),
        "n_timesteps": int(len(parsed)),
        "n_valid": int(parsed["precip_mm"].notna().sum()),
        "ambiguities": [
            "Beta readme labels MF/QF as placeholders but files contain flags; "
            "mapped via DSI-3260 semantics (M/A/D → NaN).",
            "Timestamps stored as station-local wall clock in time_utc column; "
            "load_standardized applies fixed EST offset (-5).",
        ],
    }
    log.info("%s: %d steps, valid=%.1f%%, low-coverage years=%s",
             station_id, entry["n_timesteps"],
             100 * entry["n_valid"] / max(entry["n_timesteps"], 1),
             entry["years_valid_frac_lt_90"])
    return entry


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/data.json")
    p.add_argument("--raw-dir", default="data/raw/ncei_source")
    p.add_argument("--out-dir", default="data/raw")
    p.add_argument("--download", action="store_true",
                   help="Download missing station .15m.csv files from NCEI")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cfg = json.loads(Path(args.config).read_text())
    raw_dir, out_dir = Path(args.raw_dir), Path(args.out_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.download:
        import urllib.request
        for g in cfg["gauges"]:
            sid = g["station_id"]
            dest = raw_dir / f"{sid}.15m.csv"
            if dest.exists():
                log.info("exists %s", dest)
                continue
            url = g["source_url_template"].format(station_id=sid)
            log.info("GET %s", url)
            urllib.request.urlretrieve(url, dest)

    entries = []
    for g in cfg["gauges"]:
        sid = g["station_id"]
        src = raw_dir / f"{sid}.15m.csv"
        if not src.exists():
            raise FileNotFoundError(f"Missing {src}; re-run with --download")
        entries.append(standardize_gauge(sid, src, out_dir, g))

    manifest = {
        "dataset": "NCEI HPD / CPD 15-minute precipitation v2 beta",
        "citation": (
            "Hourly Precipitation Data (HPD) Network of 15-minute observations, "
            "Version 2 alpha/beta, NOAA NCEI."
        ),
        "docs_url": "https://www.ncei.noaa.gov/pub/data/hpd/auto/v2/beta/15min/readme.15min.txt",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "gauges": entries,
        "rules": {
            "explicit_zero": "value>=0 with QF not in {M,A,D} and MF not accumulation",
            "nan": "missing (-9999), QF in {M,A,D}, or accumulation MF",
        },
    }
    man_path = out_dir / "raw_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({e["station_id"]: {
        "valid_pct": round(100 * e["n_valid"] / e["n_timesteps"], 1),
        "low_years": e["years_valid_frac_lt_90"],
    } for e in entries}, indent=2))
    print(f"Wrote {man_path}")


if __name__ == "__main__":
    main()

"""research/events.py — observed-event detection and 72 h window extraction."""
from __future__ import annotations

import numpy as np
import pandas as pd

N = 288                      # 72 h at 15 min
STD_OFFSET_H = -5            # fixed UTC offset for Detroit standard time (no DST)


def load_standardized(path, std_offset_h: float = STD_OFFSET_H) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["time_utc"])
    t = (df["time_utc"].dt.tz_localize(None) + pd.Timedelta(hours=std_offset_h)).dt.floor("15min")
    s = pd.Series(df["precip_mm"].to_numpy(float), index=t).groupby(level=0).sum(min_count=1)
    idx = pd.date_range(s.index.min(), s.index.max(), freq="15min")
    return s.reindex(idx)                         # NaN = missing/unknown


def detect_events(p: pd.Series, ietd_h=6.0, min_depth_mm=6.35) -> list[dict]:
    wet = np.flatnonzero(np.nan_to_num(p.to_numpy(), nan=0.0) > 0)
    if wet.size == 0:
        return []
    gap, spans, start, last = int(ietd_h * 4), [], wet[0], wet[0]
    for j in wet[1:]:
        if j - last - 1 >= gap:
            spans.append((start, last)); start = j
        last = j
    spans.append((start, last))
    out = []
    for s, e in spans:
        d = float(np.nansum(p.iloc[s:e + 1]))
        if d >= min_depth_mm:
            out.append(dict(start=p.index[s], end=p.index[e], i0=s, i1=e, depth_mm=d))
    return out


def extract_window(p: pd.Series, ev: dict, tail_margin_h=6.0):
    """Return (window Series, reject_reason|None)."""
    t0 = ev["start"].normalize()
    if t0 not in p.index:
        return None, "window_start_outside_record"
    i0 = p.index.get_loc(t0)
    if isinstance(i0, slice):
        return None, "ambiguous_window_start"
    if i0 + N > len(p):
        return None, "window_exceeds_record"
    w = p.iloc[i0:i0 + N]
    if w.isna().any():
        return None, "missing_values_in_window"
    if ev["end"] > w.index[-1] - pd.Timedelta(hours=tail_margin_h):
        return None, "event_too_long_for_window"
    return w, None


def descriptors(w: pd.Series) -> dict:
    a = w.to_numpy(float)
    r = lambda k: float(pd.Series(a).rolling(k).sum().max())
    return dict(total_mm=float(a.sum()), max15_mm=float(a.max()), max1h_mm=r(4), max3h_mm=r(12),
                max6h_mm=r(24), max24h_mm=r(96), wet_steps=int((a > 0).sum()),
                peak_pos_frac=float(a.argmax() / max(N - 1, 1)))


def select_non_overlapping(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Greedy by event depth (largest first). Windows are [t0, t0+72h)."""
    keep, drop = [], []
    for r in sorted(rows, key=lambda r: -r["total_mm"]):
        if any(abs((r["t0"] - k["t0"]).total_seconds()) < N * 900 for k in keep):
            drop.append({**r, "reject": "overlaps_larger_event"})
        else:
            keep.append(r)
    return sorted(keep, key=lambda r: r["t0"]), drop


def ari_class(desc: dict, pfds: pd.DataFrame | None) -> dict:
    """pfds: index = duration minutes; columns = ARI years; values = depth mm."""
    if pfds is None or pfds.empty:
        return dict(ari_15min=np.nan, ari_60min=np.nan, ari_360min=np.nan,
                    ari_1440min=np.nan, ari_max=np.nan, severity_class="unknown")
    cols = {15: "max15_mm", 60: "max1h_mm", 360: "max6h_mm", 1440: "max24h_mm"}
    out, aris = {}, np.array(pfds.columns, float)
    for dur, key in cols.items():
        if dur not in pfds.index:
            out[f"ari_{dur}min"] = np.nan
            continue
        depths = pfds.loc[dur].to_numpy(float)
        x = desc[key]
        if x < depths[0]:
            ari = float(aris[0]) / 2
        elif x > depths[-1]:
            ari = float("inf")
        else:
            ari = float(np.exp(np.interp(x, depths, np.log(aris))))
        out[f"ari_{dur}min"] = ari
    vals = [v for v in out.values() if v == v]
    out["ari_max"] = max(vals) if vals else float("nan")
    am = out["ari_max"]
    out["severity_class"] = ("<1yr" if am < 1 else "1-2yr" if am < 2 else
                             "2-5yr" if am < 5 else "5-10yr" if am < 10 else ">=10yr"
                             if am == am else "unknown")
    return out


def empirical_severity(total_mm: float, thresholds: dict) -> str:
    """Fallback severity labels from dataset quantiles when PFDS is unavailable."""
    if total_mm < thresholds["p33"]:
        return "mild"
    if total_mm < thresholds["p66"]:
        return "moderate"
    if total_mm < thresholds["p90"]:
        return "severe"
    return "extreme"

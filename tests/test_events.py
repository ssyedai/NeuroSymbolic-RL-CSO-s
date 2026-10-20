"""Tests for event extraction (Stage 11)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.events import N, detect_events, extract_window, select_non_overlapping
from multistorm.storms import rain_to_gage_value


def _series_from_mm(values, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="15min")
    return pd.Series(values, index=idx)


def test_detect_two_events_with_ietd():
    # 2 h rain, 7 h dry, 2 h rain
    wet = [1.0] * 8
    dry = [0.0] * (7 * 4)
    vals = wet + dry + wet + [0.0] * 50
    p = _series_from_mm(vals)
    ev = detect_events(p, ietd_h=6.0, min_depth_mm=1.0)
    assert len(ev) == 2
    assert ev[0]["depth_mm"] == pytest.approx(8.0)


def test_reject_missing_in_window():
    vals = [1.0] * 20 + [0.0] * 400
    p = _series_from_mm(vals)
    p.iloc[10] = np.nan
    ev = detect_events(p, ietd_h=6.0, min_depth_mm=1.0)[0]
    w, reason = extract_window(p, ev)
    assert w is None and reason == "missing_values_in_window"


def test_reject_long_event():
    # 90 h continuous rain starting at t0 — too long for 72h window with 6h tail
    vals = [1.0] * (90 * 4)
    p = _series_from_mm(vals)
    ev = detect_events(p, ietd_h=6.0, min_depth_mm=1.0)[0]
    w, reason = extract_window(p, ev, tail_margin_h=6.0)
    assert reason == "event_too_long_for_window"


def test_overlap_keeps_larger():
    t0 = pd.Timestamp("2020-01-01")
    rows = [
        dict(t0=t0, total_mm=10.0),
        dict(t0=t0 + pd.Timedelta(hours=12), total_mm=30.0),
        dict(t0=t0 + pd.Timedelta(days=5), total_mm=5.0),
    ]
    keep, drop = select_non_overlapping(rows)
    assert len(keep) == 2
    assert keep[0]["total_mm"] == 30.0 or any(k["total_mm"] == 30 for k in keep)
    assert any(d["reject"] == "overlaps_larger_event" for d in drop)


def test_rain_to_gage_value():
    # 2.5 mm / 15 min = 10 mm/h = 10/25.4 in/h
    assert rain_to_gage_value(2.5) == pytest.approx(2.5 / 6.35)
    assert rain_to_gage_value(0.0) == 0.0

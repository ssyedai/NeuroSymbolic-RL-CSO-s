"""Unit tests for multistorm.storms (no SWMM required)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from multistorm.storms import (
    N_STEPS,
    PEAK_TARGET,
    StormSampler,
    assign_splits,
    load_storms,
    make_storm,
)

ROOT = Path(__file__).resolve().parents[1]
RAIN = ROOT / "data/unused/rain"


def test_header_row_skipping(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("time,rain\n1.0\n2.0\n3.0\n")
    # first row becomes NaN after coerce → dropped by dropna; remaining 3 rows padded
    storms = load_storms(tmp_path, scaling="none")
    assert len(storms) == 1
    assert storms[0].intensity[0] in (1.0, 2.0)  # header may coerce to nan and drop


def test_datetime_column_skipping(tmp_path):
    df = pd.DataFrame({
        0: pd.date_range("2020-01-01", periods=10, freq="15min"),
        1: np.linspace(1, 5, 10),
    })
    p = tmp_path / "dt.csv"
    df.to_csv(p, header=False, index=False)
    storms = load_storms(tmp_path, scaling="none")
    assert len(storms) == 1
    assert storms[0].intensity.max() == pytest.approx(5.0)


def test_multi_column_files(tmp_path):
    df = pd.DataFrame({0: np.ones(50), 1: np.full(50, 2.0)})
    (tmp_path / "m.csv").write_text(df.to_csv(header=False, index=False))
    storms = load_storms(tmp_path, scaling="none")
    assert len(storms) == 2
    assert storms[0].storm_id.endswith("_c0")
    assert storms[1].intensity.max() == pytest.approx(2.0)


def test_padding_truncation():
    short = make_storm(np.ones(10), "short", "x", scaling="none")
    assert len(short.depth) == N_STEPS
    assert short.meta["padded"] is True
    long = make_storm(np.ones(400), "long", "x", scaling="none")
    assert len(long.depth) == N_STEPS
    assert long.meta["truncated"] is True


def test_nan_negative_dry_rejection():
    with pytest.raises(ValueError, match="NaN"):
        make_storm(np.array([1.0, np.nan, 2.0]), "n", "x")
    with pytest.raises(ValueError, match="negative"):
        make_storm(np.array([1.0, -0.1, 2.0]), "n", "x")
    with pytest.raises(ValueError, match="dry"):
        make_storm(np.zeros(50), "n", "x")


def test_trial7_scaling_raindata():
    storms = load_storms(RAIN, scaling="peak")
    rain = [s for s in storms if s.storm_id == "raindata"][0]
    assert rain.intensity.max() == pytest.approx(PEAK_TARGET, rel=1e-6)
    # Trial 7: depth = intensity * 900/3600; total ≈ 114 mm
    assert rain.depth.sum() == pytest.approx(114.0, abs=5.0)
    wet = int((rain.depth > 0).sum())
    assert 60 <= wet <= 100
    assert rain.depth.max() == pytest.approx(6.0, abs=0.05)  # 24 * 0.25


def test_split_determinism():
    storms = load_storms(RAIN, scaling="peak")
    a, ia = assign_splits(storms, seed=42)
    b, ib = assign_splits(storms, seed=42)
    assert [s.split for s in a] == [s.split for s in b]
    assert ia["counts"] == ib["counts"]


def test_extrapolation_guard():
    # synthesize 6 storms with distinct totals
    storms = [
        make_storm(np.full(288, v), f"s{v}", "x", scaling="none")
        for v in (1, 2, 3, 4, 5, 10)
    ]
    out, info = assign_splits(storms, seed=0, extrapolation_guard=True)
    # extremes (1 and 10) should remain in train
    by_id = {s.storm_id: s.split for s in out}
    assert by_id["s1"] == "train"
    assert by_id["s10"] == "train"


def test_sampler_coverage():
    storms = [
        make_storm(np.full(288, v + 1), f"s{v}", "x", scaling="none")
        for v in range(4)
    ]
    samp = StormSampler(storms, mode="shuffled_cycle", seed=1)
    seen = [samp.next().storm_id for _ in range(4)]
    assert sorted(seen) == sorted(s.storm_id for s in storms)
    # second cycle also covers all
    seen2 = [samp.next().storm_id for _ in range(4)]
    assert sorted(seen2) == sorted(s.storm_id for s in storms)

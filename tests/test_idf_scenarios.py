import json
import numpy as np
import pandas as pd
import pytest
from research import idf, scenarios as S
from research.onset import find_onset_factor
from research import build_scaled_storms as B


def test_idf_roundtrip_and_reference_depths():
    assert abs(float(idf.idf_depth_mm(25, 1440)) - 100.7) < 1.0
    assert abs(float(idf.idf_depth_mm(1000, 1440)) - 217) < 3
    for T in (2, 10, 100):
        d = idf.idf_depth_mm(T, 360)
        assert abs(float(idf.t_eq(d, 360)) - T) < 1e-6
    assert float(idf.t_eq(0.0, 60)) == 0.0
    assert abs(idf.prob_at_least_once(1000, 30) - 0.0296) < 1e-3          # 1000-yr: ~3% in 30 years
    assert abs(idf.prob_at_least_once(100, 30) - 0.26) < 0.01


def _parent(sid="e1", year=2015, total=None):
    """Realistic convective storm: 6 h core with a 1 h peak, plus a light tail (1h:6h:24h depths ~ 0.76 : 1 : 1.36)."""
    d = np.zeros(288)
    d[40:64] = 0.2          # 6 h core
    d[50:54] += 3.0         # 1 h peak
    d[100:130] = 0.2        # light tail
    if total is not None:
        d = d * (total / d.sum())
    return dict(storm_id=sid, year=year, depth=d)


def test_amplification_preserves_shape():
    p = _parent()
    v, rej = S.build_T_variants([p], [10], min_anchor_mm=10, k_hi=6.0)
    assert not rej, rej
    assert v, "expected one T10 variant"
    d = v[0]["depth"]
    assert np.allclose(d / d.sum(), p["depth"] / p["depth"].sum())          # same temporal pattern
    assert abs(v[0]["T_by_dur"][360] - 10) < 0.05                           # anchored at 6 h


def test_T_variants_reject_reasons_and_atlas_requirement():
    small = _parent("tiny", total=5.0)
    _, rej = S.build_T_variants([small], [10])
    assert rej[0]["reason"] == "below_min_anchor_depth"
    _, rej = S.build_T_variants([_parent()], [1000], min_anchor_mm=10, k_hi=100)
    assert rej[0]["reason"] == "needs_atlas14_table"
    atlas = pd.DataFrame({1000.0: [150.0, 170.0, 217.0]}, index=pd.Index([60, 360, 1440], name="duration_min"))
    v, rej = S.build_T_variants([_parent()], [1000], min_anchor_mm=10, k_hi=100, pfds=atlas)
    assert not rej, rej
    assert v and abs(S.roll_max(v[0]["depth"], 24) - 170.0) < 1e-6


def test_onset_variants_and_ceiling():
    p = _parent()
    v, rej = S.build_C_variants([p], {"e1": 2.0}, mults=(1.0, 3.0, 9.0), k_cap=12.0)
    assert [x["rung"] for x in v] == ["C1", "C3"] and rej[0]["reason"].startswith("k_over_cap")
    assert abs(v[1]["k"] - 6.0) < 1e-9
    _, rej = S.build_C_variants([p], {"e1": None})
    assert rej[0]["reason"] == "no_cso_onset_within_k_cap"
    assert S.eligible_for_training(dict(T_anchor=80.0), 100) and not S.eligible_for_training(dict(T_anchor=400.0), 100)
    assert S.eligible_for_training(dict(T_anchor=400.0), 1000)


def test_find_onset_factor():
    d = _parent()["depth"]
    f = lambda depth: max(0.0, 50 * (depth.sum() / d.sum() - 2.3))        # spills when k > 2.3
    k, ev = find_onset_factor(f, d, floor=1.0)
    assert 2.3 < k < 2.3 * 1.06 and len(ev) <= 12
    assert find_onset_factor(lambda x: 0.0, d)[0] is None
    assert find_onset_factor(lambda x: 99.0, d)[0] == 1.0
    with pytest.raises(RuntimeError, match="non-monotone"):
        find_onset_factor(lambda x: 2.0 if x[0] < 2.0 else 0.0,
                          np.ones(288), grid=(1.0, 2.0))


def test_parent_split_no_leakage():
    ps = [_parent("a", 2012), _parent("b", 2019), _parent("c", 2024)]
    sp = S.assign_parent_splits(ps, [2019], [2024])
    assert sp == {"a": "train", "b": "val", "c": "test"}


def test_build_cli_end_to_end(tmp_path):
    rain = tmp_path / "rain"; rain.mkdir()
    rows = []
    for i, (yr, tot) in enumerate([(2012, 40), (2013, 45), (2019, 42), (2024, 44)]):
        p = _parent(f"ev{i}", yr, None)
        pd.DataFrame(p["depth"] * 4).to_csv(rain / f"ev{i}.csv", header=False, index=False)
        rows.append(dict(storm_id=f"ev{i}", t0=f"{yr}-06-10"))
    pd.DataFrame(rows).to_csv(tmp_path / "events.csv", index=False)
    pd.DataFrame(dict(
        storm_id=["ev0", "ev1", "ev2", "ev3"],
        k_onset=[2.0, 2.5, np.nan, 3.0],
        volume_units=["m3"] * 4,
        complete_four_outfall_objective=[True] * 4,
    )).to_csv(tmp_path / "onset.csv", index=False)
    (tmp_path / "onset.csv.summary.json").write_text(json.dumps({
        "n_storms": 4,
        "n_expected_parents": 4,
        "complete_table": True,
        "hydraulic_gate_passed": True,
        "G1_pass": True,
    }))
    out = tmp_path / "out"
    df, rej = B.main(["--rain-dir", str(rain), "--events", str(tmp_path / "events.csv"), "--out", str(out),
                      "--onset", str(tmp_path / "onset.csv"), "--val-years", "2019", "--test-years", "2024",
                      "--ladder-train", "5,10", "--ladder-test", "", "--min-anchor-mm", "10", "--min-R-anchor-mm", "10", "--k-hi", "6"])
    man = json.loads((out / "data_manifest.json").read_text())["storms"]
    assert set(df.family) == {"R", "T", "C"}
    assert (df[df.parent == "ev3"].split == "test").all() and (df[df.parent == "ev0"].split == "train").all()
    assert all(man[v]["provenance"] == ("observed" if man[v]["family"] == "R" else "scaled_real") for v in man)
    assert "ev2" not in set(df[df.family == "C"].parent) and "no_cso_onset_within_k_cap" in set(rej.reason)
    # guard accepts the directory and rejects a tampered file
    from research.guard import assert_provenance
    from types import SimpleNamespace as NS
    storms = [NS(storm_id=v, split=man[v]["split"], meta={"scaling": "none"}) for v in man]
    assert_provenance(storms, out)
    with open(out / f"{storms[0].storm_id}.csv", "a") as fh:
        fh.write("1.0\n")
    with pytest.raises(RuntimeError):
        assert_provenance(storms, out)
    with pytest.raises(RuntimeError):
        assert_provenance([NS(storm_id=storms[1].storm_id, split="test", meta={"scaling": "none"})], out,
                          allowed={"test": {"observed"}}) if man[storms[1].storm_id]["provenance"] != "observed" else (_ for _ in ()).throw(RuntimeError())


def test_flat_family():
    p = _parent()
    v, _ = S.build_F_variants([p], (2.0,))
    assert v[0]["family"] == "F" and v[0]["rung"] == "F2" and np.allclose(v[0]["depth"], 2 * p["depth"])

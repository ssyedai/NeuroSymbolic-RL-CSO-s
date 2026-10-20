import numpy as np
from multistorm.stl import storage_metrics, rho_storage_first, rho_flood_free
from multistorm import metrics_v8 as M
from multistorm.samplers import StratifiedSampler
from multistorm.replay import RingReplay
from multistorm.obsfeat import rain_features, RAIN_SCALES


def L(cso, fill, flood=None):
    n = len(cso)
    return dict(cso_flow=np.array(cso, float), store_fill_ratio=np.array(fill, float),
                flooding=np.zeros(n) if flood is None else np.array(flood, float))


def test_storage_first_semantics():
    ok = L([0, 0, 5, 5], [0.2, 0.9, 0.97, 1.0])                  # spills only when storage full
    bad = L([0, 5, 5, 0], [0.2, 0.4, 0.5, 0.6])                  # spills with headroom
    assert storage_metrics(ok)["sat_storage_first"] and storage_metrics(ok)["store_first_viol_steps"] == 0
    m = storage_metrics(bad)
    assert not m["sat_storage_first"] and m["store_first_viol_steps"] == 2 and m["store_first_viol_rate"] == 1.0
    assert abs(m["suo_onset"] - 0.4) < 1e-12
    assert np.isnan(storage_metrics(L([0, 0], [0.1, 0.2]))["suo_onset"])
    assert not storage_metrics(L([0, 0], [0.1, 0.2], flood=[0, 3.0]))["sat_flood_free"]
    assert rho_flood_free([0, 0]) > 0 and rho_storage_first([0, 0], [0, 0]) > 0


def test_flood_nonregression_and_hindsight():
    ref = dict(cso_total=1000.0, flood_total=0.0)
    hind = dict(cso_total=600.0, flood_total=0.0)
    s = dict(cso_total=800.0, flood_total=0.0)
    e = M.enrich(s, ref, hind)
    assert e["flood_nonregress"] and e["flood_zero_when_feasible"] and e["scorecard_pass"]
    assert abs(e["pct_achievable_captured"] - 50.0) < 1e-9 and abs(e["regret_vs_hindsight"] - 200.0) < 1e-9
    worse = M.enrich(dict(cso_total=700.0, flood_total=500.0), ref, hind)
    assert not worse["flood_nonregress"] and not worse["flood_zero_when_feasible"] and not worse["scorecard_pass"]
    refw = dict(cso_total=1000.0, flood_total=900.0)               # reference floods: tolerance applies
    assert M.flood_nonregression(dict(flood_total=900.0), refw)["flood_nonregress"]
    assert np.isnan(M.vs_hindsight(s, ref, dict(cso_total=999.5))["pct_achievable_captured"])
    assert M.vs_hindsight(s, ref, None) == {}


def test_stratified_sampler_balance_and_state():
    storms = [dict(id=f"a{i}", meta=dict(rung="T10")) for i in range(5)] + \
             [dict(id=f"b{i}", meta=dict(rung="C2")) for i in range(2)] + [dict(id="r0", meta=dict(rung="R"))]
    sp = StratifiedSampler(storms, seed=0)
    for _ in range(3000):
        sp.next()
    c = np.array(list(sp.counts.values())); assert c.min() > 900 and c.max() < 1100        # rungs ~equal
    st = sp.state_dict(); a = [sp.next()["id"] for _ in range(20)]
    sp.load_state_dict(st); b = [sp.next()["id"] for _ in range(20)]
    assert a == b


def test_ring_replay_wraps():
    r = RingReplay(5, 3, 2)
    for i in range(8):
        r.push(np.full(3, i), np.full(2, i), float(i), 0.5, np.full(3, i + 1), 0.0)
    assert len(r) == 5 and set(r.o[:, 0]) == {3, 4, 5, 6, 7}
    o, a, rew, c, no, d = r.sample(16)
    assert o.shape == (16, 3) and rew.shape == (16, 1) and (no[:, 0] == o[:, 0] + 1).all()


def test_rain_features_causal():
    r = np.zeros(288); r[10:14] = 2.0
    assert (rain_features(r, 0) == 0).all()
    assert rain_features(r, 10).sum() == 0                          # nothing fallen yet in first 10 intervals
    f = rain_features(r, 12) * RAIN_SCALES
    assert abs(f[0] - 2.0) < 1e-5 and abs(f[1] - 4.0) < 1e-5 and abs(f[5] - 0.5) < 1e-5   # now, 1h, hours since start
    assert np.allclose(rain_features(r, 12), rain_features(np.r_[r[:12], np.full(276, 99.0)], 12))   # no look-ahead

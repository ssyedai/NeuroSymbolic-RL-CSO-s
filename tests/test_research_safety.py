import numpy as np
import pandas as pd
import pytest

from multistorm.metrics_v8 import enrich, aggregate_native
from multistorm.safety_selection import validation_selection


def row(**kw):
    return dict(split="val", rung="T10", cso_reduction_vs_native_pct=20.0,
                flood_nonregress=True, flood_zero_when_feasible=True,
                intervention_rate=0.1, **kw)


def test_zero_reference_events_are_not_removed_from_safety():
    safe = row()
    unsafe = {**safe, "cso_reduction_vs_native_pct": np.nan,
              "flood_nonregress": False, "flood_zero_when_feasible": False}
    d = pd.DataFrame([safe, unsafe])
    assert validation_selection(d) == -80
    assert validation_selection(d, strict=True) == -np.inf


def test_missing_safety_and_test_split_cannot_select():
    d = pd.DataFrame([row()])
    assert validation_selection(d, strict=True) == 20
    assert validation_selection(d.drop(columns="flood_nonregress")) == -np.inf
    with pytest.raises(ValueError, match="validation"):
        validation_selection(d.assign(split="test"))
    assert validation_selection(d.assign(intervention_rate=np.nan)) == -80


def test_native_reference_and_sampled_units():
    e = enrich(dict(cso_total=80, flood_total=2), dict(cso_total=100, flood_total=1))
    assert e["cso_reduction_pct"] == 20
    assert e["flood_ratio"] == 2
    assert e["native_cso"] == 100
    assert e["flood_vol_m3_sampled"] == pytest.approx(2 * 900 * 0.028316846592)
    assert not e["overflow_accounting_complete"]
    zero = enrich(dict(cso_total=20, flood_total=15), dict(cso_total=0, flood_total=0))
    a = aggregate_native(pd.DataFrame([{**e, "cso_total": 80}, {**zero, "cso_total": 20}]))
    assert a["cso_red_micro"] == 0  # additional CSO on a dry-reference event counts
    assert a["flood_nonregress_rate"] == 0.5
    assert a["reference_control"] == "native"


def test_zero_when_feasible_is_required_by_scorecard():
    # Relative tolerance alone permits 20.2; zero-when-feasible permits only 10.
    e = enrich(dict(cso_total=0, flood_total=15), dict(cso_total=10, flood_total=10))
    assert e["flood_nonregress"] and not e["flood_zero_when_feasible"]
    assert not e["scorecard_pass"]


def test_evaluation_uses_native_and_resets_schedule():
    from types import SimpleNamespace
    from multistorm.evaluate import evaluate
    from tests.test_metrics import _fake_log
    from multistorm.metrics import episode_summary

    log = _fake_log(T=2, cso=25, flood=0)
    log["store_fill_ratio"] = np.ones(2)
    static = episode_summary(_fake_log(T=2, cso=10, flood=0))
    native = episode_summary(_fake_log(T=2, cso=50, flood=0))
    rec = dict(static=static, native=native, baseline_flooding=0)
    env = SimpleNamespace(
        kb=SimpleNamespace(set_reference=lambda x: None), physical_rain=True,
        reset=lambda options: (np.zeros(1), {}),
        step=lambda a: (np.zeros(1), 0, False, True, {}),
        get_episode_log=lambda: log,
    )
    class Policy:
        resets = 0
        def reset(self):
            self.resets += 1
        def select_action(self, obs, deterministic):
            return np.ones(7)
    policy = Policy()
    storm = SimpleNamespace(storm_id="p__T5", split="val", depth=np.zeros(288),
                            meta=dict(parent="p", family="T", rung="T5"))
    df = evaluate(policy, env, [storm, storm], SimpleNamespace(get=lambda s: rec), "val",
                  hind_table={"p": dict(cso_total=0, flood_total=0)})
    assert policy.resets == 2
    assert (df.cso_reduction_pct == 50).all()  # static would be -150%
    assert "regret_vs_hindsight" not in df  # do not borrow another storm's result
    assert aggregate_native(df)["cso_red_micro"] == 50


def test_training_flags_do_not_enable_test_evaluation_implicitly():
    from multistorm.config import parse_args
    cfg = parse_args([])
    assert not cfg.evaluate_test and not cfg.strict_safety_selection
    cfg = parse_args(["--strict-safety-selection", "--evaluate-test"])
    assert cfg.evaluate_test and cfg.strict_safety_selection

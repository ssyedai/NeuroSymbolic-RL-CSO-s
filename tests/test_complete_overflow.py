import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from multistorm.complete_overflow import storage_capacities, CompleteOverflowKB
from multistorm.metrics_v8 import enrich
from multistorm.safety_selection import validation_selection
from multistorm.storms import load_storms


def test_storage_capacity_integrates_area_and_spill_crest(tmp_path):
    inp = tmp_path / "storage.inp"
    inp.write_text("[STORAGE]\nS 0 4 0 TABULAR C\n[CURVES]\nC STORAGE 0 2\nC 2 6\nC 3 6\n[WEIRS]\nW S O TRANSVERSE 1\n")
    physical, usable = storage_capacities(inp)
    assert physical["S"] == pytest.approx(20)
    assert usable["S"] == pytest.approx(3)


def test_bypass_rule_has_auditable_flood_exception():
    topo = {g: dict(risk_up=["up"], storage_down=[], weirs_down=[]) for g in range(7)}
    kb = CompleteOverflowKB({"up": 10}, ["up"], topo)
    obs = dict(node_depths={"up": 1}, flooding=0, cso_flow=0)
    action = kb.project_action(np.full(7, 0.3), obs)
    assert np.all(action[3:5] == 0)
    assert len([r for r in kb.last_info["explanations"] if r["rule"] == "BYPASS_CLOSE"]) == 2
    action = kb.project_action(np.full(7, 0.3), {**obs, "node_depths": {"up": 9.5}})
    assert np.all(action[3:5] >= 0.5)


def test_complete_score_rejects_increased_total_overflow():
    ref = dict(volume_units="m3", cso_total=100, flood_total=0, total_overflow_vol_m3=100)
    s = dict(volume_units="m3", cso_total=99, flood_total=9, total_overflow_vol_m3=108,
             overflow_accounting_complete=True)
    metrics = enrich(s, ref)
    assert metrics["flood_nonregress"] and not metrics["scorecard_pass"]
    d = pd.DataFrame([{**metrics, "split": "val", "intervention_rate": 0.1}])
    assert validation_selection(d, strict=True) == -np.inf
    with pytest.raises(ValueError, match="units"):
        enrich(s, {**ref, "volume_units": None})


def test_selective_loader_does_not_open_test_rainfall(tmp_path):
    (tmp_path / "data_manifest.json").write_text(json.dumps({"storms": {"train": {}, "test": {}}}))
    (tmp_path / "train.csv").write_text("1\n" * 288)
    (tmp_path / "test.csv").write_text("malformed,test,file\n")
    storms = load_storms(tmp_path, "none", storm_ids=["train"])
    assert [s.storm_id for s in storms] == ["train"]


def test_safety_first_search_cannot_trade_flooding_for_cso():
    from research.controllability import safety_objective, static_search
    from research.optimize_rules import score
    ref = dict(volume_units="m3", cso_total=10000, flood_total=0, total_overflow_vol_m3=10000)
    unsafe = {**ref, "cso_total": 0, "flood_total": 11, "total_overflow_vol_m3": 11}
    safe = {**ref, "cso_total": 9900, "total_overflow_vol_m3": 9900}
    assert safety_objective(safe, ref) < safety_objective(unsafe, ref)
    def evaluate(policy, storm, projection):
        return safe if policy.p[0, 0] == 0.5 else unsafe
    best = static_search(evaluate, None, ref, n=2, safety_first=True)
    assert best[2] is safe
    result = score({}, list(range(100)), lambda t, i: (unsafe if i == 99 else safe, ref), safety_first=True)
    assert result > 3  # even 1 unsafe event in 100 cannot be averaged away


def test_complete_native_episode_accounts_for_full_horizon_and_cleans_files():
    from multistorm import adapters as A
    from research.guard import assert_provenance
    root = Path("data/useful/rain_scenarios")
    if not root.exists():
        pytest.skip("Local research rainfall required")
    storm = load_storms(root, "none", storm_ids=["USC00200230_20100719__T10"])[0]
    assert_provenance([storm], root)
    env, _, _ = A.build_v8(0, complete_overflow=True)
    try:
        env.reset(options=dict(storm=storm, physical_rain=True, native=True))
        generated = Path(env.input_file)
        done = False
        while not done:
            _, _, term, trunc, _ = env.step(np.full(7, 0.5))
            done = term or trunc
        log = env.get_episode_log()
        s = log["accounting_summary"]
        assert s["simulated_steps"] == len(log["cso_flow"]) == 288
        assert s["cso_total"] > 0 and s["flood_total"] > 0
        assert s["cso_total"] == pytest.approx(sum(log["cso_flow"]) * 900 * 0.028316846592)
        assert s["flood_total"] == pytest.approx(sum(log["flooding"]) * 900 * 0.028316846592)
        assert np.isfinite(s["routing_error_pct"])
        assert s["boundary_reverse_inflow_vol_m3"] > 0
        assert s["cumulative_outfall_inflow_vol_m3"] == pytest.approx(s["system_outflow_vol_m3"] + s["boundary_reverse_inflow_vol_m3"])
        assert s["cso_total"] + s["treated_outfall_vol_m3"] == pytest.approx(s["system_outflow_vol_m3"], abs=1e-7)
        assert not generated.exists() and not generated.with_suffix(".out").exists()
        env.reset(options=dict(storm=storm, physical_rain=True, native=False, use_projection=False))
        assert "RULE FIRSTFLUSH" not in Path(env.input_file).read_text().upper()
        assert "RULE FIRSTFLUSH" in Path("7MPF_CSO_08.inp").read_text().upper()
        command = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4])
        for _ in range(4):
            env.step(command)
        assert np.allclose(env.get_episode_log()["actions_actual"][:, :7], command)
        # The seven-dimensional policy owns gates only. Pump operation remains
        # under the INP's safety/treatment interlocks and is not forced ON.
        assert env.get_episode_log()["accounting_summary"]["pump_control"] == "INP native"
        assert np.all(np.isfinite(env.get_episode_log()["actions_actual"][:, 7:]))
        env.reset(options=dict(storm=storm, physical_rain=True, native=True))
        assert "RULE FIRSTFLUSH" in Path(env.input_file).read_text().upper()
        env.native_pumps = True
        env.reset(options=dict(storm=storm, physical_rain=True, native=False, use_projection=False))
        text = Path(env.input_file).read_text().upper()
        assert "RULE PUMP27A" in text and "RULE FIRSTFLUSH" not in text
        env.step(command)
        log = env.get_episode_log()
        assert np.allclose(log["actions_target"][:, :7], command)
        assert log["accounting_summary"]["pump_control"] == "INP native"
    finally:
        env.close()

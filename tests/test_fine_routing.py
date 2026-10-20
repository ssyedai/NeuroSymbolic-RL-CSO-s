import pytest
from research.fine_routing import patch_options, summarize


def test_subsecond_profile_preserves_controller_and_other_sections():
    text = "[OPTIONS]\nROUTING_STEP 00:00:10\nMINIMUM_STEP 0.5\nRULE_STEP 00:00:00\n[CONTROLS]\nRULE X\n; ROUTING_STEP preserve\n"
    result = patch_options(text, 0.25)
    assert "ROUTING_STEP 0.25" in result
    assert "MINIMUM_STEP 0.25" in result
    assert "RULE_STEP 00:00:00" in result
    assert result.split("[CONTROLS]")[1] == text.split("[CONTROLS]")[1]
    assert "RULE_STEP 00:00:01" in patch_options(text, 0.5, 1)
    with pytest.raises(ValueError, match="MINIMUM_STEP"):
        patch_options(text.replace("MINIMUM_STEP", "MISSING"), 0.25)
    with pytest.raises(ValueError, match="MAX_TRIALS"):
        patch_options(text, 0.25, tight_solver=True)
    slot = patch_options(text, .25, surcharge_method="SLOT")
    assert "SURCHARGE_METHOD SLOT\n[CONTROLS]" in slot
    assert slot.split("[CONTROLS]")[1] == text.split("[CONTROLS]")[1]
    assert patch_options(slot, .5, surcharge_method="EXTRAN").count("SURCHARGE_METHOD") == 1
    assert "SURCHARGE_METHOD" not in patch_options(text, .5)


def test_convergence_cannot_hide_flood_sensitivity_or_incomplete_cases():
    cfg = dict(expected_runs=3, routing_seconds=[1, 0.5, 0.25])
    rows = [dict(storm_id="train", case="native", routing_seconds=dt,
                 cso_total=100, flood_total=flood, total_overflow_vol_m3=100+flood,
                 routing_error_pct=0.1) for dt, flood in [(1, 3), (0.5, 0), (0.25, 0)]]
    assert not summarize(rows[:2], cfg)["complete"]
    assert not summarize(rows, cfg)["passed"]
    rows[0].update(flood_total=0, total_overflow_vol_m3=100)
    assert summarize(rows, cfg)["passed"]


def test_convergence_rejects_missing_continuity_and_duplicate_runs():
    cfg = dict(expected_runs=2, routing_seconds=[1, .5])
    rows = [dict(storm_id="train", case="native", routing_seconds=dt,
                 cso_total=100, flood_total=0, total_overflow_vol_m3=100,
                 routing_error_pct=error) for dt, error in [(1, 0.1), (.5, float("nan"))]]
    assert not summarize(rows, cfg)["passed"]
    with pytest.raises(ValueError, match="Duplicate"):
        summarize([rows[0], rows[0]], cfg)


def test_explicit_accuracy_overrides_are_bounded_and_preserve_rules():
    text = "[OPTIONS]\nROUTING_STEP 10\nMINIMUM_STEP 0.5\nMAX_TRIALS 8\nHEAD_TOLERANCE 0.005\n[CONTROLS]\nRULE untouched\n"
    result = patch_options(text, .25, tight_solver=True, max_trials=100, head_tolerance=1e-7)
    assert "MAX_TRIALS 100" in result
    assert "HEAD_TOLERANCE 0.0000001000" in result
    assert result.split("[CONTROLS]")[1] == text.split("[CONTROLS]")[1]
    for tolerance in (0, float("nan"), .1):
        with pytest.raises(ValueError):
            patch_options(text, .25, head_tolerance=tolerance)
    with pytest.raises(ValueError):
        patch_options(text, .25, max_trials=201)


def test_tight_profile_allows_an_explicit_bounded_iteration_ablation():
    text = "[OPTIONS]\nROUTING_STEP 10\nMINIMUM_STEP 0.5\nMAX_TRIALS 8\nHEAD_TOLERANCE 0.005\n"
    result = patch_options(text, .5, tight_solver=True, max_trials=200)
    assert "MAX_TRIALS 200" in result
    assert "HEAD_TOLERANCE 0.0001" in result

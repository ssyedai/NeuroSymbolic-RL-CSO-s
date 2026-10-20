import pytest
from research.weir_reproduction import CREST, INFLOW, TAIL, discharge, equilibrium, model_text


def test_equilibrium_satisfies_independent_free_weir_solution_and_submerged_balance():
    free = CREST + (INFLOW / 285)**(2/3)
    assert equilibrium(604) == pytest.approx(free, abs=1e-10)
    head = equilibrium()
    assert TAIL < head < CREST+10
    assert discharge(head) == pytest.approx(INFLOW, abs=1e-6)
    assert discharge(TAIL) == 0
    assert discharge(TAIL-1) == 0
    with pytest.raises(ValueError):
        equilibrium(inflow=1e6)


def test_isolated_model_has_no_rain_or_controller_and_explicit_equilibrium_state():
    text = model_text(.25, "SLOT", 100, 1e-7, TAIL)
    assert "[RAINGAGES]" not in text
    assert "[CONTROLS]" not in text
    assert "ROUTING_STEP 0.25" in text
    assert "HEAD_TOLERANCE 0.0000001000" in text
    assert "S FLOW \"\" FLOW 1 1 65.0" in text

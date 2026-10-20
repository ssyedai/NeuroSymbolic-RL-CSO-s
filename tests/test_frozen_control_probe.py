import pytest

from research.frozen_control_probe import freeze_controls


def test_freeze_controls_removes_only_control_body():
    model = """[OPTIONS]
FLOW_UNITS CFS
[CONTROLS]
RULE A
IF NODE N1 DEPTH > 1
THEN ORIFICE O1 SETTING = 0
[REPORT]
INPUT YES
"""
    frozen = freeze_controls(model)
    assert "RULE A" not in frozen
    assert "[OPTIONS]" in frozen
    assert "[REPORT]" in frozen
    assert "intentionally empty" in frozen


def test_freeze_controls_requires_rules():
    with pytest.raises(ValueError, match="does not contain native rules"):
        freeze_controls("[CONTROLS]\n; empty\n[REPORT]\n")

import pandas as pd
import pytest
from research.report_flow_guard import validate_pair


def frame():
    return pd.DataFrame([dict(case="a", input_sha256="same", max_late_flow_error_cfs=.01,
                             outflow_error_pct=.1, routing_error_pct=.1, flooding_ft3=0)]).set_index("case")


def test_comparison_rejects_changed_inputs_and_missing_or_duplicate_cases():
    base = frame()
    validate_pair(base, base.copy())
    changed = base.copy()
    changed.loc["a", "input_sha256"] = "changed"
    with pytest.raises(ValueError, match="inputs"):
        validate_pair(base, changed)
    with pytest.raises(ValueError, match="Unmatched"):
        validate_pair(base, base.iloc[:0])
    with pytest.raises(ValueError, match="Duplicate"):
        validate_pair(base, pd.concat([base, base]))


def test_comparison_rejects_missing_safety_measurement():
    candidate = frame()
    candidate.loc["a", "flooding_ft3"] = float("nan")
    with pytest.raises(ValueError, match="Non-finite"):
        validate_pair(frame(), candidate)

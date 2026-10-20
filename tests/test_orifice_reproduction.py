import math

import numpy as np
import pandas as pd
import pytest

from research.orifice_reproduction import orifice_head, TAIL
from research.report_orifice_verification import validate_results


def test_orifice_reference_balances_flow_above_cutoff():
    for flow in (5, 65):
        assert .4*7*14.14*math.sqrt(64.4*(orifice_head(flow)-TAIL)) == pytest.approx(flow)
    for flow in (0, -1, .1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            orifice_head(flow)


def test_verification_rejects_missing_nonfinite_and_false_pass():
    rows = [dict(case=f"{node}_{method}_{flow}_{step:g}", inflow_cfs=flow,
                 max_late_flow_error_cfs=0., volume_error_pct=0., routing_error_pct=0.,
                 flooding_ft3=0., late_flow_range_cfs=0., verified=True)
            for node in ("junction", "storage") for method in ("SLOT", "EXTRAN")
            for flow in (5, 65) for step in (1, .5, .25)]
    frame = pd.DataFrame(rows).set_index("case")
    assert validate_results(frame).all()
    with pytest.raises(ValueError):
        validate_results(frame.iloc[1:])
    for value in (np.nan, 1.):
        altered = frame.copy()
        altered.iloc[0, altered.columns.get_loc("max_late_flow_error_cfs")] = value
        with pytest.raises(ValueError):
            validate_results(altered)

import numpy as np
import pandas as pd
import pytest

from research.reversing_orifice import CUTOFF, TAIL, boundary_points, reference_flow, reversing_model, summarize


def test_cutoff_reference_is_zero_inside_and_odd_outside():
    gaps = np.array([-.001, -.00010001, -CUTOFF, 0, CUTOFF, .00010001, .001])
    q = reference_flow(gaps)
    assert np.array_equal(q[2:5], [0, 0, 0])
    assert q == pytest.approx(-q[::-1])
    assert q[-1] == pytest.approx(.4*98.98*np.sqrt(64.4*.001))
    assert q[-2] > 3  # A finite jump at the cutoff, not a smooth zero crossing.
    with pytest.raises(ValueError):
        reference_flow(np.nan)


def test_reversing_model_preserves_gate_and_removes_flap_and_inflow():
    text = reversing_model(.25, "junction", .001)
    assert "[CONTROLS]" not in text and "[INFLOWS]" not in text
    assert "[RAINGAGES]" not in text
    assert "O 602.797 TIMESERIES STAGE NO" in text
    assert "W S O SIDE 0 0.4 NO 0.117" in text
    assert "W RECT_CLOSED 7 14.14 0 0" in text
    points = np.array(boundary_points(.001))
    assert points[0, 0] == 0 and points[-1, 0] == 600
    assert points[:, 1].max()-TAIL == pytest.approx(.001)
    assert TAIL-points[:, 1].min() == pytest.approx(.001)


def test_quiescent_balance_and_fail_closed_trace_checks():
    points = np.array(boundary_points(.00005))
    times = np.arange(1, 601, dtype=float)
    frame = pd.DataFrame(dict(seconds=times, storage_head_ft=TAIL,
        outfall_head_ft=np.interp(times, *points.T), flow_cfs=0., volume_ft3=100.))
    totals = {"system_"+k:0. for k in ("dwInflow", "wwInflow", "gwInflow", "iiInflow",
        "exInflow", "outflow", "flooding", "evapLoss", "seepLoss")}
    totals.update(system_initStorage=100., system_finalStorage=100., routing_error_pct=0., flooding_ft3=0.)
    assert summarize(frame, totals, .00005)["verified"]
    altered = frame.copy()
    altered.loc[100, "outfall_head_ft"] += .01
    with pytest.raises(ValueError, match="Boundary"):
        summarize(altered, totals, .00005)
    totals["system_finalStorage"] += .02
    assert not summarize(frame, totals, .00005)["balance_pass"]
    with pytest.raises(ValueError):
        summarize(frame.iloc[:-3], totals, .00005)

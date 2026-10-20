import pandas as pd
import pytest
from research.report_transition_trace import analyze


def test_head_convergence_does_not_hide_final_flow_mismatch():
    trace=pd.DataFrame(dict(seconds=[1.,1.],iteration=[0,1],computed=[1,1],
        pre_head_s=[616.,616.],pre_head_o=[616.,616.],new_depth=[14.708,14.708],
        q_raw=[0.,0.],q_used=[1.,.5],combined_converged=[1,1],
        orifice_area=[.02,.02],node_effective_area=[12.566,12.566]))
    samples=pd.DataFrame(dict(seconds=[1.],outfall_head_ft=[616.]))
    _,_,summary=analyze(trace,samples)
    assert summary['declared_converged_steps']==1
    assert summary['max_residual_at_declared_convergence_cfs']==pytest.approx(.5)
    trace.loc[1,'iteration']=2
    with pytest.raises(ValueError,match='Missing'):
        analyze(trace,samples)

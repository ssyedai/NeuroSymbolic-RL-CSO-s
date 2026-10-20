import math
import pytest
from research.cutoff_root import classify, COEFFICIENT, CUTOFF
from research.continuous_orifice_probe import continuous_flow


def test_cutoff_branches_have_an_open_flow_limit_and_missing_root_interval():
    alpha=.001
    limit=CUTOFF+alpha*COEFFICIENT*math.sqrt(CUTOFF)
    for sign in (-1,1):
        assert classify(sign*CUTOFF,alpha)=='zero_branch'
        assert classify(sign*(CUTOFF+limit)/2,alpha)=='no_exact_root'
        assert classify(sign*limit,alpha)=='no_exact_root'
        assert classify(sign*(limit+1e-5),alpha)=='flowing_branch'
    with pytest.raises(ValueError):
        classify(0,0)


def test_alternative_law_is_odd_continuous_and_retains_large_head_flow():
    assert continuous_flow(0)==0
    for gap in (CUTOFF/2,CUTOFF,CUTOFF*2):
        assert continuous_flow(-gap)==pytest.approx(-continuous_flow(gap))
    assert continuous_flow(CUTOFF*(1-1e-9))==pytest.approx(continuous_flow(CUTOFF*(1+1e-9)),rel=2e-9)
    assert continuous_flow(.001)==pytest.approx(COEFFICIENT*math.sqrt(.001))
    assert continuous_flow(CUTOFF/2)==pytest.approx(.5*COEFFICIENT*math.sqrt(CUTOFF))

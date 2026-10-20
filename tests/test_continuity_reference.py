import math
import pytest
from research.verify_continuity_probe import continuous_root
from research.cutoff_root import COEFFICIENT, CUTOFF


def test_closed_form_solution_satisfies_each_monotone_branch():
    for alpha in (.00000001,.001,1.):
        for b in (-10.,-.001,-.00001,0.,.00001,.001,10.):
            g=continuous_root(b,alpha)
            q=COEFFICIENT*(g/math.sqrt(CUTOFF) if abs(g)<=CUTOFF else math.copysign(math.sqrt(abs(g)),g))
            assert g+alpha*q==pytest.approx(b,abs=1e-12)
    with pytest.raises(ValueError):
        continuous_root(0,0)

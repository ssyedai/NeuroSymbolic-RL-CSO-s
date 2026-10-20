import numpy as np
from research.coupled_balance_probe import coupled_step, AREAS, INCIDENCE
from research.continuous_orifice_probe import continuous_flow


def test_independent_coupled_balance_conserves_volume_and_satisfies_all_nodes():
    for gap in (.00005,.001,-.001):
        old=np.array([0.,-gap,.5*gap])
        q=np.zeros(2)
        volume=AREAS @ old
        for _ in range(20):
            new,new_q=coupled_step(old,q,.25)
            residual=AREAS*(new-old)-.125*(INCIDENCE @ (q+new_q))
            assert np.max(abs(residual))<=1e-9
            assert abs(AREAS @ new-volume)<1e-8
            assert np.allclose(new_q,continuous_flow(-INCIDENCE.T @ new))
            old,q=new,new_q


def test_equal_heads_remain_quiescent():
    old=np.ones(3)*.001
    h,q=coupled_step(old,np.zeros(2),1.)
    assert np.array_equal(h,old)
    assert np.array_equal(q,np.zeros(2))


def test_forced_balance_retains_known_added_volume():
    old=np.array([0.,-.00005,.000025])
    h,q=coupled_step(old,np.zeros(2),.25,0.,.2)
    assert abs(AREAS @ (h-old)-.025)<1e-9

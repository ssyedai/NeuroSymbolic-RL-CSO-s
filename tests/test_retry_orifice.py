import pytest
from research.retry_orifice import acceptable, retry


class FakeSession:
    def __init__(self, fail_below=False, corrupt=False):
        self.time=0.
        self.restarts=0
        self.fail_below=fail_below
        self.corrupt=corrupt

    def restart(self):
        self.time=0.
        self.restarts+=1

    def step(self,dt):
        self.time+=dt
        bad=self.time>.25 and (self.fail_below or dt>.125)
        return dict(seconds=self.time,head_s=616.,head_o=616.,flow=0.,
                    residual=1. if bad else 0.,converged=0 if bad else 1,
                    system_outflow=self.time+(1 if self.corrupt and self.restarts else 0))


def test_retry_discards_failed_state_and_exactly_replays_accepted_prefix():
    result=retry(FakeSession(),horizon=.5,minimum=.125)
    assert result['status']=='complete'
    assert result['rejected_steps']==1
    assert result['accepted_steps']==3
    assert result['final_accepted_state']['system_outflow']==.5


def test_floor_failure_restores_last_accepted_state_and_corruption_fails():
    session=FakeSession(fail_below=True)
    result=retry(session,horizon=.5,minimum=.125)
    assert result['status']=='minimum_step_failed'
    assert result['accepted_time_s']==session.time==.25
    assert result['rejected_steps']==2
    with pytest.raises(ValueError,match='exactly restore'):
        retry(FakeSession(corrupt=True),horizon=.5,minimum=.125)


def test_acceptance_requires_convergence_and_finite_final_flow_consistency():
    state=dict(head_s=616.,head_o=616.,flow=0.,residual=0.,converged=1)
    assert acceptable(state)
    for key,value in [('converged',0),('residual',.051),('flow',float('nan'))]:
        assert not acceptable({**state,key:value})

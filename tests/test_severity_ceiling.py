from types import SimpleNamespace
import pytest
from multistorm.diet import within_training_ceiling,eligible_for_training


def test_declared_extreme_cannot_hide_behind_lower_fitted_severity():
    meta=dict(family='T',rung='T200',T_anchor=80.,T_target=200.)
    assert not within_training_ceiling(meta,100)
    assert within_training_ceiling(meta,1000)
    assert not within_training_ceiling(dict(family='T',rung='T10',T_anchor=200.),100)


def test_invalid_severity_fails_closed_and_legacy_is_preserved():
    assert within_training_ceiling({},100)
    assert not within_training_ceiling({'T_anchor':float('nan')},100)
    assert not within_training_ceiling({'family':'R'},100)
    assert within_training_ceiling({'family':'R','T_anchor':0.5},100)
    assert not within_training_ceiling({'family':'T','rung':'Tbad'},100)
    with pytest.raises(ValueError):within_training_ceiling({},float('nan'))


def test_test_only_training_override_is_limited_to_d3():
    s=SimpleNamespace(split='train',storm_id='p__T200',meta=dict(family='T',rung='T200',T_anchor=80.,test_only=True))
    assert not eligible_for_training(s,'D2_ladder100',1000,True)
    assert eligible_for_training(s,'D3_ladder1000',1000,True)
    s.split='test'
    assert not eligible_for_training(s,'D3_ladder1000',1000,True)

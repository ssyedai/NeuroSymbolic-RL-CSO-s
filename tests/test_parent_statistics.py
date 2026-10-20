import pandas as pd
import pytest
from research.parent_statistics import prepare,compare


def examples():
    rows=[]
    for method in ('native','candidate'):
        for seed in range(3):
            for parent in range(3):
                for child in range(parent+1):
                    cso=10.+parent-(1 if method=='candidate' else 0)
                    rows.append(dict(method=method,seed=seed,split='val',family='C',rung='C1',parent=str(parent),
                        storm_id=f'{parent}_{child}',cso_54_m3=cso,cso_65_m3=0.,cso_54_B_m3=0.,cso_65_B_m3=0.,
                        flood_total=0.,cso_total=cso,total_overflow_vol_m3=cso))
    return pd.DataFrame(rows)


def test_children_are_averaged_before_parent_inference():
    data=examples();parents=prepare(data)
    assert len(parents)==18
    result=compare(data,'candidate','native',n_boot=50)
    assert all(r['n_events']==3 for r in result)
    assert result[1]['mean_diff']==pytest.approx(1.)
    assert result[0]['p_wilcoxon']==1.


def test_incomplete_pairs_and_bypass_omission_are_rejected():
    data=examples()
    with pytest.raises(ValueError):compare(data.iloc[1:],'candidate','native',n_boot=10)
    data.loc[0,'cso_54_B_m3']=5.
    with pytest.raises(ValueError):prepare(data)


def test_parent_split_leakage_is_rejected():
    data=examples();data.loc[0,'split']='test'
    with pytest.raises(ValueError):prepare(data)

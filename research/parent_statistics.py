"""Matched parent-event statistics for future validated all-four-outfall runs.

Consumes explicitly supplied results only; never discovers or opens test data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from multistorm.stats import paired_compare, holm

OUTFALLS=['cso_54_m3','cso_65_m3','cso_54_B_m3','cso_65_B_m3']
METRICS=['flood_total','cso_total','total_overflow_vol_m3']
KEYS=['method','seed','split','family','rung','parent','storm_id']


def prepare(frame):
    d=frame.copy()
    required=KEYS+OUTFALLS+METRICS
    if any(k not in d for k in required) or d.empty:
        raise ValueError('Missing event identifiers or all-four-outfall volumes')
    if d[required].isna().any().any() or d.duplicated(KEYS).any():
        raise ValueError('Missing values or duplicate event records')
    if not np.isfinite(d[OUTFALLS+METRICS].to_numpy(dtype=float)).all() or (d[OUTFALLS+METRICS]<0).any().any():
        raise ValueError('Invalid volume')
    if not np.allclose(d.cso_total,d[OUTFALLS].sum(axis=1),rtol=1e-9,atol=1e-6):
        raise ValueError('CSO must include all four untreated outfalls')
    if not np.allclose(d.total_overflow_vol_m3,d.cso_total+d.flood_total,rtol=1e-9,atol=1e-6):
        raise ValueError('Total overflow must equal CSO plus nodal flooding')
    if (d.groupby('parent').split.nunique()>1).any():
        raise ValueError('Parent occurs in multiple splits')
    if (d.groupby('storm_id')[['parent','split','family','rung']].nunique()>1).any().any():
        raise ValueError('Inconsistent scenario metadata')
    # Equal weight per parent within each reported family/rung.
    return d.groupby(KEYS[:-1],as_index=False,dropna=False)[METRICS].mean()


def compare(frame, method, reference, n_boot=10000):
    d=frame[frame.method.isin([method,reference])].copy()
    if method==reference or set(d.method)!={method,reference}:
        raise ValueError('Two distinct methods required')
    # Check children before aggregation; equal parent IDs alone can conceal missing storms.
    identity=KEYS[1:]
    a=set(map(tuple,d[d.method==method][identity].to_numpy()))
    b=set(map(tuple,d[d.method==reference][identity].to_numpy()))
    if a!=b: raise ValueError('Methods must have identical seeds and child events; no silent dropping')
    parents=prepare(d)
    output=[]
    for group,g in parents.groupby(['split','family','rung'],sort=True):
        seeds=sorted(g.seed.unique());events=sorted(g.parent.unique())
        if len(seeds)<3 or len(events)<3: raise ValueError('At least three seeds and three parents required per group')
        for metric in METRICS:
            arrays=[]
            for name in (method,reference):
                matrix=g[g.method==name].pivot(index='seed',columns='parent',values=metric).reindex(index=seeds,columns=events)
                if matrix.isna().any().any(): raise ValueError('Incomplete seed by parent matrix')
                arrays.append(matrix.to_numpy())
            result=paired_compare(*arrays,higher_is_better=False,n_boot=n_boot,seed=0)
            if np.array_equal(arrays[0].mean(0),arrays[1].mean(0)):
                result['p_wilcoxon']=1.0
            output.append(dict(zip(['split','family','rung'],group),method=method,reference=reference,
                metric=metric,seeds=len(seeds),**result))
    corrected=holm({str(i):r['p_wilcoxon'] for i,r in enumerate(output)})
    for i,row in enumerate(output):row['p_holm']=corrected[str(i)]
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True)
    p.add_argument('--method',required=True);p.add_argument('--reference',default='native')
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    rows=compare(pd.read_csv(a.input),a.method,a.reference)
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'statistics.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
    (a.out/'run_config.json').write_text(json.dumps(dict(input=str(a.input.resolve()),
        input_sha256=hashlib.sha256(a.input.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        method=a.method,reference=a.reference,bootstrap_seed=0,bootstrap_replicates=10000,
        effect='positive means lower candidate volume',unit='parent event; children averaged within family/rung',
        multiplicity='Holm across all rows in this invocation; combine planned comparisons before final reporting',
        scope='statistics only; does not certify hydraulics, protocol freeze or experimental provenance'),indent=2))


if __name__=='__main__':main()

"""Independent scalar reference and fixed acceptance for diagnostic storage runs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from research.cutoff_root import AREA, COEFFICIENT, CUTOFF
from research.continuous_orifice_probe import continuous_flow
from research.reversing_orifice import summarize, TAIL


def continuous_root(b, alpha):
    if not math.isfinite(b) or not math.isfinite(alpha) or alpha<=0:
        raise ValueError('Invalid scalar target')
    if abs(b)<=CUTOFF+alpha*COEFFICIENT*math.sqrt(CUTOFF):
        return b/(1+alpha*COEFFICIENT/math.sqrt(CUTOFF))
    # Stable quadratic root for sqrt(abs(g)); avoids subtractive cancellation.
    z=2*abs(b)/(math.sqrt((alpha*COEFFICIENT)**2+4*abs(b))+alpha*COEFFICIENT)
    return math.copysign(z*z,b)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--prior',type=Path,required=True)
    args=p.parse_args()
    rows=pd.read_csv(args.run/'results.csv',float_precision='round_trip')
    expected={f'{n}_{a:g}_{s:g}' for n in ('junction','storage') for a in (.00005,.001) for s in (1,.5,.25)}
    if len(rows)!=12 or set(rows.case)!=expected:
        raise ValueError('Incomplete case matrix')
    refs={}
    for _,row in rows.iterrows():
        path=args.run/(row.case+'.inp')
        original=args.prior/'candidate'/(row.case+'.inp')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row.input_sha256 or path.read_bytes()!=original.read_bytes():
            raise ValueError('Unmatched input')
        data=pd.read_csv(args.run/(row.case+'.csv.gz'),float_precision='round_trip')
        check=summarize(data,row.to_dict(),row.amplitude_ft,flow_law=continuous_flow)
        if check['verified']!=row.verified:
            raise ValueError('Stored decision mismatch')
        if row.node=='storage':
            old_head=TAIL
            old_q=0.
            old_t=0.
            reference=[]
            for state in data.itertuples():
                alpha=(state.seconds-old_t)/(2*AREA)
                b=old_head-state.outfall_head_ft-alpha*old_q
                gap=continuous_root(b,alpha)
                q=float(continuous_flow(gap))
                head=state.outfall_head_ft+gap
                reference.append((state.seconds,head,q))
                old_head,old_q,old_t=head,q,state.seconds
            r=pd.DataFrame(reference,columns=['seconds','reference_head_ft','reference_flow_cfs'])
            refs[row.case]=dict(max_head_error_ft=float(abs(r.reference_head_ft-data.storage_head_ft).max()),
                               max_flow_error_cfs=float(abs(r.reference_flow_cfs-data.flow_cfs).max()))
            r.to_csv(args.run/(row.case+'_scalar_reference.csv.gz'),index=False,compression='gzip')
    result=dict(matched_inputs=True,decisions_recomputed=True,verified=int(rows.verified.sum()),cases=12,
                reference_scope='independent constant-area trapezoidal solution, storage cases only',
                storage_reference_comparison=refs,production_adoption=False)
    (args.run/'independent_verification.json').write_text(json.dumps(result,indent=2))
    (args.run/'verification_source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

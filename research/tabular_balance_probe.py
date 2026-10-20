"""Actual 7M storage geometry versus independent integral-volume continuity."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import platform
from importlib.metadata import version
import numpy as np
import pandas as pd
from research.coupled_balance_probe import INCIDENCE
from research.continuous_orifice_probe import continuous_flow
from research.cutoff_root import COEFFICIENT, CUTOFF
from research.isolated_swmm_dll import run_model


DEPTH = np.array([0.,11.5,11.6,17.5,17.6,18.5,18.6,26.5,39.5,46.5])
AREA = np.array([465.01,465.01,1559.715,1559.715,18716.58,18716.58,24231.285,24231.285,24231.285,24231.285])
VOLUME = np.r_[0.,np.cumsum(np.diff(DEPTH)*(AREA[:-1]+AREA[1:])/2)]
INVERT = 582.792


def storage_volume(y):
    i = np.clip(np.searchsorted(DEPTH,y,side='right')-1,0,len(DEPTH)-2)
    dy = y-DEPTH[i]
    return VOLUME[i]+AREA[i]*dy+.5*(AREA[i+1]-AREA[i])/np.diff(DEPTH)[i]*dy*dy


def volumes(y):
    return np.r_[12.566*y[0],storage_volume(y[1:])]


def reference_step(old, old_q, dt, old_inflow, new_inflow):
    y=old.copy()
    old_v=volumes(old)
    def residual(x):
        q=continuous_flow(-INCIDENCE.T@x)
        return volumes(x)-old_v-.5*dt*(INCIDENCE@(old_q+q)+np.array([old_inflow+new_inflow,0.,0.]))
    for _ in range(100):
        r=residual(y)
        if max(abs(r))<1e-8:
            return y,continuous_flow(-INCIDENCE.T@y)
        gap=-INCIDENCE.T@y
        slope=np.where(abs(gap)<=CUTOFF,COEFFICIENT/np.sqrt(CUTOFF),
                       COEFFICIENT/(2*np.sqrt(np.maximum(abs(gap),CUTOFF))))
        areas=np.r_[12.566,np.interp(y[1:],DEPTH,AREA)]
        jac=np.diag(areas)+.5*dt*(INCIDENCE@np.diag(slope)@INCIDENCE.T)
        change=np.linalg.solve(jac,-r)
        scale=1.
        while scale>2**-30:
            trial=y+scale*change
            if np.linalg.norm(residual(trial))<np.linalg.norm(r):
                y=trial
                break
            scale*=.5
        else:
            # Roundoff at tabular-volume magnitudes can prevent further descent.
            if max(abs(r))<1e-7:return y,continuous_flow(-INCIDENCE.T@y)
            raise RuntimeError('Independent integral-volume Newton line search failed')
    raise RuntimeError('Independent integral-volume Newton failed')


def model(step, initial, inflow=65.):
    return f'''[TITLE]
Synthetic tabular storage conservation; not thesis performance
[OPTIONS]
FLOW_UNITS CFS
FLOW_ROUTING DYNWAVE
START_DATE 01/01/2020
START_TIME 00:00:00
REPORT_START_DATE 01/01/2020
REPORT_START_TIME 00:00:00
END_DATE 01/01/2020
END_TIME {'00:10:00' if inflow>0 else '00:05:00'}
ROUTING_STEP {step}
VARIABLE_STEP 0
MINIMUM_STEP {step}
REPORT_STEP 00:00:01
SURCHARGE_METHOD SLOT
MAX_TRIALS 40
HEAD_TOLERANCE 0.0001
ALLOW_PONDING NO
LINK_OFFSETS DEPTH
[STORAGE]
S {INVERT} 46.5 {initial} FUNCTIONAL 0 0 12.566 0 0
O {INVERT} 46.5 {initial} TABULAR G 0 0
B {INVERT} 46.5 {initial} TABULAR G 0 0
[OUTFALLS]
Z 0 FREE NO
[ORIFICES]
W S O SIDE 0 .4 NO .117
V S B SIDE 0 .4 NO .117
[XSECTIONS]
W RECT_CLOSED 7 14.14 0 0
V RECT_CLOSED 7 14.14 0 0
[CURVES]
'''+ '\n'.join(f'G {"Storage" if i==0 else ""} {d} {a}' for i,(d,a) in enumerate(zip(DEPTH,AREA)))+'''
[INFLOWS]
S FLOW "" FLOW 1 1 INFLOW_VALUE
[REPORT]
INPUT NO
CONTROLS NO
NODES ALL
LINKS ALL
'''.replace('INFLOW_VALUE',str(inflow))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dll',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--inflow',type=float,choices=[65.,-65.],default=65.)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    config=dict(purpose='Independent integrated-volume verification of actual 7M tabular storage geometry',
                seed=0,git_hash=None,manifest_hash=None,theta_hash=None,
                versions={**{name:version(name) for name in ('numpy','pandas','pyswmm','swmm-toolkit')},'python':platform.python_version()},
                depths_ft=DEPTH.tolist(),areas_ft2=AREA.tolist(),inflow_cfs=a.inflow,steps=[1.,.5,.25],
                initial_depths_ft=[17.4,18.4] if a.inflow>0 else [17.7,18.7],duration_seconds=600 if a.inflow>0 else 300,processes=1,budget_seconds=600,
                criteria=dict(head_ft=.0001,flow_cfs=.05,zero_flood=True),production_adoption=False,
                dll_sha256=hashlib.sha256(a.dll.read_bytes()).hexdigest(),
                runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                caveat='Two equal tabular storage units and constant-area source; no conduits or native rules.')
    (a.out/'run_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    (a.out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    rows=[];start=time.monotonic()
    for initial in config['initial_depths_ft']:
        for step in config['steps']:
            case=f'tabular_{initial:g}_{step:g}'
            path=a.out/(case+'.inp');path.write_text(model(step,initial,a.inflow),encoding='utf-8')
            samples,final=run_model(a.dll,path,start,extra_nodes=('B',),extra_links=('V',))
            data=pd.DataFrame(samples,columns=['seconds','S_head','O_head','W_flow','S_volume','B_head','V_flow'])
            old=np.full(3,initial);q=np.zeros(2);t=0.;ref=[]
            for seconds in data.seconds:
                old,q=reference_step(old,q,seconds-t,a.inflow if t>0 else 0.,a.inflow)
                ref.append([*(old+INVERT),*q]);t=seconds
            ref=np.array(ref)
            err_h=float(np.max(abs(data[['S_head','O_head','B_head']].to_numpy()-ref[:,:3])))
            err_q=float(np.max(abs(data[['W_flow','V_flow']].to_numpy()-ref[:,3:])))
            reference_valid=bool(np.min(ref[:,:3]-INVERT)>=7 and
                                 np.min(data[['S_head','O_head','B_head']].to_numpy()-INVERT)>=7)
            for i,name in enumerate(['ref_S_head','ref_O_head','ref_B_head','ref_W_flow','ref_V_flow']):data[name]=ref[:,i]
            data.to_csv(a.out/(case+'.csv.gz'),index=False,compression='gzip')
            rows.append(dict(case=case,routing_seconds=step,initial_depth=initial,max_head_error_ft=err_h,
                max_flow_error_cfs=err_q,reference_fully_submerged=reference_valid,
                passed=reference_valid and err_h<=.0001 and err_q<=.05 and final['flooding_ft3']==0,
                input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**final))
            pd.DataFrame(rows).to_csv(a.out/'results.csv',index=False)
            print(case,err_h,err_q,rows[-1]['passed'],flush=True)
    (a.out/'summary.json').write_text(json.dumps(dict(cases=len(rows),passed=sum(r['passed'] for r in rows),
        wall_seconds=time.monotonic()-start,production_adoption=False),indent=2),encoding='utf-8')


if __name__=='__main__':main()

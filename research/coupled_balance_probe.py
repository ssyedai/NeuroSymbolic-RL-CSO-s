"""Synthetic three-node test of simultaneous endpoint continuity; no rain/RL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import numpy as np
import pandas as pd
from research.continuous_orifice_probe import continuous_flow
from research.cutoff_root import COEFFICIENT, CUTOFF
from research.isolated_swmm_dll import run_model
from research.weir_reproduction import model_text, TAIL

# S -> O and S -> B. Equal large reservoirs are a synthetic simplification.
AREAS = np.array([12.566, 24231.285, 24231.285])
INCIDENCE = np.array([[-1., -1.], [1., 0.], [0., 1.]])


def coupled_step(old, old_q, dt, old_inflow=0., new_inflow=0.):
    """Independent simultaneous trapezoidal balance, in relative-head coordinates."""
    h = old.copy()
    def residual(x):
        q = continuous_flow(-INCIDENCE.T @ x)
        return AREAS*(x-old)-.5*dt*(INCIDENCE @ (old_q+q)+np.array([old_inflow+new_inflow,0.,0.]))
    for _ in range(80):
        r = residual(h)
        if np.max(np.abs(r)) <= 1e-9:
            return h, continuous_flow(-INCIDENCE.T @ h)
        gaps = -INCIDENCE.T @ h
        slope = np.where(np.abs(gaps) <= CUTOFF, COEFFICIENT/np.sqrt(CUTOFF),
                         COEFFICIENT/(2*np.sqrt(np.maximum(np.abs(gaps), CUTOFF))))
        jac = np.diag(AREAS)+.5*dt*(INCIDENCE @ np.diag(slope) @ INCIDENCE.T)
        change = np.linalg.solve(jac, -r)
        scale = 1.
        while scale > 2**-30:
            candidate = h+scale*change
            if np.linalg.norm(residual(candidate)) < np.linalg.norm(r):
                h = candidate
                break
            scale *= .5
        else:
            raise RuntimeError('Independent coupled Newton line search failed')
    raise RuntimeError('Independent coupled balance did not converge')


def make_model(step, amplitude, endpoint, inflow=0.):
    initial = np.array([0., -amplitude, .5*amplitude])
    s = model_text(step, 'SLOT', 40, .0001, TAIL)
    nodes = '[STORAGE]\n'
    for name, h, area in zip(('S','O','B'), initial+TAIL, AREAS):
        if name == 'S' and endpoint == 'junction':
            continue
        nodes += f'{name} 601.292 28 {h-601.292:.12f} FUNCTIONAL 0 0 {area} 0 0\n'
    if endpoint == 'junction':
        nodes += f'[JUNCTIONS]\nS 601.292 28 {TAIL-601.292:.12f} 0 0\n'
    # Disconnected dry outfall satisfies SWMM's network validator; exchanges no water.
    nodes += '[OUTFALLS]\nZ 0 FREE NO\n'
    s = re.sub(r'\[STORAGE\].*?(?=\[WEIRS\])', nodes, s, flags=re.S)
    s = re.sub(r'\[WEIRS\].*?(?=\[REPORT\])',
        '[ORIFICES]\nW S O SIDE 0 .4 NO .117\nV S B SIDE 0 .4 NO .117\n'
        '[XSECTIONS]\nW RECT_CLOSED 7 14.14 0 0\nV RECT_CLOSED 7 14.14 0 0\n', s, flags=re.S)
    if inflow:
        s=s.replace('[REPORT]',f'[INFLOWS]\nS FLOW "" FLOW 1 1 {inflow}\n[REPORT]')
    return s.replace('Synthetic isolated weir verification', 'Synthetic coupled endpoint verification')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dll',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--inflow',type=float,choices=[0.,.2,65.],default=0.)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    config=dict(purpose='Synthetic simultaneous-head diagnostic, not thesis performance',
        processes=1,budget_seconds=600,duration_seconds=600,steps=[1,.5,.25],inflow_cfs=a.inflow,
        amplitudes=[.00005,.001],endpoints=['storage','junction'],max_trials=40,
        head_tolerance_ft=.0001,areas_ft2=AREAS.tolist(),git_hash=None,seed=None,
        manifest_hash=None,theta_hash=None,production_adoption=False,
        criteria=dict(max_head_error_ft=.0001,max_flow_error_cfs=.05,
                      max_constitutive_residual_cfs=.05,zero_flood=True),
        caveat='Junction area is computational, not physical storage. Both reservoirs use synthetic equal constant areas.',
        dll_sha256=hashlib.sha256(a.dll.read_bytes()).hexdigest(),
        sources={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                 (Path(__file__),Path('research/isolated_swmm_dll.py'),Path('research/continuous_orifice_probe.py'))})
    (a.out/'run_config.json').write_text(json.dumps(config,indent=2))
    start=time.monotonic()
    rows=[]
    previous=os.environ.get('SWMM_FAILURE_TRACE')
    try:
        for endpoint in config['endpoints']:
            for amplitude in config['amplitudes']:
                for dt in config['steps']:
                    case=f'{endpoint}_{amplitude:g}_{dt:g}'
                    path=a.out/(case+'.inp')
                    path.write_text(make_model(dt,amplitude,endpoint,a.inflow))
                    trace=a.out/(case+'_failures.csv')
                    os.environ['SWMM_FAILURE_TRACE']=str(trace.resolve())
                    samples,final=run_model(a.dll,path,start,extra_nodes=('B',),extra_links=('V',))
                    data=pd.DataFrame(samples,columns=['seconds','S_head','O_head','W_flow','S_volume','B_head','V_flow'])
                    old=np.array([0.,-amplitude,.5*amplitude])
                    q=np.zeros(2)  # SWMM initializes both link flows to zero.
                    t=0.
                    reference=[]
                    for seconds in data.seconds:
                        old,q=coupled_step(old,q,seconds-t,a.inflow if t>0 else 0.,a.inflow)
                        reference.append([*(old+TAIL),*q])
                        t=seconds
                    ref=np.array(reference)
                    heads=data[['S_head','O_head','B_head']].to_numpy()
                    flows=data[['W_flow','V_flow']].to_numpy()
                    if not np.isfinite(data.to_numpy()).all() or t<599:
                        raise ValueError('Invalid/incomplete simulation')
                    err_h=float(np.max(abs(heads-ref[:,:3])))
                    err_q=float(np.max(abs(flows-ref[:,3:])))
                    residual=float(np.max(abs(flows-continuous_flow(-heads @ INCIDENCE))))
                    for n,name in enumerate(('ref_S_head','ref_O_head','ref_B_head','ref_W_flow','ref_V_flow')):
                        data[name]=ref[:,n]
                    data.to_csv(a.out/(case+'.csv.gz'),index=False,compression='gzip')
                    attribution=pd.read_csv(trace)
                    passed=err_h<=.0001 and err_q<=.05 and residual<=.05 and final['flooding_ft3']==0
                    rows.append(dict(case=case,max_head_error_ft=err_h,max_flow_error_cfs=err_q,
                        max_constitutive_residual_cfs=residual,verified=passed,
                        unconverged_steps=int(attribution.unconverged_steps.iloc[0]),
                        total_steps=int(attribution.total_steps.iloc[0]),
                        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**final))
                    pd.DataFrame(rows).to_csv(a.out/'results.csv',index=False)
    finally:
        if previous is None: os.environ.pop('SWMM_FAILURE_TRACE',None)
        else: os.environ['SWMM_FAILURE_TRACE']=previous
    result=dict(cases=len(rows),passed=sum(r['verified'] for r in rows),production_adoption=False,
                wall_seconds=time.monotonic()-start)
    (a.out/'summary.json').write_text(json.dumps(result,indent=2))
    (a.out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    print(pd.DataFrame(rows)[['case','max_head_error_ft','max_flow_error_cfs','max_constitutive_residual_cfs','unconverged_steps','verified']].to_string(index=False))
    print(json.dumps(result))


if __name__=='__main__':
    main()

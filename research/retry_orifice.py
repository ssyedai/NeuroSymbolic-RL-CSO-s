"""Bounded rejection/retry via deterministic full-state replay, not hotstarts."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from research.isolated_swmm_dll import RoutingTotals, run_model
from research.reversing_orifice import reference_flow, reversing_model

MIN_STEP = .25/128


def acceptable(state):
    values=[state[k] for k in ("head_s","head_o","flow","residual")]
    return bool(np.isfinite(values).all() and min(values[:2]) > 608.292 and
                state["converged"] == 1 and state["residual"] <= .05)


def retry(session, horizon=5., minimum=MIN_STEP, deadline=None):
    accepted=[]
    attempts=[]
    dt=.25
    restored=0
    def restore():
        nonlocal restored
        session.restart()
        for old in accepted:
            actual=session.step(old["dt"])
            if actual != old["state"]:
                raise ValueError("Replay does not exactly restore accepted history")
        restored+=1
    status="complete"
    while sum(x["dt"] for x in accepted) < horizon-1e-10:
        if deadline is not None and time.monotonic()>deadline:
            status="budget_exhausted"
            break
        if len(attempts)>=20000:
            status="attempt_limit"
            break
        state=session.step(dt)
        if abs(state["seconds"]-(sum(x["dt"] for x in accepted)+dt)) > 1e-7:
            raise ValueError("Solver did not advance by the requested step")
        good=acceptable(state)
        attempts.append(dict(dt=dt,accepted=good,**state))
        if good:
            accepted.append(dict(dt=dt,state=state))
        else:
            restore()  # Discard rejected time, stats, caches and mass accounting.
            if dt/2 < minimum-1e-12:
                status="minimum_step_failed"
                break
            dt/=2
    return dict(status=status,accepted_steps=len(accepted),rejected_steps=sum(not x["accepted"] for x in attempts),
                restored_prefixes=restored,accepted_time_s=sum(x["dt"] for x in accepted),
                smallest_attempt_s=min(x["dt"] for x in attempts),attempts=attempts,
                final_accepted_state=accepted[-1]["state"] if accepted else None)


class Session:
    def __init__(self,dll,path):
        self.lib=C.CDLL(str(dll.resolve()))
        self.path=path
        self.opened=self.started=False
        signatures={"swmm_open":[C.c_char_p]*3,"swmm_start":[C.c_int],"swmm_end":[],"swmm_close":[],
                    "swmm_step":[C.POINTER(C.c_double)],"swmm_diagSetStep":[C.c_double],"swmm_diagConverged":[],
                    "swmm_getIndex":[C.c_int,C.c_char_p],
                    "swmm_getNodeResult":[C.c_int,C.c_int,C.POINTER(C.c_double)],
                    "swmm_getLinkResult":[C.c_int,C.c_int,C.POINTER(C.c_double)],
                    "swmm_getSystemRoutingTotals":[C.POINTER(RoutingTotals)]}
        for name,args in signatures.items():
            getattr(self.lib,name).argtypes=args
            getattr(self.lib,name).restype=C.c_int
        self.restart()

    def call(self,name,*args):
        result=getattr(self.lib,name)(*args)
        if result:
            raise RuntimeError(f"{name}: {result}")

    def close(self):
        try:
            if self.started:
                self.call("swmm_end")
        finally:
            self.started=False
            if self.opened:
                self.call("swmm_close")
            self.opened=False

    def restart(self):
        self.close()
        self.call("swmm_open",*(str(p.resolve()).encode('ascii') for p in
                  (self.path,self.path.with_suffix('.rpt'),self.path.with_suffix('.out'))))
        self.opened=True
        self.call("swmm_start",0)
        self.started=True
        self.s=self.lib.swmm_getIndex(2,b'S')
        self.o=self.lib.swmm_getIndex(2,b'O')
        self.w=self.lib.swmm_getIndex(3,b'W')
        if min(self.s,self.o,self.w)<0:
            raise ValueError("Expected S/O/W")

    def value(self,name,index,field):
        value=C.c_double()
        self.call(name,index,field,C.byref(value))
        return value.value

    def step(self,dt):
        self.call("swmm_diagSetStep",dt)
        elapsed=C.c_double()
        self.call("swmm_step",C.byref(elapsed))
        if elapsed.value<=0:
            raise ValueError("Unexpected end of bounded experiment")
        hs=self.value("swmm_getNodeResult",self.s,6)
        ho=self.value("swmm_getNodeResult",self.o,6)
        q=self.value("swmm_getLinkResult",self.w,0)
        totals=RoutingTotals()
        self.call("swmm_getSystemRoutingTotals",C.byref(totals))
        return dict(seconds=elapsed.value*86400,head_s=hs,head_o=ho,flow=q,
                    volume=self.value("swmm_getNodeResult",self.s,3),
                    converged=self.lib.swmm_diagConverged(),residual=float(abs(q-reference_flow(hs-ho))),
                    **{"system_"+k:getattr(totals,k) for k,_ in totals._fields_})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dll',type=Path,required=True)
    parser.add_argument('--prior',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--horizon',type=float,choices=[5.,62.],default=5.)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((args.prior/'run_config.json').read_text())
    cfg.update(purpose="Isolated rejection/retry with full restart and exact accepted-prefix replay",
        horizon_s=args.horizon,initial_step_s=.25,minimum_step_s=MIN_STEP,max_attempts=20000,budget_s=600,
        acceptance="iteration convergence AND final-head flow residual <=0.05 CFS; no threshold relaxation",
        restoration="reopen original input; replay all accepted dt; exact state and all system-total comparison",
        scope="four fixed-gate synthetic cases; no full-network adoption",expected_runs=4,
        diagnostic_dll=str(args.dll.resolve()),dll_sha256=hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      (Path(__file__),Path('research/prepare_retry_engine.py'),Path('research/isolated_swmm_dll.py'))})
    (args.out/'run_config.json').write_text(json.dumps(cfg,indent=2))
    (args.out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    started=time.monotonic()
    prior=pd.read_csv(args.prior/'results.csv',float_precision='round_trip')
    equivalence=[]
    # API exposure with unused setter must preserve existing full-run results.
    for node in ('junction','storage'):
        name=f'{node}_0.001_0.25'
        path=args.out/('equivalence_'+name+'.inp')
        path.write_bytes((args.prior/'candidate'/(name+'.inp')).read_bytes())
        samples,final=run_model(args.dll,path,started)
        reference=pd.read_csv(args.prior/'candidate'/(name+'.csv.gz'),float_precision='round_trip')
        old=prior[(prior.case==name)&(prior.engine=='candidate')].iloc[0]
        if not np.array_equal(samples,reference.to_numpy()) or not all(final[k]==old[k] for k in final):
            raise ValueError('API-only build changed hydraulic results')
        equivalence.append(dict(case=name,exact_equivalence=True))
    (args.out/'equivalence.json').write_text(json.dumps(equivalence,indent=2))
    results=[]
    for node in ('junction','storage'):
        for amp in (.00005,.001):
            name=f'{node}_{amp:g}'
            path=args.out/(name+'.inp')
            path.write_text(reversing_model(.25,node,amp))
            session=Session(args.dll,path)
            try:
                result=retry(session,horizon=args.horizon,deadline=started+600)
            finally:
                session.close()
            attempts=result.pop('attempts')
            pd.DataFrame(attempts).to_csv(args.out/(name+'_attempts.csv'),index=False)
            result.update(case=name,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            results.append(result)
            (args.out/'results.json').write_text(json.dumps(results,indent=2))
    print(json.dumps([{k:v for k,v in r.items() if k!='final_accepted_state'} for r in results],indent=2))


if __name__=='__main__':
    main()

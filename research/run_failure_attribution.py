"""Replay a fixed TRAIN resolution with read-only convergence attribution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import pandas as pd
from research.network_dll_probe import main as network_main


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dll',type=Path,required=True)
    parser.add_argument('--prior',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--step',type=float,choices=[.5,.25],default=.25)
    args=parser.parse_args()
    path=(args.out/'failure_attribution.csv').resolve()
    old_env=os.environ.get('SWMM_FAILURE_TRACE')
    old_argv=sys.argv[:]
    try:
        os.environ['SWMM_FAILURE_TRACE']=str(path)
        sys.argv=['network_dll_probe','--dll',str(args.dll),'--out',str(args.out),'--routing-seconds',str(args.step)]
        network_main()
    finally:
        sys.argv=old_argv
        if old_env is None: os.environ.pop('SWMM_FAILURE_TRACE',None)
        else: os.environ['SWMM_FAILURE_TRACE']=old_env
    actual=pd.read_csv(args.out/'results.csv',float_precision='round_trip').iloc[0]
    prior=pd.read_csv(args.prior/'results.csv',float_precision='round_trip')
    expected=prior[prior.routing_seconds==args.step].iloc[0]
    for key in expected.index:
        if key!='wall_seconds' and actual[key]!=expected[key]:
            raise ValueError(f'Logging changed result: {key}')
    trace=pd.read_csv(path)
    if trace.empty or trace.total_steps.nunique()!=1:
        raise ValueError('Missing or inconsistent attribution')
    result=dict(exact_hydraulic_equivalence=True,production_adoption=False,
        scope='final-iteration failure counts; multiple elements can fail in one step',
        total_steps=int(trace.total_steps.iloc[0]),unconverged_steps=int(trace.unconverged_steps.iloc[0]),
        pre_flow_failed_steps=int(trace.pre_flow_failed_steps.iloc[0]),
        top_continuity=trace[trace.kind=='node'].nlargest(10,'continuity_failures').to_dict('records'),
        top_final_flow=trace[trace.kind=='link'].nlargest(10,'final_flow_failures').to_dict('records'),
        top_head=trace[trace.kind=='node'].nlargest(10,'head_failures').to_dict('records'),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        attribution_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (args.out/'attribution_summary.json').write_text(json.dumps(result,indent=2))
    (args.out/'attribution_runner.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k:v for k,v in result.items() if not k.startswith('top_')},indent=2))
    print(trace.nlargest(8,'continuity_failures')[['kind','id','continuity_failures','max_continuity_ft3']].to_string(index=False))
    print(trace.nlargest(5,'final_flow_failures')[['kind','id','final_flow_failures','max_flow_cfs']].to_string(index=False))


if __name__=='__main__':
    main()

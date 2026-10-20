"""Bounded TRAIN iteration-cap sensitivity; thresholds and equations unchanged."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import time
from research.network_dll_probe import run_native


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--step',type=float,choices=[1,.5,.25],required=True)
    p.add_argument('--trials',type=int,choices=[80,200],default=200)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prior',type=Path,default=Path('runs/hydraulic_validation_20261019/network_balance_bypass'))
    p.add_argument('--dll',type=Path,default=Path('runs/hydraulic_validation_20261019/balance_bins_build/src/solver/Release/swmm5.dll'))
    a=p.parse_args()
    prior=a.prior
    cfg=json.loads((prior/'run_config.json').read_text())
    assert cfg['split']=='train'
    dll=a.dll
    a.out.mkdir(exist_ok=False)
    path=a.out/f'native_{a.step:g}.inp'
    old=(prior/path.name).read_bytes()
    new,count=re.subn(rb'(?m)^(MAX_TRIALS\s+)40(?=\s|$)',lambda m:m[1]+str(a.trials).encode(),old)
    if count!=1:raise ValueError('Expected one original MAX_TRIALS=40')
    path.write_bytes(new)
    cfg.update(purpose='Iteration-cap sensitivity; not an accepted solver or reference',
               max_trials=a.trials,routing_seconds=[a.step],expected_runs=1,budget_s=1200,
               engine_dll=str(dll.resolve()),dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),
               input_sha256=hashlib.sha256(new).hexdigest(),prior_input_sha256=hashlib.sha256(old).hexdigest(),
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.out/'run_config.json').write_text(json.dumps(cfg,indent=2))
    (a.out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    key='SWMM_BALANCE_BINS';previous=os.environ.get(key)
    os.environ[key]=str((a.out/f'balance_bins_{a.step:g}.csv').resolve())
    start=time.monotonic()
    try:result=run_native(dll,path,start+1200)
    finally:
        if previous is None:os.environ.pop(key,None)
        else:os.environ[key]=previous
    report=path.with_suffix('.rpt').read_text()
    result.update(routing_seconds=a.step,max_trials=a.trials,wall_seconds=time.monotonic()-start,
                  nonconverging_pct=float(re.search(r'% of Steps Not Converging\s*:\s*([\d.]+)',report).group(1)))
    (a.out/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()

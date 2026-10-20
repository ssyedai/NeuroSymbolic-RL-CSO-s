"""Verify an explicitly changed continuous law on existing synthetic inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from research.isolated_swmm_dll import run_model
from research.reversing_orifice import summarize


def continuous_flow(gap):
    gap=np.asarray(gap,dtype=float)
    if not np.isfinite(gap).all():
        raise ValueError('Non-finite head')
    magnitude=np.abs(gap)
    return .4*7*14.14*np.sqrt(64.4)*np.where(magnitude<=.0001,gap/.01,np.sign(gap)*np.sqrt(magnitude))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dll',type=Path,required=True)
    p.add_argument('--prior',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cfg=json.loads((args.prior/'run_config.json').read_text())
    cfg.update(purpose='Alternative continuous-orifice formulation; not original SWMM or control improvement',
        expected_runs=12,engine=str(args.dll.resolve()),dll_sha256=hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        law='q=K*gap/sqrt(0.0001) below threshold; K*sign(gap)*sqrt(abs(gap)) above',
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                      (Path(__file__),Path('research/reversing_orifice.py'),Path('research/isolated_swmm_dll.py'))})
    (args.out/'run_config.json').write_text(json.dumps(cfg,indent=2))
    (args.out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    rows=[]
    start=time.monotonic()
    for node in ('junction','storage'):
        for amp in (.00005,.001):
            for step in (1,.5,.25):
                case=f'{node}_{amp:g}_{step:g}'
                path=args.out/(case+'.inp')
                path.write_bytes((args.prior/'candidate'/(case+'.inp')).read_bytes())
                samples,final=run_model(args.dll,path,start)
                data=pd.DataFrame(samples,columns=['seconds','storage_head_ft','outfall_head_ft','flow_cfs','volume_ft3'])
                data.to_csv(args.out/(case+'.csv.gz'),index=False,compression='gzip')
                rows.append(dict(case=case,node=node,amplitude_ft=amp,step=step,
                    input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    **summarize(data,final,amp,flow_law=continuous_flow),**final))
                pd.DataFrame(rows).to_csv(args.out/'results.csv',index=False)
    result=dict(complete=len(rows)==12,verified=sum(r['verified'] for r in rows),runs=len(rows),production_adoption=False)
    (args.out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':
    main()

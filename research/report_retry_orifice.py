"""Recompute retry acceptance and water balance from retained attempts."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from research.retry_orifice import acceptable


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    results=json.loads((args.run/'results.json').read_text())
    config=json.loads((args.run/'run_config.json').read_text())
    rows=[]
    for result in results:
        d=pd.read_csv(args.run/(result['case']+'_attempts.csv'),float_precision='round_trip')
        decisions=d.apply(lambda r:acceptable(r.to_dict()),axis=1)
        if not decisions.equals(d.accepted):
            raise ValueError('Stored acceptance differs from final-flow check')
        a=d[d.accepted]
        if len(a)!=result['accepted_steps'] or int((~d.accepted).sum())!=result['rejected_steps']:
            raise ValueError('Attempt counts disagree')
        if result['restored_prefixes']!=result['rejected_steps']:
            raise ValueError('Missing restoration')
        t=0.
        for _,attempt in d.iterrows():
            if abs(attempt.seconds-(t+attempt['dt']))>1e-7:
                raise ValueError('Rejected time leaked into accepted timeline')
            if attempt.accepted:
                t+=attempt['dt']
        if t!=result['accepted_time_s']:
            raise ValueError('Incorrect accepted time')
        final=a.iloc[-1]
        if any(final[k]!=v for k,v in result['final_accepted_state'].items()):
            raise ValueError('Final state contains rejected results')
        balance=(final.system_initStorage+sum(final['system_'+k] for k in
            ('dwInflow','wwInflow','gwInflow','iiInflow','exInflow'))-
            sum(final['system_'+k] for k in ('finalStorage','outflow','flooding','evapLoss','seepLoss')))
        gross=float((a.flow.abs()*a.dt).sum())
        balance_pass=bool(np.isfinite(balance) and abs(balance)<=max(.01,.01*gross))
        rows.append(dict(case=result['case'],status=result['status'],accepted_time_s=t,
            accepted_steps=len(a),rejected_steps=result['rejected_steps'],
            max_accepted_residual_cfs=float(a.residual.max()),system_balance_residual_ft3=balance,
            gross_link_volume_ft3=gross,balance_pass=balance_pass,
            completed_horizon=bool(t==config['horizon_s']),
            verified=bool(t==config['horizon_s'] and balance_pass and final.system_flooding==0
                          and np.isfinite(final.system_pctError) and abs(final.system_pctError)<=1)))
    (args.run/'verification.json').write_text(json.dumps(dict(production_adoption=False,
        all_completed=all(r['completed_horizon'] for r in rows),rows=rows),indent=2))
    (args.run/'report_source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    main()

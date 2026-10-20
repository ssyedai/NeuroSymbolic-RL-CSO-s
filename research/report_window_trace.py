"""Summarize read-only solver exit traces without conflating local residuals and volume loss."""
import json
from pathlib import Path
import pandas as pd


def main():
    root=Path('runs/hydraulic_validation_20261019/window_trace')
    checks=json.loads((root/'replay_verification.json').read_text())
    if len(checks)!=2 or not all(r['exact_final_match'] for r in checks):
        raise ValueError('Both unchanged replays required')
    summaries=[]
    for dt in (.5,.25):
        d=pd.read_csv(root/f'windows_{dt:g}.csv')
        for window,(start,end) in enumerate(((81000,85500),(112500,116100)),1):
            part=d[d.seconds.between(start,end)]
            exits=part[part.id=='35440']
            nodes=[]
            for name,g in part[part.kind=='node'].groupby('id'):
                signed=g.area*(g.depth-g.old_depth)-.5*g.dt*(g.old_net+g.net)
                nodes.append(dict(id=name,max_residual_ft3=float(g.residual.max()),
                                  continuity_failures=int((g.residual>1e-6).sum()),
                                  signed_equation_proxy_sum_ft3=float(signed.sum()),
                                  absolute_stopping_residual_sum_ft3=float(g.residual.sum())))
            links=[]
            for name,g in part[part.kind=='link'].groupby('id'):
                links.append(dict(id=name,max_final_flow_residual_cfs=float(g.residual.max()) if name in ('1360','1360_B','35444','W1') else None,
                                  setting_changes=int((g.setting.diff().abs()>0).sum()),
                                  target_changes=int((g.target.diff().abs()>0).sum()),
                                  max_flow_cfs=float(g.flow.max()),
                                  first_flow_second=float(g.loc[g.flow>1e-6,'seconds'].min()) if (g.flow>1e-6).any() else None))
            summaries.append(dict(step=dt,window=window,start=start,end=end,
                steps=len(exits),failed_steps=int((exits.converged==0).sum()),
                nodes=nodes,links=links))
    result=dict(windows=summaries,accepted=False,
        caution='Signed equation proxy uses reported final area and excludes bound/surcharge qualifications. It is not cumulative physical water loss. Conduit/pump final-flow residuals are not evaluated. Window boundaries are inclusive.')
    (root/'window_summary.json').write_text(json.dumps(result,indent=2))
    for s in summaries:
        n=next(n for n in s['nodes'] if n['id']=='35440')
        w=next(n for n in s['links'] if n['id']=='35444')
        print(f"dt={s['step']} window={s['window']} failed={s['failed_steps']}/{s['steps']} storage residual sum={n['absolute_stopping_residual_sum_ft3']:.6g} ft3; first weir flow={w['first_flow_second']}")


if __name__=='__main__':main()

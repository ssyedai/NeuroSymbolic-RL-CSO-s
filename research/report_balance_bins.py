"""Summarize verified final-iteration residual bins; never label them physical storage."""
import json
from pathlib import Path
import pandas as pd


def main():
    root=Path('runs/hydraulic_validation_20261019/balance_bins')
    verified=json.loads((root/'replay_verification.json').read_text())
    if len(verified)!=2 or not all(v['exact_final_match'] for v in verified):
        raise ValueError('Unverified logging run')
    records=[]
    for dt in (.5,.25):
        d=pd.read_csv(root/f'balance_bins_{dt:g}.csv')
        if d.duplicated(['bin_end','node']).any() or set(d.bin_end)!=set(range(900,259201,900)):
            raise ValueError('Missing/duplicate bins')
        if not (d.groupby('node').steps.sum()==259200/dt).all():
            raise ValueError('Inconsistent step counts')
        previous=pd.read_csv(Path('runs/hydraulic_validation_20261019/window_trace')/f'failures_{dt:g}.csv')
        actual=d.groupby('node').failed.sum()
        counts=previous[previous.kind=='node'].set_index('id').continuity_failures
        if not actual.equals(counts.reindex(actual.index).rename('failed')):
            # Compare values explicitly because index/series naming is not hydraulic evidence.
            if not (actual==counts.reindex(actual.index)).all():raise ValueError('Failure-count mismatch')
        summed=d.groupby('node')[['sum_signed_ft3','sum_absolute_ft3']].sum()
        pre=d[d.bin_end<=81900].groupby('node')[['sum_signed_ft3','sum_absolute_ft3']].sum()
        records.append(dict(step=dt,failure_counts_match_prior=True,
            largest_total_residual_nodes=summed.nlargest(10,'sum_absolute_ft3').reset_index().to_dict('records'),
            largest_preoverflow_residual_nodes=pre.nlargest(10,'sum_absolute_ft3').reset_index().to_dict('records'),
            largest_bins=d.nlargest(12,'sum_absolute_ft3').to_dict('records')))
    summary=dict(results=records,accepted=False,
        interpretation='Final ordinary-node continuity-equation residuals, not a global physical water budget. Signed sums can cancel; maxima and absolute sums complement failure counts.')
    (root/'balance_summary.json').write_text(json.dumps(summary,indent=2))
    print('288 bins per resolution verified; node failure counts match prior instrumentation.')


if __name__=='__main__':main()

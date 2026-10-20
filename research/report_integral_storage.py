"""Verify the completed isolated/network evidence for the storage experiment."""
import hashlib
import json
from pathlib import Path
import pandas as pd


def main():
    root=Path('runs/hydraulic_validation_20261020')
    groups={}
    for name,column,count in [('integral_weir','equilibrium_verified',24),
                              ('integral_orifice','verified',24),
                              ('integral_reversing','verified',12),
                              ('tabular_after','passed',6),
                              ('tabular_draining_valid_scope','passed',6)]:
        data=pd.read_csv(root/name/'results.csv')
        if len(data)!=count or not data[column].eq(True).all():
            raise ValueError(f'Failed or incomplete isolated group: {name}')
        groups[name]=dict(cases=len(data),passed=int(data[column].sum()))
        if name.startswith('tabular'):
            for case in data.case:
                samples=pd.read_csv(root/name/(case+'.csv.gz'))
                for fields in [('S_head','O_head','B_head'),('ref_S_head','ref_O_head','ref_B_head')]:
                    if (samples[list(fields)].to_numpy()-582.792).min()<7:
                        raise ValueError('Fully submerged independent-reference scope violated')
    before=pd.read_csv(root/'tabular_before/results.csv')
    after=pd.read_csv(root/'tabular_after/results.csv')
    if not before.case.equals(after.case) or not before.input_sha256.equals(after.input_sha256):
        raise ValueError('Before/after inputs are unmatched')
    network=pd.read_csv(root/'network_integral_storage/results.csv')
    decision=json.loads((root/'network_integral_storage/summary.json').read_text(encoding='utf-8'))
    if len(network)!=3 or not decision['complete']:
        raise ValueError('All three network refinements must finish')
    prior=pd.read_csv('runs/hydraulic_validation_20261019/network_surface_transition/results.csv')
    if not network.input_sha256.equals(prior.input_sha256):
        raise ValueError('Network inputs differ from prior candidate')
    pairs=[]
    for comparison in decision['comparisons']:
        fine=network[network.routing_seconds==comparison['fine']].iloc[0]
        delta=comparison['absolute_deltas_m3']['cso_total']
        pairs.append(dict(**comparison,cso_relative_pct=100*delta/fine.cso_total,
                          cso_limit_m3=max(1.,.01*abs(fine.cso_total))))
    evidence={}
    for folder in list(groups)+['tabular_before','surface_stride_localization','surface_control_trace','network_integral_storage']:
        for p in (root/folder).iterdir():
            if p.is_file() and p.suffix in ('.json','.csv','.py','.gz','.png'):
                evidence[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [Path('research/tabular_balance_probe.py'),Path('research/prepare_integral_storage.py'),
              Path(__file__),Path('docs/integral_storage_verification_20261020.md')]:
        evidence[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    report=dict(isolated_groups=groups,isolated_passes=72,isolated_cases=72,
                previous_tabular_passes=int(before.passed.sum()),previous_tabular_cases=6,
                network_comparisons=pairs,network_probe_passed=decision['passed'],
                production_engine_adopted=False,training_permitted=False,
                control_change_logger_valid=False,
                caveat='Even a passed single TRAIN probe would not certify all G0-G3 or authorize training.',
                evidence_sha256=evidence)
    (root/'current_verification_bundle.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='evidence_sha256'},indent=2))


if __name__=='__main__':main()

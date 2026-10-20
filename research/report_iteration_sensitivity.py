"""Compare matched iteration budgets without relaxing hydraulic criteria."""
import csv
import hashlib
import json
import re
from pathlib import Path


def main():
    root = Path('runs/hydraulic_validation_20261019')
    original = root / 'network_surface_transition'
    with (original / 'results.csv').open() as f:
        prior = {float(r['routing_seconds']): r for r in csv.DictReader(f)}
    results = []
    evidence = {}
    for step, suffix in ((0.5, '05'), (0.25, '025')):
        folder = root / f'surface_trials200_{suffix}'
        result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        old = (original / f'native_{step:g}.inp').read_bytes()
        new = (folder / f'native_{step:g}.inp').read_bytes()
        restored, count = re.subn(rb'(?m)^(MAX_TRIALS\s+)200(?=\s|$)',
                                  lambda m: m[1]+b'40', new)
        if count != 1 or restored != old:
            raise ValueError('Unmatched sensitivity inputs')
        result['cso_change_from_40_m3'] = result['cso_total']-float(prior[step]['cso_total'])
        results.append(result)
        for filename in ('run_config.json', 'result.json', f'native_{step:g}.inp'):
            path = folder / filename
            evidence[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    coarse, fine = results
    delta = abs(coarse['cso_total']-fine['cso_total'])
    limit = max(1., 0.01*abs(fine['cso_total']))
    checks = dict(cso=delta <= limit,
                  total=abs(coarse['total_overflow_vol_m3']-fine['total_overflow_vol_m3']) <=
                        max(1., .01*abs(fine['total_overflow_vol_m3'])),
                  flood=abs(coarse['flood_total']-fine['flood_total']) <= 1.,
                  routing=all(abs(r['routing_error_pct']) <= 1. for r in results))
    summary = dict(results=results, finest_pair_checks=checks,
                   cso_delta_m3=delta, cso_limit_m3=limit,
                   cso_relative_pct=100*delta/abs(fine['cso_total']),
                   finest_pair_passed=all(checks.values()),
                   coarse_pair_tested=False, full_gate_passed=False,
                   production_adoption=False, evidence_sha256=evidence)
    (root / 'surface_iteration_sensitivity.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

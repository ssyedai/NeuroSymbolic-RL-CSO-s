"""Summarize read-only replay evidence without treating residuals as water loss."""
import csv
import json
from collections import defaultdict
from pathlib import Path


def main():
    root = Path('runs/hydraulic_validation_20261019')
    current = root / 'surface_failure_attribution'
    replay = json.loads((current / 'replay_verification.json').read_text(encoding='utf-8'))
    if len(replay) != 2 or not all(r['exact_final_match'] for r in replay):
        raise ValueError('Both exact replays required before attribution')
    records = {}
    for step in (0.5, 0.25):
        with (current / f'failures_{step:g}.csv').open() as f:
            rows = list(csv.DictReader(f))
        records[str(step)] = dict(
            total_steps=int(rows[0]['total_steps']),
            unconverged_steps=int(rows[0]['unconverged_steps']),
            nodes=sorted((r for r in rows if r['kind'] == 'node'),
                         key=lambda r: int(r['continuity_failures']), reverse=True)[:7],
            links=sorted((r for r in rows if r['kind'] == 'link'),
                         key=lambda r: int(r['final_flow_failures']), reverse=True)[:4])
    residuals = {}
    for name in ('balance_bins', 'surface_failure_attribution'):
        totals = defaultdict(float)
        with (root / name / 'balance_bins_0.5.csv').open() as f:
            for r in csv.DictReader(f):
                if float(r['bin_start']) < 82800:
                    totals[r['node']] += float(r['sum_absolute_ft3'])
        residuals[name] = {n: totals[n] for n in ('3517', '3528', '3534', '3536', '1360', '35440', '35442')}
    result = dict(exact_replays=True, failures=records,
                  pre_82800s_sum_absolute_continuity_residual_ft3=residuals,
                  caveat='Residual sums are diagnostics, not measured water losses; failure counts overlap.',
                  hydraulic_gate_passed=False, production_adoption=False)
    (current / 'attribution_summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

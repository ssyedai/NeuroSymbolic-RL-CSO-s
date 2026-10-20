"""Localize refinement differences from cumulative engine counters, not sampled flows."""
import hashlib
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('runs/hydraulic_validation_20261019/stride_localization'))
    root = parser.parse_args().root
    checks = json.loads((root / 'replay_verification.json').read_text())
    if len(checks) != 2 or not all(r['exact_final_match'] for r in checks):
        raise ValueError('Requires two verified unchanged replays')
    data = pd.read_csv(root / 'stride_observations.csv')
    volumes = [f'cso_{n}_m3' for n in ('54', '65', '54_B', '65_B')]
    data['cso_m3'] = data[volumes].sum(axis=1)
    coarse = data[data.routing_seconds == .5].set_index('seconds')
    fine = data[data.routing_seconds == .25].set_index('seconds')
    assert list(coarse.index) == list(fine.index) == list(range(900, 259201, 900))
    intervals = pd.DataFrame(index=coarse.index)
    for label, frame in [('coarse', coarse), ('fine', fine)]:
        intervals[label + '_cso_m3'] = frame.cso_m3
        intervals[label + '_interval_m3'] = frame.cso_m3.diff().fillna(frame.cso_m3.iloc[0])
    intervals['cumulative_difference_m3'] = coarse.cso_m3 - fine.cso_m3
    intervals['interval_difference_m3'] = intervals.coarse_interval_m3 - intervals.fine_interval_m3
    intervals['start_seconds'] = intervals.index - 900
    intervals['end_seconds'] = intervals.index
    intervals.to_csv(root / 'interval_differences.csv', index=False)
    ranked = intervals.reindex(intervals.interval_difference_m3.abs().sort_values(ascending=False).index)
    summary = dict(
        final_difference_m3=float(intervals.cumulative_difference_m3.iloc[-1]),
        sum_absolute_interval_difference_m3=float(intervals.interval_difference_m3.abs().sum()),
        largest_intervals=ranked.head(10).to_dict(orient='records'),
        first_nonzero_difference_interval_end_seconds=int(intervals.index[np.abs(intervals.cumulative_difference_m3) > 1e-6][0]),
        max_cumulative_difference_m3=float(intervals.cumulative_difference_m3.max()),
        max_cumulative_difference_at_seconds=int(intervals.cumulative_difference_m3.idxmax()),
        outfall_final_differences_m3={c:float(coarse[c].iloc[-1]-fine[c].iloc[-1]) for c in volumes},
        max_flood_m3=float(data.flood_m3.max()),
        observation_sha256=hashlib.sha256((root / 'stride_observations.csv').read_bytes()).hexdigest(),
        interpretation='Cumulative counters localize volume differences exactly at 900-second boundaries. Sampled heads and link flows cannot resolve internal transitions or establish causation.',
        accepted=False)
    (root / 'localization_summary.json').write_text(json.dumps(summary, indent=2))
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    hours = coarse.index / 3600
    axes[0].plot(hours, coarse.cso_m3, label='0.5 s maximum step')
    axes[0].plot(hours, fine.cso_m3, label='0.25 s maximum step')
    axes[0].set_ylabel('Cumulative CSO (m³)')
    axes[0].legend()
    axes[1].plot(hours, intervals.cumulative_difference_m3)
    axes[1].set_ylabel('Cumulative difference (m³)')
    axes[2].bar(hours, intervals.interval_difference_m3, width=.22)
    axes[2].set_ylabel('15-minute difference (m³)')
    axes[2].set_xlabel('Hours since simulation start')
    for ax in axes:
        ax.grid(alpha=.25)
    fig.suptitle('Failed TRAIN hydraulic diagnostic — coarse minus fine\nNative controls; cumulative all-four-outfall CSO; no controller-performance claim')
    fig.tight_layout()
    fig.savefig(root / 'localization.png', dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

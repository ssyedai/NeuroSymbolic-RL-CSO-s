"""Read-only cumulative observer replay of the fixed failed TRAIN diagnostic."""
import csv
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import time

from research.network_dll_probe import run_native, NodeStats, CSO_OUTFALLS, FT3_TO_M3


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prior', type=Path, default=Path('runs/hydraulic_validation_20261019/network_balance_bypass'))
    parser.add_argument('--out', type=Path, default=Path('runs/hydraulic_validation_20261019/stride_localization'))
    args = parser.parse_args()
    source, dest = args.prior, args.out
    dest.mkdir(parents=True, exist_ok=False)
    cfg = json.loads((source / 'run_config.json').read_text())
    assert cfg['split'] == 'train'
    dll = Path(cfg['engine_dll'])
    assert sha(dll) == cfg['dll_sha256']
    expected = {float(r['routing_seconds']): r for r in csv.DictReader((source / 'results.csv').open())}
    cfg.update(purpose='Read-only stride cumulative localization; no equation or scheduling change',
               routing_seconds=[.5, .25], expected_runs=2, budget_s=900,
               observer_source_sha256=sha(Path(__file__)),
               runner_source_sha256=sha(Path('research/network_dll_probe.py')))
    (dest / 'run_config.json').write_text(json.dumps(cfg, indent=2))
    records, verified = [], []
    deadline = time.monotonic() + 900
    for dt in cfg['routing_seconds']:
        path = dest / f'native_{dt:g}.inp'
        path.write_bytes((source / path.name).read_bytes())
        assert sha(path) == expected[dt]['input_sha256']

        def observe(lib, call, seconds):
            row = dict(routing_seconds=dt, seconds=seconds)
            for name in CSO_OUTFALLS:
                index = lib.swmm_getIndex(2, name.encode())
                if index < 0:
                    raise ValueError(name)
                value = C.c_double()
                call('swmm_getNodeTotalInflow', index, C.byref(value))
                row[f'cso_{name}_m3'] = value.value * FT3_TO_M3
            row['flood_m3'] = 0.
            for i in range(lib.swmm_getCount(2)):
                kind = C.c_int()
                call('swmm_getNodeType', i, C.byref(kind))
                if kind.value != 1:
                    stats = NodeStats()
                    call('swmm_getNodeStats', i, C.byref(stats))
                    row['flood_m3'] += stats.volFlooded * FT3_TO_M3
            for name in ('1360', '35440', '35442', '65'):
                value = C.c_double()
                index = lib.swmm_getIndex(2, name.encode())
                if index < 0:
                    raise ValueError(name)
                call('swmm_getNodeResult', index, 6, C.byref(value))
                row[name + '.head_ft'] = value.value
            for name in ('1360_B', '1360', '35444', 'W1', 'PUMP29@35445-3565'):
                index = lib.swmm_getIndex(3, name.encode())
                if index < 0:
                    raise ValueError(name)
                for field, suffix in ((0, 'flow_cfs'), (5, 'setting'), (6, 'target')):
                    value = C.c_double()
                    call('swmm_getLinkResult', index, field, C.byref(value))
                    row[f'{name}.{suffix}'] = value.value
            records.append(row)

        result = run_native(dll, path, deadline, stride_observer=observe)
        checks = {key: value == float(expected[dt][key]) for key, value in result.items()
                  if isinstance(value, (float, int))}
        verified.append(dict(routing_seconds=dt, exact_final_match=all(checks.values()), checks=checks,
                             result=result))
        with (dest / 'stride_observations.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        (dest / 'replay_verification.json').write_text(json.dumps(verified, indent=2))
        if not all(checks.values()):
            raise RuntimeError('Observer replay differs from prior final results')
        print(f'{dt:g}s: exact final match; {len(records)} observations saved', flush=True)


if __name__ == '__main__':
    main()

"""Replay unchanged saved TRAIN inputs using an explicitly instrumented DLL."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import time
from research.network_dll_probe import run_native


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prior', type=Path, required=True)
    p.add_argument('--dll', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--balance-bins', action='store_true')
    p.add_argument('--steps', nargs='+', type=float, choices=[.5,.25], default=[.5,.25])
    p.add_argument('--trace-config', type=Path)
    p.add_argument('--control-transitions', action='store_true')
    args = p.parse_args()
    cfg = json.loads((args.prior / 'run_config.json').read_text())
    if cfg['split'] != 'train':
        raise ValueError('TRAIN-only hydraulic diagnostic')
    expected = {float(r['routing_seconds']):r for r in csv.DictReader((args.prior/'results.csv').open())}
    args.out.mkdir(exist_ok=False)
    cfg.update(purpose='Logging-only full-event balance bins' if args.balance_bins else 'Logging-only internal transitions in localized intervals',
               engine_dll=str(args.dll.resolve()), dll_sha256=hashlib.sha256(args.dll.read_bytes()).hexdigest(),
               routing_seconds=args.steps, expected_runs=len(args.steps), budget_s=900,
               windows_seconds=[] if args.balance_bins else [[81000,85500],[112500,116100]],
               balance_bins=args.balance_bins, control_transitions=args.control_transitions,
               observer_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if args.trace_config:
        trace_cfg=json.loads(args.trace_config.read_text())
        cfg['windows_seconds']=trace_cfg['windows_seconds']
        cfg['trace_config']=trace_cfg
        cfg['trace_config_sha256']=hashlib.sha256(args.trace_config.read_bytes()).hexdigest()
    (args.out/'run_config.json').write_text(json.dumps(cfg,indent=2))
    (args.out/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    old = {key:os.environ.get(key) for key in ('SWMM_WINDOW_TRACE','SWMM_FAILURE_TRACE','SWMM_BALANCE_BINS','SWMM_CONTROL_TRACE')}
    rows = []
    deadline = time.monotonic()+900
    try:
        for dt in cfg['routing_seconds']:
            path = args.out/f'native_{dt:g}.inp'
            path.write_bytes((args.prior/path.name).read_bytes())
            assert hashlib.sha256(path.read_bytes()).hexdigest()==expected[dt]['input_sha256']
            os.environ['SWMM_WINDOW_TRACE']=str((args.out/f'windows_{dt:g}.csv').resolve())
            os.environ['SWMM_FAILURE_TRACE']=str((args.out/f'failures_{dt:g}.csv').resolve())
            if args.control_transitions:
                os.environ['SWMM_CONTROL_TRACE']=str((args.out/f'controls_{dt:g}.csv').resolve())
            if args.balance_bins:
                os.environ['SWMM_BALANCE_BINS']=str((args.out/f'balance_bins_{dt:g}.csv').resolve())
            start=time.monotonic()
            result=run_native(args.dll,path,deadline)
            checks={k:v==float(expected[dt][k]) for k,v in result.items() if isinstance(v,(int,float))}
            rows.append(dict(routing_seconds=dt,exact_final_match=all(checks.values()),checks=checks,
                             wall_seconds=time.monotonic()-start,result=result))
            (args.out/'replay_verification.json').write_text(json.dumps(rows,indent=2))
            if not all(checks.values()):raise RuntimeError('Logging changed final metrics')
            print(f'{dt:g}s exact match: {rows[-1]["wall_seconds"]:.1f}s',flush=True)
    finally:
        for key,value in old.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':
    main()

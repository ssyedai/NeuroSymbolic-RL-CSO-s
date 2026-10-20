"""Create a hash-verified local diagnostic archive; never label it a thesis release."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--evidence-root',type=Path,default=Path('runs/hydraulic_validation_20261019'))
    parser.add_argument('--engine-source',type=Path,default=Path('runs/hydraulic_validation_20261019/surface_transition_source'))
    parser.add_argument('--additional-source',type=Path,action='append',default=[])
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    paths=set()
    for folder in ('research','multistorm','tests','docs','configs','patches'):
        for p in Path(folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.md','.json','.csv','.txt','.yaml','.yml'}:
                paths.add(p)
    for pattern in ('README*','AGENTS.md','app.py','requirements*.txt','pyproject.toml','pytest.ini'):
        paths.update(p for p in Path('.').glob(pattern) if p.is_file())
    source=args.engine_source
    for tree in [source]+args.additional_source:
        paths.update(p for p in tree.rglob('*') if p.is_file() and '.git' not in p.parts)
    folders=('stride_localization','window_trace','balance_bins','upstream_trace','upstream_iteration',
             'trials200_05','surface_boundary_checks','surface_weir','surface_orifice','surface_reversing_verified',
             'network_surface_transition','network_balance_bypass',
             'surface_failure_attribution','surface_trials200_05','surface_trials200_025',
             'surface_stride_localization','surface_control_trace','tabular_before','tabular_after',
             'tabular_draining','tabular_draining_verified','tabular_draining_valid_scope',
             'integral_weir','integral_orifice','integral_reversing','network_integral_storage')
    base=args.evidence_root
    for folder in folders:
        paths.update(p for p in (base/folder).rglob('*') if p.is_file() and p.suffix in {'.csv','.json','.py','.png','.md','.gz'})
    for p in [base/'research_readiness.json',base/'current_verification_bundle.json',
              base/'surface_iteration_sensitivity.json',
              Path('runs/hydraulic_validation_20261017/environment_packages.json')]:
        if p.exists():paths.add(p)
    noaa=Path('runs/noaa_verification_20261017/detroit_city_airport')
    paths.update(p for p in noaa.rglob('*') if p.is_file() and p.suffix in {'.json','.csv','.txt'})
    manifest={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    note=('Blocked research checkpoint, not a completed thesis or validated controller. '
          'Includes current code, diagnostic source and compact numerical evidence. '
          'Excludes installed/built binaries, full rainfall archives, hydraulic binary outputs and legacy model checkpoints. '
          'Full simulation reproduction additionally needs the original model and guarded rainfall data. '
          'The candidate changes numerical surface allocation and the near-zero orifice law; it is not stock SWMM. '
          'See docs/conduit_surface_transition_20261019.md and the readiness JSON.\n')
    with zipfile.ZipFile(args.out,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(paths):z.write(p,p.as_posix())
        z.writestr('CHECKPOINT_MANIFEST.json',json.dumps(manifest,indent=2))
        z.writestr('CHECKPOINT_README.txt',note)
    with zipfile.ZipFile(args.out) as z:
        for name,digest in manifest.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError(name)
    result=dict(path=str(args.out),files=len(manifest),bytes=args.out.stat().st_size,
                sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(),all_entries_verified=True,
                thesis_complete=False,production_engine_adopted=False)
    args.out.with_suffix('.verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

"""Add a continuity-residual stopping check to the separate diagnostic solver."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(before):
    changes=[
        ('    double  weirSlope;', '    double  continuityResidual;       // ordinary-depth equation residual, ft3\n    double  weirSlope;'),
        ('        Xnode[i].sumdqdh = 0.0;', '        Xnode[i].continuityResidual = 0.0;\n        Xnode[i].sumdqdh = 0.0;'),
        ('        if (Xnode[i].converged == FALSE) return FALSE;',
         '        if (Xnode[i].converged == FALSE) return FALSE;\n        if (!(Xnode[i].continuityResidual <= 1.0e-6)) return FALSE;'),
        ('    // --- save new depth for node\n    Node[i].newDepth = yNew;',
         '''    // Diagnostic stopping check for the ordinary non-flooded update only.
    // No volume or depth is changed; reject an unconverged continuity equation.
    if (!isSurcharged && !isPonded && yNew < yMax && yNew > 0.0)
        Xnode[i].continuityResidual = fabs(surfArea * (yNew - yOld) - dV);
    // --- save new depth for node
    Node[i].newDepth = yNew;''')]
    after=before
    for old,new in changes:
        if after.count(old)!=1:
            raise ValueError('Unexpected continuity-check source: '+old)
        after=after.replace(old,new)
    return after


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    before=(args.source/'src/solver/dynwave.c').read_text()
    after=patch_source(before)
    shutil.copytree(args.source,args.out)
    (args.out/'src/solver/dynwave.c').write_text(after)
    (args.out/'continuity_check.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before/dynwave.c',tofile='after/dynwave.c')))
    (args.out/'continuity_check_config.json').write_text(json.dumps(dict(
        purpose='stricter local equation convergence; separate alternative-formulation diagnostic',
        continuity_residual_tolerance_ft3=1e-6,max_trials='unchanged',head_tolerance='unchanged',
        original_sha256=hashlib.sha256(before.encode()).hexdigest(),
        modified_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__=='__main__':
    main()

"""Separate final-head regulator check; restore constitutive-evaluation fields."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(before):
    function='''
static int finalRegulatorCheck(void)
{
    int i, k, good = TRUE;
    double raw, used;
    TLink savedLink;
    TOrifice savedOrifice;
    TWeir savedWeir;
    for (i=0; i<Nobjects[LINK]; i++)
    {
        if (Link[i].type != ORIFICE && Link[i].type != WEIR) continue;
        savedLink = Link[i];
        k = Link[i].subIndex;
        if (Link[i].type == ORIFICE) savedOrifice = Orifice[k];
        else savedWeir = Weir[k];
        used = Link[i].newFlow;
        raw = link_getInflow(i);
        Link[i] = savedLink;
        if (Link[i].type == ORIFICE) Orifice[k] = savedOrifice;
        else Weir[k] = savedWeir;
        if (!(fabs(raw-used) <= MAX(0.001, 0.001*MAX(fabs(raw),fabs(used)))))
            good = FALSE;
    }
    return good;
}
'''
    marker='int dynwave_execute(double tStep)'
    if before.count(marker)!=1:
        raise ValueError('Unexpected execution function')
    after=before.replace(marker,function+'\n'+marker)
    marker='        converged = converged && WeirFlowConverged;'
    if after.count(marker)!=1:
        raise ValueError('Missing existing flow check')
    return after.replace(marker,marker+'\n        if (!finalRegulatorCheck()) converged = FALSE;')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    before=(args.source/'src/solver/dynwave.c').read_text()
    after=patch_source(before)
    shutil.copytree(args.source,args.out)
    (args.out/'src/solver/dynwave.c').write_text(after)
    (args.out/'postcheck.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before/dynwave.c',tofile='after/dynwave.c')))
    (args.out/'postcheck_config.json').write_text(json.dumps(dict(
        scope='post-depth-update weir/orifice check with restored constitutive state',
        abs_tolerance_cfs=.001,relative_tolerance=.001,max_trials='unchanged',production_adoption=False,
        original_sha256=hashlib.sha256(before.encode()).hexdigest(),
        modified_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__=='__main__':
    main()

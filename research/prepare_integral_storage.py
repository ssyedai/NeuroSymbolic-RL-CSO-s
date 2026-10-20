"""Separate candidate using integrated storage volume in ordinary node balance."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    before=(a.source/'src/solver/dynwave.c').read_text(encoding='utf-8')
    helper='''
// Storage has a physical volume curve; integrate it instead of multiplying
// a single tangent area by the entire depth increment. Keep the adjoining
// conduit contribution frozen at this iteration, as in the existing update.
static double nodeBalanceIncrement(int node,double old,double last,double depth,double area)
{
    double extra;
    if(Node[node].type!=STORAGE) return area*(depth-old);
    extra=MAX(0.0,area-node_getSurfArea(node,last));
    return node_getVolume(node,depth)-node_getVolume(node,old)+extra*(depth-old);
}
'''
    anchor='// Diagnostic scalar solve for a storage-to-outfall weir contribution only.'
    assert before.count(anchor)==1
    after=before.replace(anchor,helper+'\n'+anchor,1)
    substitutions={
      'rlo=area*(lo-old)-dV+alpha*':'rlo=nodeBalanceIncrement(node,old,last,lo,area)-dV+alpha*',
      'rhi=area*(hi-old)-dV+alpha*':'rhi=nodeBalanceIncrement(node,old,last,hi,area)-dV+alpha*',
      'r=area*(mid-old)-dV+alpha*':'r=nodeBalanceIncrement(node,old,last,mid,area)-dV+alpha*',
      'if (Xnode[i].weirSlope > 0.0)':'if (Xnode[i].weirSlope > 0.0 || Node[i].type == STORAGE)',
      'dy = (surfArea * (yOld - yLast) + dV) / denom;':'dy = (dV - nodeBalanceIncrement(i,yOld,yLast,yLast,surfArea)) / denom;',
      'Xnode[i].continuityResidual = fabs(surfArea * (yNew - yOld) - dV);':'Xnode[i].continuityResidual = fabs(nodeBalanceIncrement(i,yOld,yLast,yNew,surfArea) - dV);'
    }
    for old,new in substitutions.items():
        if after.count(old)!=1:raise ValueError(f'Unexpected anchor: {old}')
        after=after.replace(old,new,1)
    shutil.copytree(a.source,a.out)
    (a.out/'src/solver/dynwave.c').write_text(after,encoding='utf-8')
    (a.out/'integral_storage.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True))),encoding='utf-8')
    (a.out/'integral_storage_config.json').write_text(json.dumps(dict(
        purpose='Experimental numerical conservation correction; no new discharge law or geometry',
        source=str(a.source.resolve()),before_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_sha256=hashlib.sha256(after.encode()).hexdigest(),
        scope='Ordinary storage update and storage/outfall bracket; no change to flooding or surcharge branches',
        production_adoption=False),indent=2),encoding='utf-8')


if __name__=='__main__':main()

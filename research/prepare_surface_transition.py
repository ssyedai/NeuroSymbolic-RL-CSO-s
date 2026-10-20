"""Separate forward-flow conduit surface-allocation continuity experiment."""
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
    p.add_argument('--keep-original',action='store_true')
    a=p.parse_args()
    before=(a.source/'src/solver/dwflow.c').read_text()
    after=before
    if not a.keep_original:
        old='''                    if ( ycMax - ycMin < FUDGE ) *fasnh = 0.0;
                    else *fasnh = (ycMax - y2) / (ycMax - ycMin);'''
        new='''                    // In this branch ycMin <= y2 < ycMax, so the denominator is positive.
                    // Match zero downstream allocation at the critical boundary and full allocation above.
                    *fasnh = (y2 - ycMin) / (ycMax - ycMin);'''
        assert after.count(old)==1
        after=after.replace(old,new)
        old='''        surfArea1 = (width1 + widthMid) * length / 4.;
        surfArea2 = (widthMid + width2) * length / 4. * fasnh;'''
        assert after.count(old)==1
        after=after.replace(old,old+'\n        surfArea1 *= (2.0 - fasnh); // join the doubled upstream critical allocation continuously')
    after+='''
// Diagnostic-only exported query of the actual compiled surface allocation.
// Caller opens and starts an explicit model; all touched link/conduit fields are restored.
__declspec(dllexport) int diag_surface(int j,double q,double y1,double y2,double* out)
{
    int k,n1,n2; double h1,h2; TLink saved; TConduit savedConduit;
    if(j<0 || j>=Nobjects[LINK] || Link[j].type!=CONDUIT) return 1;
    saved=Link[j];k=Link[j].subIndex;savedConduit=Conduit[k];
    n1=Link[j].node1;n2=Link[j].node2;
    h1=Node[n1].invertElev+Link[j].offset1+y1;
    h2=Node[n2].invertElev+Link[j].offset2+y2;
    out[0]=link_getYcrit(j,fabs(q));out[1]=link_getYnorm(j,fabs(q));
    findSurfArea(j,q,Conduit[k].modLength,&h1,&h2,&y1,&y2);
    out[2]=Link[j].surfArea1;out[3]=Link[j].surfArea2;out[4]=Link[j].flowClass;
    out[5]=y1;out[6]=y2;
    Link[j]=saved;Conduit[k]=savedConduit;return 0;
}
'''
    shutil.copytree(a.source,a.out)
    (a.out/'src/solver/dwflow.c').write_text(after)
    (a.out/'surface_transition.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True))))
    (a.out/'surface_transition_config.json').write_text(json.dumps(dict(
        purpose='Forward offset-conduit numerical surface-allocation transition; no production adoption',
        changed=not a.keep_original,scope='Forward flow between normal and critical depths; reverse-flow behavior unchanged',
        inherited='Rejected conduit-bypass candidate including alternative continuous near-zero orifice law',
        before_sha256=hashlib.sha256(before.encode()).hexdigest(),after_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__=='__main__':main()

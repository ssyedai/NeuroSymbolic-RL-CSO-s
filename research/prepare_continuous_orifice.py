"""Explicit alternative near-zero law, diagnostic only; never install as native."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(before):
    start=before.index("double orifice_getInflow(int j)\n")
    end=before.index("double orifice_getFlow(int j,",start)
    prefix,suffix=before[:start],before[end:]
    before=before[start:end]
    old="    if ( head <= FUDGE || y1 <= FUDGE ||"
    new="""    // Diagnostic formulation: continuous near-zero fully submerged SIDE flow.
    if ( head <= ((Orifice[k].type == SIDE_ORIFICE && f == 1.0 &&
                   h2 >= hcrown) ? 0.0 : FUDGE) || y1 <= FUDGE ||"""
    if before.count(old)!=1:
        raise ValueError('Unexpected orifice head guard')
    after=before.replace(old,new)
    old="    q = dir * orifice_getFlow(j, k, head, f, Link[j].hasFlapGate);"
    new=old+"""
    // Explicit changed law below FUDGE: linear in signed head; unchanged above.
    if (Orifice[k].type == SIDE_ORIFICE && f == 1.0 && h2 >= hcrown &&
        head > 0.0 && head < FUDGE)
    {
        q *= sqrt(head / FUDGE);
        Link[j].dqdh = fabs(q) / head;
    }
"""
    if after.count(old)!=1:
        raise ValueError('Unexpected orifice discharge evaluation')
    return prefix+after.replace(old,new)+suffix


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    before=(args.source/'src/solver/link.c').read_text()
    after=patch_source(before)
    shutil.copytree(args.source,args.out)
    (args.out/'src/solver/link.c').write_text(after)
    (args.out/'continuous_orifice.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='cutoff/link.c',tofile='continuous/link.c')))
    (args.out/'continuous_orifice_config.json').write_text(json.dumps(dict(
        status='alternative hydraulic formulation; diagnostic only; not production native',
        scope='fully submerged SIDE orifices below 0.0001 ft head difference',
        law='q = Cd*A*sqrt(2g/cutoff)*signed_head below cutoff; original above',
        rationale='remove verified no-root interval, not select improved CSO',
        original_sha256=hashlib.sha256(before.encode()).hexdigest(),
        changed_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__=='__main__':
    main()

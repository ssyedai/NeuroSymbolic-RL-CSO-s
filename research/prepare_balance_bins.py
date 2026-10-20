"""Aggregate final ordinary-node equation residuals in fixed 900-second bins."""
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
    before=(a.source/'src/solver/dynwave.c').read_text()
    after=before.replace('double  continuityResidual;', 'double signedResidual;\n    double  continuityResidual;',1)
    after=after.replace('#include "headers.h"', '''#include "headers.h"
#include <stdio.h>
typedef struct {double sum,absolute,maximum; long failed,steps;} BalanceBin;
static BalanceBin *BalanceBins=NULL;
static FILE *BalanceFile=NULL;
static long LastBalanceBin=0;
''',1)
    after=after.replace('    VariableStep = 0.0;', '''    VariableStep = 0.0;
    LastBalanceBin=0;
    if(getenv("SWMM_BALANCE_BINS")) {
        BalanceFile=fopen(getenv("SWMM_BALANCE_BINS"),"w");
        BalanceBins=(BalanceBin*)calloc(Nobjects[NODE],sizeof(BalanceBin));
        if(!BalanceFile || !BalanceBins) {report_writeErrorMsg(ERR_MEMORY,"balance bins");return;}
        fprintf(BalanceFile,"bin_start,bin_end,node,steps,failed,sum_signed_ft3,sum_absolute_ft3,max_absolute_ft3\\n");
    }''',1)
    after=after.replace('    FREE(Xnode);', '''    if(BalanceFile) fclose(BalanceFile);
    BalanceFile=NULL;
    FREE(BalanceBins);
    FREE(Xnode);''',1)
    after=after.replace('        Xnode[i].continuityResidual = 0.0;',
                        '        Xnode[i].continuityResidual = 0.0;\n        Xnode[i].signedResidual = 0.0;')
    old='''    if (!isSurcharged && !isPonded && yNew < yMax && yNew > 0.0)
        Xnode[i].continuityResidual = fabs(surfArea * (yNew - yOld) - dV);'''
    new='''    if (!isSurcharged && !isPonded && yNew < yMax && yNew > 0.0) {
        Xnode[i].signedResidual = surfArea * (yNew - yOld) - dV;
        Xnode[i].continuityResidual = fabs(surfArea * (yNew - yOld) - dV);
    }'''
    assert after.count(old)==1
    after=after.replace(old,new)
    anchor='    if ( !converged ) updateConvergenceStats();'
    after=after.replace(anchor,anchor+'''
    if(BalanceFile && BalanceBins) {
        int n; long bin=(long)ceil(NewRoutingTime/900000.0);
        if(bin!=LastBalanceBin && LastBalanceBin>0) {
            for(n=0;n<Nobjects[NODE];n++) {
                if(Node[n].type==OUTFALL) continue;
                fprintf(BalanceFile,"%ld,%ld,%s,%ld,%ld,%.17g,%.17g,%.17g\\n",
                    (LastBalanceBin-1)*900,LastBalanceBin*900,Node[n].ID,
                    BalanceBins[n].steps,BalanceBins[n].failed,BalanceBins[n].sum,
                    BalanceBins[n].absolute,BalanceBins[n].maximum);
            }
            memset(BalanceBins,0,Nobjects[NODE]*sizeof(BalanceBin));
        }
        LastBalanceBin=bin;
        for(n=0;n<Nobjects[NODE];n++) {
            if(Node[n].type==OUTFALL) continue;
            BalanceBins[n].steps++;
            BalanceBins[n].sum+=Xnode[n].signedResidual;
            BalanceBins[n].absolute+=Xnode[n].continuityResidual;
            BalanceBins[n].maximum=MAX(BalanceBins[n].maximum,Xnode[n].continuityResidual);
            if(Xnode[n].continuityResidual>1e-6) BalanceBins[n].failed++;
        }
    }
''',1)
    # Flush the last bin on close; the preceding bins flush at the next routing step.
    after=after.replace('    if(BalanceFile) fclose(BalanceFile);','''    if(BalanceFile && BalanceBins) {
        int n;
        for(n=0;n<Nobjects[NODE];n++) {
            if(Node[n].type==OUTFALL) continue;
            fprintf(BalanceFile,"%ld,%ld,%s,%ld,%ld,%.17g,%.17g,%.17g\\n",
                (LastBalanceBin-1)*900,LastBalanceBin*900,Node[n].ID,
                BalanceBins[n].steps,BalanceBins[n].failed,BalanceBins[n].sum,
                BalanceBins[n].absolute,BalanceBins[n].maximum);
        }
    }
    if(BalanceFile) fclose(BalanceFile);''',1)
    shutil.copytree(a.source,a.out)
    (a.out/'src/solver/dynwave.c').write_text(after)
    (a.out/'balance_bins.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True))))
    (a.out/'balance_bins_config.json').write_text(json.dumps(dict(
        purpose='Read-only ordinary-node residual sums; not physical mass loss',
        before_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__=='__main__':main()

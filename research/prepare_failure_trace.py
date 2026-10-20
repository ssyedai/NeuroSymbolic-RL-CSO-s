"""Read-only per-element attribution of final-iteration convergence failures."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(before):
    declarations='''
typedef struct {
    long head, continuity, flow;
    int currentFlowFailed;
    double currentResidual, maxContinuity, maxFlow;
} FailureRecord;
static FailureRecord *NodeFailure = NULL, *LinkFailure = NULL;
static long DiagSteps, DiagFailed, DiagPreFlowFailed;
'''
    after=before.replace('#include "headers.h"','#include "headers.h"\n#include <stdio.h>\n'+declarations,1)
    old='    VariableStep = 0.0;'
    new=old+'''
    DiagSteps = DiagFailed = DiagPreFlowFailed = 0;
    if (getenv("SWMM_FAILURE_TRACE"))
    {
        NodeFailure = (FailureRecord*)calloc(Nobjects[NODE], sizeof(FailureRecord));
        LinkFailure = (FailureRecord*)calloc(Nobjects[LINK], sizeof(FailureRecord));
        if (!NodeFailure || !LinkFailure)
        {
            FREE(NodeFailure); FREE(LinkFailure);
            report_writeErrorMsg(ERR_MEMORY, "Failure-trace allocation failed");
            return;
        }
    }
'''
    if after.count(old)!=1:
        raise ValueError('Unexpected initialization')
    after=after.replace(old,new)
    old='    FREE(Xnode);'
    new='''    FILE* diagnostic;
    int i;
    const char* path = getenv("SWMM_FAILURE_TRACE");
    if (path && NodeFailure && LinkFailure)
    {
        diagnostic = fopen(path, "w");
        if (diagnostic)
        {
            fprintf(diagnostic,"kind,id,head_failures,continuity_failures,final_flow_failures,max_continuity_ft3,max_flow_cfs,total_steps,unconverged_steps,pre_flow_failed_steps\\n");
            for (i=0;i<Nobjects[NODE];i++)
                if (Node[i].type != OUTFALL)
                    fprintf(diagnostic,"node,%s,%ld,%ld,0,%.17g,0,%ld,%ld,%ld\\n",
                        Node[i].ID,NodeFailure[i].head,NodeFailure[i].continuity,
                        NodeFailure[i].maxContinuity,DiagSteps,DiagFailed,DiagPreFlowFailed);
            for (i=0;i<Nobjects[LINK];i++)
                if (Link[i].type == ORIFICE || Link[i].type == WEIR)
                    fprintf(diagnostic,"link,%s,0,0,%ld,0,%.17g,%ld,%ld,%ld\\n",
                        Link[i].ID,LinkFailure[i].flow,LinkFailure[i].maxFlow,
                        DiagSteps,DiagFailed,DiagPreFlowFailed);
            fclose(diagnostic);
        }
    }
    FREE(NodeFailure); FREE(LinkFailure);
    FREE(Xnode);'''
    if after.count(old)!=1:
        raise ValueError('Unexpected close')
    after=after.replace(old,new)
    old='        if (!(fabs(raw-used) <= MAX(0.001, 0.001*MAX(fabs(raw),fabs(used)))))'
    new='''        if (LinkFailure)
        {
            LinkFailure[i].currentResidual = fabs(raw-used);
            LinkFailure[i].currentFlowFailed = !(fabs(raw-used) <= MAX(0.001, 0.001*MAX(fabs(raw),fabs(used))));
        }
'''+old
    if after.count(old)!=1:
        raise ValueError('Missing final-flow check')
    after=after.replace(old,new)
    old='    if ( !converged ) updateConvergenceStats();'
    new=old+'''
    if (NodeFailure && LinkFailure)
    {
        int n;
        DiagSteps++;
        if (!converged) DiagFailed++;
        if (!WeirFlowConverged) DiagPreFlowFailed++;
        for (n=0;n<Nobjects[NODE];n++)
        {
            if (Node[n].type == OUTFALL) continue;
            if (!Xnode[n].converged) NodeFailure[n].head++;
            if (!(Xnode[n].continuityResidual <= 1e-6)) NodeFailure[n].continuity++;
            NodeFailure[n].maxContinuity = MAX(NodeFailure[n].maxContinuity,Xnode[n].continuityResidual);
        }
        for (n=0;n<Nobjects[LINK];n++)
        {
            if (Link[n].type != ORIFICE && Link[n].type != WEIR) continue;
            if (LinkFailure[n].currentFlowFailed) LinkFailure[n].flow++;
            LinkFailure[n].maxFlow = MAX(LinkFailure[n].maxFlow,LinkFailure[n].currentResidual);
        }
    }
'''
    if after.count(old)!=1:
        raise ValueError('Missing exit')
    return after.replace(old,new)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    before=(args.source/'src/solver/dynwave.c').read_text()
    after=patch_source(before)
    shutil.copytree(args.source,args.out)
    (args.out/'src/solver/dynwave.c').write_text(after)
    (args.out/'failure_trace.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='before/dynwave.c',tofile='after/dynwave.c')))
    (args.out/'failure_trace_config.json').write_text(json.dumps(dict(
        purpose='Read-only exit attribution; no extra hydraulic evaluations',
        original_sha256=hashlib.sha256(before.encode()).hexdigest(),
        modified_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__=='__main__':
    main()

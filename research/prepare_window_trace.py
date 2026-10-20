"""Instrument final solver states in the two localized TRAIN intervals."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from research.prepare_failure_trace import patch_source


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    before = (args.source / 'src/solver/dynwave.c').read_text()
    after = patch_source(before)
    after = after.replace('static long DiagSteps, DiagFailed, DiagPreFlowFailed;',
        'static long DiagSteps, DiagFailed, DiagPreFlowFailed;\nstatic FILE *WindowFile = NULL;')
    after = after.replace('    VariableStep = 0.0;', '''    VariableStep = 0.0;
    if (getenv("SWMM_WINDOW_TRACE")) {
        WindowFile = fopen(getenv("SWMM_WINDOW_TRACE"), "w");
        if (WindowFile) fprintf(WindowFile,"seconds,dt,iterations,converged,kind,id,head1,head2,old_depth,depth,area,old_volume,volume,old_net,net,residual,flow,setting,target,head_converged\\n");
    }''', 1)
    after = after.replace('    FREE(NodeFailure); FREE(LinkFailure);\n    FREE(Xnode);',
        '    if (WindowFile) fclose(WindowFile);\n    WindowFile = NULL;\n    FREE(NodeFailure); FREE(LinkFailure);\n    FREE(Xnode);')
    anchor = '    if ( !converged ) updateConvergenceStats();'
    trace = '''
    if (WindowFile && ((NewRoutingTime >= 81000000.0 && NewRoutingTime <= 85500000.0) ||
                       (NewRoutingTime >= 112500000.0 && NewRoutingTime <= 116100000.0))) {
        int z, n1, n2;
        for (z=0; z<Nobjects[NODE]; z++) {
            if (strcmp(Node[z].ID,"1360") && strcmp(Node[z].ID,"35440") &&
                strcmp(Node[z].ID,"35442") && strcmp(Node[z].ID,"65")) continue;
            fprintf(WindowFile,"%.17g,%.17g,%d,%d,node,%s,%.17g,0,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,0,0,0,%d\\n",
                NewRoutingTime/1000.,tStep,Steps,converged,Node[z].ID,
                Node[z].invertElev+Node[z].newDepth,Node[z].oldDepth,Node[z].newDepth,
                MAX(Xnode[z].newSurfArea,MinSurfArea),Node[z].oldVolume,Node[z].newVolume,
                Node[z].oldNetInflow,Node[z].inflow-Node[z].outflow,
                Xnode[z].continuityResidual,Xnode[z].converged);
        }
        for (z=0; z<Nobjects[LINK]; z++) {
            if (strcmp(Link[z].ID,"1360") && strcmp(Link[z].ID,"1360_B") &&
                strcmp(Link[z].ID,"35444") && strcmp(Link[z].ID,"W1") &&
                strcmp(Link[z].ID,"Connection_2") && strcmp(Link[z].ID,"PUMP29@35445-3565")) continue;
            n1=Link[z].node1; n2=Link[z].node2;
            fprintf(WindowFile,"%.17g,%.17g,%d,%d,link,%s,%.17g,%.17g,0,0,0,0,0,0,0,%.17g,%.17g,%.17g,%.17g,0\\n",
                NewRoutingTime/1000.,tStep,Steps,converged,Link[z].ID,
                Node[n1].invertElev+Node[n1].newDepth,Node[n2].invertElev+Node[n2].newDepth,
                LinkFailure ? LinkFailure[z].currentResidual : -1.,Link[z].newFlow,Link[z].setting,Link[z].targetSetting);
        }
    }
'''
    assert after.count(anchor) == 1
    after = after.replace(anchor, anchor + trace)
    shutil.copytree(args.source, args.out)
    (args.out / 'src/solver/dynwave.c').write_text(after)
    (args.out / 'window_trace.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))))
    (args.out / 'window_trace_config.json').write_text(json.dumps(dict(
        purpose='Read-only final-iteration trace; no additional hydraulic evaluations',
        windows_seconds=[[81000,85500],[112500,116100]],
        before_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_sha256=hashlib.sha256(after.encode()).hexdigest()), indent=2))


if __name__ == '__main__':
    main()

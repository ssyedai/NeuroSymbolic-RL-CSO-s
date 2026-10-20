"""Add read-only all-event control-transition logging to a window-trace source."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    before = (a.source / 'src/solver/dynwave.c').read_text(encoding='utf-8')
    declaration = '''
static FILE *ControlFile = NULL;
static double *ControlSetting = NULL, *ControlTarget = NULL;
'''
    after = before.replace('static FILE *WindowFile = NULL;',
                           'static FILE *WindowFile = NULL;'+declaration, 1)
    init = '''
    if (getenv("SWMM_CONTROL_TRACE")) {
        int z;
        ControlSetting = (double*)calloc(Nobjects[LINK], sizeof(double));
        ControlTarget = (double*)calloc(Nobjects[LINK], sizeof(double));
        ControlFile = fopen(getenv("SWMM_CONTROL_TRACE"), "w");
        if (!ControlSetting || !ControlTarget || !ControlFile) {
            if (ControlFile) fclose(ControlFile);
            ControlFile = NULL;
            FREE(ControlSetting); FREE(ControlTarget);
            report_writeErrorMsg(ERR_MEMORY, "Control trace allocation/open failed");
            return;
        }
        /* Finite sentinel: upstream Release uses /fp:fast, which can invalidate NaN equality guards. */
        for (z=0;z<Nobjects[LINK];z++) ControlSetting[z]=ControlTarget[z]=-1.0;
        fprintf(ControlFile,"step_end_seconds,dt,id,kind,setting,target,prior_setting,prior_target,pre_head1,pre_head2,prior_flow\\n");
    }
'''
    anchor = '    VariableStep = 0.0;'
    assert after.count(anchor) == 1
    after = after.replace(anchor, anchor+init, 1)
    anchor = '    if (WindowFile) fclose(WindowFile);'
    assert after.count(anchor) == 1
    after = after.replace(anchor, '''    if (ControlFile) fclose(ControlFile);
    ControlFile = NULL;
    FREE(ControlSetting); FREE(ControlTarget);
'''+anchor, 1)
    trace = '''
    if (ControlFile) {
        int z,n1,n2;
        for(z=0;z<Nobjects[LINK];z++) {
            if (Link[z].type!=ORIFICE && Link[z].type!=WEIR && Link[z].type!=PUMP) continue;
            if (Link[z].setting==ControlSetting[z] && Link[z].targetSetting==ControlTarget[z]) continue;
            n1=Link[z].node1;n2=Link[z].node2;
            fprintf(ControlFile,"%.17g,%.17g,%s,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\\n",
                NewRoutingTime/1000.,tStep,Link[z].ID,Link[z].type,
                Link[z].setting,Link[z].targetSetting,ControlSetting[z],ControlTarget[z],
                Node[n1].invertElev+Node[n1].newDepth,Node[n2].invertElev+Node[n2].newDepth,Link[z].newFlow);
            ControlSetting[z]=Link[z].setting;ControlTarget[z]=Link[z].targetSetting;
        }
    }
'''
    anchor = '    initRoutingStep();'
    assert after.count(anchor) == 1
    after = after.replace(anchor, anchor+trace, 1)
    shutil.copytree(a.source, a.out)
    (a.out / 'src/solver/dynwave.c').write_text(after, encoding='utf-8')
    (a.out / 'control_trace.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True))), encoding='utf-8')
    (a.out / 'control_trace_config.json').write_text(json.dumps(dict(
        purpose='Read-only control changes before hydraulic iteration; no additional flow evaluations',
        source=str(a.source.resolve()), before_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_sha256=hashlib.sha256(after.encode()).hexdigest(),
        time_semantics='NewRoutingTime is step end; head/flow fields are pre-iteration; first states have -1 prior sentinel'),
        indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

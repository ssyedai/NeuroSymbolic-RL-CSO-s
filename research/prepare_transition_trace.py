"""Add read-only iteration logging to a separate baseline or candidate source."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(source):
    candidate = "static int     WeirFlowConverged;" in source
    slope = "Xnode[n].weirSlope" if candidate else "0.0"
    guard = "WeirFlowConverged" if candidate else "-1"
    declarations = '''
// Diagnostic logging only. Restricted to the isolated one-link S/O/W model.
static FILE* TransitionFile = NULL;
static int TransitionComputed;
static double TransitionH1, TransitionH2, TransitionPrior, TransitionRaw;
static double TransitionArea;
'''
    source = source.replace('#include "headers.h"', '#include "headers.h"\n#include <stdio.h>\n#include <string.h>\n'+declarations, 1)
    old = "    int converged;\n\n    // --- initialize"
    new = '''    int converged;
    const char* tracePath;
    int n;

    // --- initialize'''
    if source.count(old) != 1:
        raise ValueError("Unexpected execute declaration")
    source = source.replace(old, new)
    start = '''    tracePath = getenv("SWMM_TRANSITION_TRACE");
    TransitionFile = NULL;
    if (tracePath && Nobjects[LINK] == 1 && Link[0].type == ORIFICE &&
        strcmp(Link[0].ID, "W") == 0 &&
        (NewRoutingTime <= 5000.0 ||
         (NewRoutingTime >= 60000.0 && NewRoutingTime <= 62000.0)))
    {
        TransitionFile = fopen(tracePath, "a");
        if (TransitionFile) fseek(TransitionFile, 0, SEEK_END);
        if (TransitionFile && ftell(TransitionFile) == 0)
            fprintf(TransitionFile, "seconds,dt,iteration,computed,pre_head_s,pre_head_o,q_prior,q_raw,q_used,orifice_area,node_effective_area,old_depth,new_depth,old_net_inflow,net_inflow,head_converged,flow_guard,combined_converged,bypassed,setting,slope\\n");
    }
'''
    marker = "    // --- keep iterating until convergence"
    if source.count(marker) != 1:
        raise ValueError("Missing iteration loop")
    source = source.replace(marker, start+"\n"+marker)
    marker = "        initNodeStates();"
    source = source.replace(marker, "        TransitionComputed = 0;\n        TransitionH1 = TransitionH2 = TransitionPrior = TransitionRaw = TransitionArea = NAN;\n"+marker, 1)
    marker = "    qNew = link_getInflow(i);"
    raw = '''
    if (TransitionFile && i == 0)
    {
        TransitionComputed = 1;
        TransitionH1 = Node[Link[i].node1].newDepth + Node[Link[i].node1].invertElev;
        TransitionH2 = Node[Link[i].node2].newDepth + Node[Link[i].node2].invertElev;
        TransitionPrior = qLast;
        TransitionRaw = qNew;
        TransitionArea = Orifice[Link[i].subIndex].surfArea;
    }
'''
    if source.count(marker) != 1:
        raise ValueError("Ambiguous raw-flow evaluation")
    source = source.replace(marker, marker+raw)
    log = f'''        if (TransitionFile)
        {{
            n = Link[0].node1;
            fprintf(TransitionFile,
                "%.17g,%.17g,%d,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d,%d,%d,%d,%.17g,%.17g\\n",
                NewRoutingTime/1000.0, tStep, Steps, TransitionComputed,
                TransitionH1, TransitionH2, TransitionPrior, TransitionRaw,
                Link[0].newFlow, TransitionArea, MAX(Xnode[n].newSurfArea, MinSurfArea),
                Node[n].oldDepth, Node[n].newDepth, Node[n].oldNetInflow,
                Node[n].inflow-Node[n].outflow, Xnode[n].converged,
                {guard}, converged, Link[0].bypassed, Link[0].setting, {slope});
        }}
'''
    marker = "        Steps++;"
    if source.count(marker) != 1:
        raise ValueError("Ambiguous iteration increment")
    source = source.replace(marker, log+marker)
    source = source.replace("    return Steps;", "    if (TransitionFile) fclose(TransitionFile);\n    TransitionFile = NULL;\n    return Steps;", 1)
    return source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    before = (args.source/"src/solver/dynwave.c").read_text()
    after = patch_source(before)
    shutil.copytree(args.source, args.out)
    (args.out/"src/solver/dynwave.c").write_text(after)
    (args.out/"transition_trace.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile="original/dynwave.c", tofile="trace/dynwave.c")))
    (args.out/"transition_trace_config.json").write_text(json.dumps(dict(
        purpose="Read-only iteration trace; no extra hydraulic evaluations or equation changes",
        source_directory=str(args.source.resolve()), windows_seconds=[[0,5],[60,62]],
        before_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_sha256=hashlib.sha256(after.encode()).hexdigest()), indent=2))


if __name__ == "__main__":
    main()

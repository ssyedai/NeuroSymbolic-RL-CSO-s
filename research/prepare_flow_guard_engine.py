"""Prepare a separate experimental SWMM build with a weir-flow stopping check.

This changes convergence detection, not the hydraulic discharge equations,
relaxation parameter, iteration cap or production simulator.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(before):
    if "static const double OMEGA               = 0.5;" not in before:
        raise ValueError("Expected original damping; refuse to combine experiments")
    edits = [
        ("static double  Omega;", "static int     WeirFlowConverged; // diagnostic iteration residual flag\nstatic double  Omega;"),
        ("        initNodeStates();\n        findLinkFlows(tStep);\n        converged = findNodeDepths(tStep);",
         "        initNodeStates();\n        WeirFlowConverged = TRUE;\n        findLinkFlows(tStep);\n"
         "        converged = findNodeDepths(tStep);\n"
         "        converged = converged && WeirFlowConverged;"),
        ("            if ( !Link[i].bypassed ) findNonConduitFlow(i, dt);",
         "            // Recompute weirs even when the head-only bypass test passes.\n"
         "            if ( !Link[i].bypassed || Link[i].type == WEIR ) findNonConduitFlow(i, dt);"),
        ("    qNew = link_getInflow(i);\n    if ( Link[i].type == PUMP )",
         "    qNew = link_getInflow(i);\n"
         "    // Compare raw constitutive flow with the prior iteration's flow.\n"
         "    // 0.001 CFS absolute floor and 0.1 percent relative tolerance.\n"
         "    // Negated comparison rejects NaN as well as a large residual.\n"
         "    if ( Link[i].type == WEIR &&\n"
         "         !(fabs(qNew - qLast) <= MAX(0.001,\n"
         "             0.001 * MAX(fabs(qNew), fabs(qLast)))) )\n"
         "        WeirFlowConverged = FALSE;\n"
         "    if ( Link[i].type == PUMP )"),
    ]
    result = before
    for old, new in edits:
        if result.count(old) != 1:
            raise ValueError("Unexpected source; refuse ambiguous flow-guard patch")
        result = result.replace(old, new)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    before = (args.source/"src/solver/dynwave.c").read_text()
    after = patch_source(before)
    shutil.copytree(args.source, args.out)
    target = args.out/"src/solver/dynwave.c"
    target.write_text(after)
    (args.out/"diagnostic.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile="baseline/src/solver/dynwave.c",
        tofile="flow_guard/src/solver/dynwave.c")))
    (args.out/"diagnostic_config.json").write_text(json.dumps(dict(
        purpose="Experimental weir-flow convergence check; no production adoption",
        upstream_commit="27dc6990cda8bce21f6c16ddae631b37e7510ffc",
        relative_flow_tolerance=.001, absolute_flow_tolerance_cfs=.001,
        check="raw constitutive flow versus previous iteration, before relaxation",
        scope="all weirs; head-only bypass disabled for weirs",
        head_tolerance_and_iteration_caps="unchanged; original INP options",
        omega=.5, changed_file="src/solver/dynwave.c",
        original_source_hashes={str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in args.source.rglob("*") if p.is_file()},
        changed_sha256=hashlib.sha256(target.read_bytes()).hexdigest()), indent=2))


if __name__ == "__main__":
    main()

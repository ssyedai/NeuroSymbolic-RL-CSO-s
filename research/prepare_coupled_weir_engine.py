"""Experimental diagonal Newton storage update using local weir sensitivities.

No installed engine is changed. Preserve original hydraulic fixed points and
flow formulas; use a finite-difference Jacobian only to improve iteration.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from research.prepare_flow_guard_engine import patch_source as add_flow_guard


SLOPE_FUNCTION = """
// Diagnostic local Jacobian, evaluated serially in the non-conduit flow loop.
// Restore each perturbed depth; caller re-evaluates base flow to restore all
// link fields touched by link_getInflow. This never modifies discharge laws.
static void addWeirSlopes(int link)
{
    int side, node;
    double saved, lo, hi, qlo, qhi, slope;
    const double epsilon = 1.0e-7; // feet, diagnostic finite-difference increment
    for (side = 0; side < 2; side++)
    {
        node = (side == 0) ? Link[link].node1 : Link[link].node2;
        if (Node[node].type != STORAGE) continue;
        saved = Node[node].newDepth;
        lo = MAX(0.0, saved - epsilon);
        hi = saved + epsilon;
        Node[node].newDepth = lo;
        qlo = link_getInflow(link);
        Node[node].newDepth = hi;
        qhi = link_getInflow(link);
        Node[node].newDepth = saved;
        slope = (qhi - qlo) / (hi - lo);
        if (side == 1) slope = -slope;
        // Non-positive or NaN sensitivities do not stabilize this diagonal.
        if (slope > 0.0) Xnode[node].weirSlope += slope;
    }
}

"""


def patch_source(before):
    result = add_flow_guard(before)
    edits = [
        ("    double  sumdqdh;", "    double  weirSlope;                // local outgoing weir slope (CFS/ft)\n    double  sumdqdh;"),
        ("        Xnode[i].sumdqdh = 0.0;", "        Xnode[i].sumdqdh = 0.0;\n        Xnode[i].weirSlope = 0.0;"),
        ("void findNonConduitFlow(int i, double dt)", SLOPE_FUNCTION+"void findNonConduitFlow(int i, double dt)"),
        ("    qNew = link_getInflow(i);", "    if (Link[i].type == WEIR) addWeirSlopes(i);\n    qNew = link_getInflow(i);"),
        ("        dy = dV / surfArea;\n        yNew = yOld + dy;",
         "        dy = dV / surfArea;\n        yNew = yOld + dy;\n"
         "        // Diagonal Newton correction for the same continuity fixed point.\n"
         "        // Account for the existing relaxation of link flow after iteration 0.\n"
         "        if (Node[i].type == STORAGE && Xnode[i].weirSlope > 0.0)\n"
         "        {\n"
         "            denom = surfArea + 0.5 * dt * Xnode[i].weirSlope *\n"
         "                    ((Steps > 0) ? Omega : 1.0);\n"
         "            dy = (surfArea * (yOld - yLast) + dV) / denom;\n"
         "            yNew = yLast + dy;\n"
         "        }")
    ]
    for old, new in edits:
        if result.count(old) != 1:
            raise ValueError("Unexpected source for coupled-update patch")
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
        tofile="coupled/src/solver/dynwave.c")))
    (args.out/"diagnostic_config.json").write_text(json.dumps(dict(
        purpose="Experimental diagonal Newton storage/weir update; not production",
        upstream_commit="27dc6990cda8bce21f6c16ddae631b37e7510ffc",
        finite_difference_ft=1e-7, relative_flow_tolerance=.001, absolute_flow_tolerance_cfs=.001,
        scope="unsurcharged storage depth iteration with adjoining weirs; both link ends",
        hydraulic_formulas="unchanged", omega=.5, iteration_caps="unchanged",
        original_source_hashes={str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in args.source.rglob("*") if p.is_file()},
        changed_file="src/solver/dynwave.c", changed_sha256=hashlib.sha256(target.read_bytes()).hexdigest()), indent=2))


if __name__ == "__main__":
    main()

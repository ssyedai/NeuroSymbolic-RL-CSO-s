"""Expose diagnostic step size and convergence status on a separate engine."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def patch_source(before):
    if "static int     WeirFlowConverged;" not in before:
        raise ValueError("Expected the experimental regulator source")
    extra = '''
// Windows-only isolated diagnostic API. No hydraulic formula changes.
static int DiagConverged = -1;
__declspec(dllexport) int swmm_diagConverged(void) { return DiagConverged; }
__declspec(dllexport) int swmm_diagSetStep(double dt)
{
    if (Nobjects[NODE] != 2 || Nobjects[LINK] != 1 ||
        Link[0].type != ORIFICE || Nobjects[POLLUT] != 0 ||
        CourantFactor != 0.0 || !(dt >= 0.001 && dt <= 0.25)) return 1;
    RouteStep = dt;
    MinRouteStep = dt;
    return 0;
}
'''
    after = before.replace("static int     WeirFlowConverged;", extra+"\nstatic int     WeirFlowConverged;",1)
    if after.count("    return Steps;") != 1:
        raise ValueError("Unexpected dynamic-wave exit")
    return after.replace("    return Steps;", "    DiagConverged = converged;\n    return Steps;")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    before=(args.source/"src/solver/dynwave.c").read_text()
    after=patch_source(before)
    shutil.copytree(args.source,args.out)
    (args.out/"src/solver/dynwave.c").write_text(after)
    (args.out/"retry_api.patch").write_text("".join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile="original/dynwave.c",tofile="diagnostic/dynwave.c")))
    (args.out/"retry_api_config.json").write_text(json.dumps(dict(
        scope="isolated one-orifice cases only; no hydraulic equations changed",
        original_sha256=hashlib.sha256(before.encode()).hexdigest(),
        patched_sha256=hashlib.sha256(after.encode()).hexdigest()),indent=2))


if __name__ == "__main__":
    main()

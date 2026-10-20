"""Separate diagnostic extension to weirs/orifices and non-outfall end nodes."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from research.prepare_coupled_weir_engine import patch_source as coupled_patch


def patch_source(before):
    after = coupled_patch(before)
    changes = [
        ("if (Node[node].type != STORAGE) continue;", "if (Node[node].type == OUTFALL) continue;"),
        ("if (Node[i].type == STORAGE && Xnode[i].weirSlope > 0.0)", "if (Xnode[i].weirSlope > 0.0)"),
        ("if (Link[i].type == WEIR) addWeirSlopes(i);", "if (Link[i].type == WEIR || Link[i].type == ORIFICE) addWeirSlopes(i);"),
        ("if ( Link[i].type == WEIR &&", "if ( (Link[i].type == WEIR || Link[i].type == ORIFICE) &&"),
        ("if ( !Link[i].bypassed || Link[i].type == WEIR )", "if ( !Link[i].bypassed || Link[i].type == WEIR || Link[i].type == ORIFICE )"),
    ]
    for old, new in changes:
        if after.count(old) != 1:
            raise ValueError("Unexpected regulator-extension source")
        after = after.replace(old, new)
    return after


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
        tofile="regulator/src/solver/dynwave.c")))
    (args.out/"diagnostic_config.json").write_text(json.dumps(dict(
        purpose="Experimental regulator/junction coupling; no production adoption",
        upstream_commit="27dc6990cda8bce21f6c16ddae631b37e7510ffc", finite_difference_ft=1e-7,
        relative_flow_tolerance=.001, absolute_flow_tolerance_cfs=.001, omega=.5,
        scope="weirs and orifices; non-outfall endpoints; ordinary depth update only",
        discharge_equations_and_small_head_cutoff="unchanged", iteration_caps="unchanged",
        original_source_hashes={str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in args.source.rglob("*") if p.is_file()},
        changed_file="src/solver/dynwave.c", changed_sha256=hashlib.sha256(target.read_bytes()).hexdigest()), indent=2))


if __name__ == "__main__":
    main()

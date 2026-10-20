"""Add a read-only, bounded trace for the native 7M flow-split predicate.

The generated source is diagnostic only.  It records the values already held by
SWMM immediately after control evaluation and actuator movement, before the
hydraulic iteration for that step.  It does not call a flow function or modify
model state.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


DECLARATIONS = r'''
static FILE *PredicateFile = NULL;
static int PredicateNode = -1, PredicateConduit = -1, PredicateGate = -1;
static double PredicateStart = 0.0, PredicateEnd = 1.0e300;
'''


INITIALIZATION = r'''
    if (getenv("SWMM_PREDICATE_TRACE")) {
        const char *startText = getenv("SWMM_PREDICATE_START");
        const char *endText = getenv("SWMM_PREDICATE_END");
        PredicateNode = project_findObject(NODE, "35440");
        PredicateConduit = project_findObject(LINK, "35281_A");
        PredicateGate = project_findObject(LINK, "35281_B");
        if (startText) PredicateStart = atof(startText);
        if (endText) PredicateEnd = atof(endText);
        PredicateFile = fopen(getenv("SWMM_PREDICATE_TRACE"), "w");
        if (!PredicateFile || PredicateNode < 0 || PredicateConduit < 0 || PredicateGate < 0) {
            if (PredicateFile) fclose(PredicateFile);
            PredicateFile = NULL;
            report_writeErrorMsg(ERR_NAME, "7M predicate trace objects/file unavailable");
            return;
        }
        fprintf(PredicateFile,
            "step_end_seconds,dt,head_35440,flow_35281_A,gate_setting,gate_target,"
            "head_above_609_27,flow_above_231\n");
    }
'''


TRACE = r'''
    if (PredicateFile && NewRoutingTime/1000. >= PredicateStart &&
        NewRoutingTime/1000. <= PredicateEnd) {
        double predicateHead = Node[PredicateNode].invertElev + Node[PredicateNode].newDepth;
        double predicateFlow = Link[PredicateConduit].newFlow;
        fprintf(PredicateFile, "%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d,%d\n",
            NewRoutingTime/1000., tStep, predicateHead, predicateFlow,
            Link[PredicateGate].setting, Link[PredicateGate].targetSetting,
            predicateHead > 609.27, predicateFlow > 231.0);
    }
'''


CLOSE = r'''
    if (PredicateFile) fclose(PredicateFile);
    PredicateFile = NULL;
'''


def patch_source(before: str) -> str:
    """Return ``dynwave.c`` with the bounded observer inserted once."""
    if "static FILE *PredicateFile" in before:
        raise ValueError("Predicate trace already present")
    after = before

    declaration_anchor = "static TXnode* Xnode;                  // extended nodal information\n"
    if after.count(declaration_anchor) != 1:
        raise ValueError("No unique dynwave shared-state anchor")
    after = after.replace(declaration_anchor, declaration_anchor + DECLARATIONS, 1)

    init_anchor = "    VariableStep = 0.0;"
    if after.count(init_anchor) != 1:
        raise ValueError("No unique dynwave initialization anchor")
    after = after.replace(init_anchor, init_anchor + INITIALIZATION, 1)

    execute_anchor = "    initRoutingStep();"
    if after.count(execute_anchor) != 1:
        raise ValueError("No unique routing-step anchor")
    after = after.replace(execute_anchor, execute_anchor + TRACE, 1)

    close_anchor = "    FREE(Xnode);"
    if after.count(close_anchor) != 1:
        raise ValueError("No unique dynwave close anchor")
    after = after.replace(close_anchor, CLOSE + close_anchor, 1)
    return after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source_file = args.source / "src/solver/dynwave.c"
    before = source_file.read_text(encoding="utf-8")
    after = patch_source(before)
    shutil.copytree(args.source, args.out)
    output_file = args.out / "src/solver/dynwave.c"
    output_file.write_text(after, encoding="utf-8")
    (args.out / "predicate_trace.patch").write_text(
        "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))),
        encoding="utf-8",
    )
    (args.out / "predicate_trace_config.json").write_text(
        json.dumps(
            {
                "purpose": "Read-only 7M native-rule predicate trace",
                "source": str(args.source.resolve()),
                "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
                "objects": {"node": "35440", "conduit": "35281_A", "gate": "35281_B"},
                "thresholds": {"head_ft": 609.27, "flow_cfs": 231.0},
                "time_semantics": "Values are pre-hydraulic-iteration state after control evaluation and actuator movement",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

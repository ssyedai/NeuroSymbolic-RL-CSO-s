"""Machine-checkable research gates required before official v8 experiments."""
from __future__ import annotations

import json
from pathlib import Path


DEFAULT_HYDRAULIC_EVIDENCE = Path("runs/hydraulic_acceptance.json")


def assert_hydraulic_training_ready(path=DEFAULT_HYDRAULIC_EVIDENCE) -> dict:
    """Require independently generated evidence for the unchanged hydraulic gate.

    The marker is deliberately generated under ``runs/`` and is never shipped as
    a source-code assertion.  A future verification command must write it only
    after the complete four-outfall, true-native refinement study passes.
    """
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(
            "Official v8 experiments are blocked: runs/hydraulic_acceptance.json "
            "does not exist. The latest verified 0.5-to-0.25 s native refinement "
            "differs by 1.422%, above the unchanged 1% limit; the 0.125 s result "
            "reverses direction and differs from 0.25 s by 6.339%. Frozen controls "
            "pass at 0.238%, isolating native switching without authorizing a new "
            "reference. See docs/native_control_resolution_20261020.md.")
    evidence = json.loads(path.read_text())
    required_true = (
        "passed", "true_native_control", "complete_four_outfall_objective",
        "zero_flood_preserved", "thresholds_unchanged",
    )
    missing = [name for name in required_true if evidence.get(name) is not True]
    pct = float(evidence.get("refinement_difference_pct", float("inf")))
    limit = float(evidence.get("refinement_limit_pct", float("nan")))
    if missing or limit != 1.0 or pct > limit:
        raise RuntimeError(
            f"Invalid hydraulic acceptance evidence: false/missing={missing}, "
            f"difference={pct}, limit={limit}. Do not train or relax thresholds.")
    return evidence

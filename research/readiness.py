"""Machine-checkable research gates required before official v8 experiments."""
from __future__ import annotations

import json
from pathlib import Path
import sys


DEFAULT_HYDRAULIC_EVIDENCE = Path("runs/hydraulic_acceptance.json")
EXPLORATORY_STATUS = "exploratory_unverified_native_reference"


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


def experiment_status(exploratory: bool = False,
                      path=DEFAULT_HYDRAULIC_EVIDENCE) -> dict:
    """Require the formal gate, or return an explicit exploratory watermark.

    This never creates hydraulic evidence and never changes the 1% threshold.
    It only allows pipeline dry-runs after the user has explicitly requested an
    exploratory experiment.
    """
    try:
        evidence = assert_hydraulic_training_ready(path)
    except RuntimeError as exc:
        if not exploratory:
            raise
        status = dict(
            research_status=EXPLORATORY_STATUS,
            exploratory=True,
            hydraulic_gate_passed=False,
            hydraulic_blocker=str(exc),
        )
        print(
            "WARNING: EXPLORATORY ONLY. The native reference failed the fixed "
            "hydraulic check. Results are not valid performance evidence.",
            file=sys.stderr,
        )
        return status
    return dict(
        research_status="official_hydraulic_gate_passed",
        exploratory=False,
        hydraulic_gate_passed=True,
        hydraulic_evidence=evidence,
    )


def isolated_output(path, exploratory: bool, official_default: str) -> Path:
    """Keep exploratory artifacts away from official defaults and caches."""
    path = Path(path)
    if not exploratory:
        return path
    if path == Path(official_default):
        path = Path("runs/exploratory") / path.name
    if "exploratory" not in {part.lower() for part in path.parts}:
        raise ValueError(
            f"Exploratory output must be under a directory named exploratory: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    """Print a plain preflight result for people starting an experiment."""
    try:
        evidence = assert_hydraulic_training_ready()
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(
        "PASS: hydraulic/native-control evidence accepted "
        f"({evidence['refinement_difference_pct']:.3f}% <= "
        f"{evidence['refinement_limit_pct']:.3f}%)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

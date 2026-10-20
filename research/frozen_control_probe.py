"""Run a bounded frozen-control hydraulic refinement diagnostic.

This removes the complete ``[CONTROLS]`` body from already-generated TRAIN
inputs.  SWMM therefore retains each link's initial target for the event:
orifices remain open and pumps remain off for this model.  The experiment is
diagnostic only and must not be used as the native reference.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import time

import pandas as pd

from research.fine_routing import summarize
from research.network_dll_probe import run_native


def freeze_controls(text: str) -> str:
    pattern = re.compile(
        r"(?ms)^(\[CONTROLS\]\s*\r?\n)(.*?)(?=^\[[^\]\r\n]+\]\s*$)"
    )
    match = pattern.search(text)
    if not match:
        raise ValueError("Expected one bounded CONTROLS section")
    body = match.group(2)
    if "RULE " not in body.upper():
        raise ValueError("CONTROLS section does not contain native rules")
    replacement = match.group(1) + "; intentionally empty: frozen-control diagnostic\n\n"
    frozen, count = pattern.subn(replacement, text, count=1)
    if count != 1 or re.search(r"(?mi)^\s*RULE\s+", pattern.search(frozen).group(2)):
        raise ValueError("Failed to freeze native rules")
    return frozen


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _transition_counts(path: Path) -> dict[str, int]:
    with path.open(newline="", encoding="utf-8") as stream:
        return {
            name: count
            for name, count in pd.Series(row[2] for row in csv.reader(stream) if row and row[0] != "step_end_seconds")
            .value_counts()
            .items()
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--resume", action="store_true", help="Resume only completed rows in an existing diagnostic directory")
    args = parser.parse_args()
    if len(args.input) < 2:
        parser.error("Provide at least two generated TRAIN inputs")
    if args.resume:
        if not args.out.is_dir():
            raise ValueError("--resume requires an existing diagnostic directory")
    else:
        args.out.mkdir(parents=True, exist_ok=False)

    inputs = []
    for source in args.input:
        source = source.resolve()
        run_config = source.parent / "run_config.json"
        if not run_config.exists() or json.loads(run_config.read_text(encoding="utf-8")).get("split") != "train":
            raise ValueError(f"Refuse non-TRAIN or untracked generated input: {source}")
        match = re.search(r"native_([0-9.]+)\.inp$", source.name)
        if not match:
            raise ValueError(f"Cannot recover routing step from {source.name}")
        inputs.append((float(match.group(1)), source))
    inputs.sort(reverse=True)

    config = {
        "purpose": "Frozen-control hydraulic refinement; diagnostic only",
        "split": "train",
        "controller": "empty [CONTROLS]; initial orifice/pump states retained",
        "native_reference": False,
        "dll": str(args.dll.resolve()),
        "dll_sha256": _sha256(args.dll),
        "routing_seconds": [step for step, _ in inputs],
        "inputs": [],
        "acceptance": "unchanged max(1 m3, 1%); continuity <= 1%",
    }
    results_path = args.out / "results.csv"
    rows = pd.read_csv(results_path).to_dict("records") if args.resume and results_path.exists() else []
    completed_steps = {float(row["routing_seconds"]) for row in rows}
    deadline = time.monotonic() + 1800
    prior_trace = os.environ.get("SWMM_CONTROL_TRACE")
    try:
        for step, source in inputs:
            destination = args.out / f"frozen_{step:g}.inp"
            expected_text = freeze_controls(source.read_text(encoding="utf-8"))
            if args.resume and destination.exists() and destination.read_text(encoding="utf-8") != expected_text:
                raise ValueError(f"Existing frozen input differs on resume: {destination}")
            destination.write_text(expected_text, encoding="utf-8")
            config["inputs"].append(
                {
                    "source": str(source),
                    "source_sha256": _sha256(source),
                    "frozen": str(destination),
                    "frozen_sha256": _sha256(destination),
                }
            )
            if step in completed_steps:
                prior_rows = [row for row in rows if float(row["routing_seconds"]) == step]
                if len(prior_rows) != 1:
                    raise ValueError(f"Resume requires exactly one completed row for {step:g} s")
                prior = prior_rows[0]
                if (
                    prior.get("split") != "train"
                    or prior.get("case") != "frozen_all_open_pumps_off"
                    or prior.get("input_sha256") != _sha256(destination)
                ):
                    raise ValueError(f"Completed row does not match frozen input: {step:g} s")
                continue
            trace = args.out / f"frozen_{step:g}_controls.csv"
            os.environ["SWMM_CONTROL_TRACE"] = str(trace.resolve())
            began = time.monotonic()
            row = {
                "storm_id": "USC00200230_20100719__T10",
                "split": "train",
                "case": "frozen_all_open_pumps_off",
                "routing_seconds": step,
                "input_sha256": _sha256(destination),
                **run_native(args.dll, destination, deadline),
            }
            row["wall_seconds"] = time.monotonic() - began
            row["control_transition_counts"] = json.dumps(_transition_counts(trace), sort_keys=True)
            rows.append(row)
            pd.DataFrame(rows).to_csv(args.out / "results.csv", index=False)
            print(
                f"dt={step:g} CSO={row['cso_total']:.6f} flood={row['flood_total']:.6f} "
                f"continuity={row['routing_error_pct']:.6f}% runtime={row['wall_seconds']:.1f}s",
                flush=True,
            )
    finally:
        if prior_trace is None:
            os.environ.pop("SWMM_CONTROL_TRACE", None)
        else:
            os.environ["SWMM_CONTROL_TRACE"] = prior_trace

    summary_config = {
        "routing_seconds": config["routing_seconds"],
        "expected_runs": len(inputs),
    }
    summary = summarize(rows, summary_config)
    summary["interpretation"] = (
        "Passing isolates the native switching controller as the refinement failure; "
        "it does not authorize this fixed policy as a reference."
    )
    (args.out / "run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

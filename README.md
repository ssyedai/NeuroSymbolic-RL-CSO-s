# NeuroSymbolic RL for Combined-Sewer Overflow Control

This repository couples EPA SWMM with a topology-aware, safety-constrained SAC
controller for seven sewer gates. The research objective is lexicographic:

1. prevent nodal-flood regression relative to the INP's native controls;
2. minimize untreated discharge at all four confirmed CSO outfalls;
3. use available storage before overflow and maximize treated discharge.

The implementation evaluates observed and amplified historical storms against
the same storm's true native control and a flood-feasible hindsight optimum.
Children of a parent event always remain in the parent's temporal split.

## Current verified status

The software and experiment guards pass, but **official training is intentionally
blocked by the unchanged hydraulic acceptance gate**. On the fixed TRAIN storm,
the best verified 0.5-to-0.25-second native-routing comparison differs by
**1.422%**, above the pre-registered **1%** limit. Native zero-deadband rules also
switch 600 versus 914 times at those resolutions. No repository record provides
the physical PLC scan interval, gate deadbands, or pump dwell times needed to
justify a corrected native controller.

Do not create `runs/hydraulic_acceptance.json` manually. It is evidence, not a
configuration switch. Details are in
[`docs/coupled_endpoint_verification_20261020.md`](docs/coupled_endpoint_verification_20261020.md)
and [`docs/training_readiness_20261020.md`](docs/training_readiness_20261020.md).
The exact operational information needed to resolve the gate is listed in
[`docs/control_spec_data_request.md`](docs/control_spec_data_request.md).
The shared Syed code, old model, rainfall files, notebook, and truncated report
are assessed in
[`docs/legacy_syed_code_audit_20261021.md`](docs/legacy_syed_code_audit_20261021.md).

## Installation and verification

Windows PowerShell:

```powershell
py -3.11 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements-windows-tested.txt
.\.venv-win\Scripts\python.exe -m pytest -q
```

Linux/macOS:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=. .venv/bin/python -m pytest -q
```

Run the research preflight separately:

```powershell
.\.venv-win\Scripts\python.exe -m research.readiness
```

It exits with code 2 and a plain `BLOCKED` message until valid hydraulic
evidence exists. Do not bypass it by creating the evidence file manually.

The v7 golden behavior remains the
default; research changes are opt-in.

## Explicit exploratory workflow

The repository can run an isolated exploratory pipeline while the hydraulic
gate is unresolved. This is useful for checking code, runtime, and data flow;
it is **not** evidence that a controller improves the real system. Exploratory
files carry `research_status=exploratory_unverified_native_reference` and
`hydraulic_gate_passed=false`, use a separate baseline-cache tag, stay under
directories named `exploratory`, and cannot be loaded by official commands.
The fixed safety and validation limits are not changed.

Run the short end-to-end check in Windows PowerShell:

```powershell
.\scripts\run_exploratory_pipeline.ps1 -Mode smoke
```

After the smoke run is sound, the same entry point can execute the full
train/validation preprocessing screens and the 300-episode one-seed pilot:

```powershell
.\scripts\run_exploratory_pipeline.ps1 -Mode full `
  -RunName exploratory_v8_pilot_s0
```

Neither command evaluates test storms. Formal test evaluation, multi-seed
claims, and protocol freezing remain blocked until the native hydraulic gate
passes. The full mode is computationally expensive because hindsight search
runs hundreds of SWMM episodes per train/validation storm.

The executed smoke result and its G3 failure diagnosis are documented in
[`docs/exploratory_execution_20261021.md`](docs/exploratory_execution_20261021.md).
The opt-in `v8_actionmask` follow-up resolves the intervention-accounting
ambiguity, but it also fails G3 because CSO, flooding safety, and cost do not
improve. A later native-rule/timing diagnostic improves CSO direction but fails
the unchanged flooding and total-overflow screens at both 15- and 5-minute
control intervals. Those variants are blocked from training. See
[`docs/nativeprior_timing_diagnostic_20261021.md`](docs/nativeprior_timing_diagnostic_20261021.md).
Do not start `-Mode full` from these results.

## Experiment sequence

After the hydraulic gate is independently passed without changing its threshold:

```powershell
# Rebuild full four-outfall native onset and controllability evidence.
.\.venv-win\Scripts\python.exe -m research.onset_table `
  --rain-dir data/useful/rain_real_full `
  --events data/useful/rain_real_full/events.csv

.\.venv-win\Scripts\python.exe -m research.run_controllability `
  --rain-dir data/useful/rain_scenarios `
  --split-manifest data/useful/rain_scenarios/splits.json

.\.venv-win\Scripts\python.exe -m research.run_optimize_rules `
  --rain-dir data/useful/rain_scenarios `
  --split-manifest data/useful/rain_scenarios/splits.json

# One-seed pilot. Test rainfall is not loaded by this process.
.\.venv-win\Scripts\python.exe -m multistorm.train_multi `
  --rain-dir data/useful/rain_scenarios `
  --split-manifest data/useful/rain_scenarios/splits.json `
  --variant v8 --diet D2_ladder100 --physical-rain --real-only `
  --theta-path runs/theta.json --episodes 300 --seed 0 `
  --run-name v8_pilot_s0
```

Test evaluation is deliberately a separate, post-freeze process:

```powershell
git tag protocol-v1
.\.venv-win\Scripts\python.exe -m multistorm.evaluate_checkpoint `
  --run runs/v8_pilot_s0 --splits test --protocol-tag protocol-v1 --repeat-check
```

Training cannot read the test split. Checkpoint selection is always
safety-feasible for v8, and official evaluation uses cumulative cubic metres at
outfalls `54`, `65`, `54_B`, and `65_B`.

## Repository map

- `app.py`: frozen v7 environment plus opt-in research hooks.
- `multistorm/`: agents, complete overflow accounting, metrics, training, and evaluation.
- `research/`: scenario generation, physical diagnostics, controllability, and rule calibration.
- `configs/v8_network.json`: local topology/geometry provenance bound to the canonical INP hash (not published with the source-only repository).
- `tests/`: golden compatibility, numerical diagnostics, safety, leakage, and resume tests.
- `docs/`: methodology, audit findings, protocol, and verification reports.

Generated runs, checkpoints, rainfall catalogs, SWMM INP files, and derived
network/configuration tables are intentionally not published. They remain in
the local research workspace; a fresh clone must receive these authorized
assets separately before running hydraulic experiments or training.

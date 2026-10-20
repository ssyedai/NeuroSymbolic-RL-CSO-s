# Fine-step hydraulic validation — 11 October 2026

This extends `hydraulic_validation_20261011.md`. These are numerical diagnostics on three TRAIN T10 parents, not evidence of RL superiority. No validation or test rainfall is used. The original INP, v7 defaults, rainfall splits and flood safety tolerances remain unchanged.

## Design fixed before the runs

`research.fine_routing` compares maximum routing steps of 1, 0.5 and 0.25 seconds. Each study includes original native gate control and static half-open gates on parents 2010-05-21, 2010-06-04 and 2010-07-19, plus gate 3530 closed on the first parent: 21 simulations. All retain native pump safeguards. Gate travel times and the 900-second external decision interval are preserved.

The default solver profile uses 8 iterations and a 0.005 ft head tolerance. A separate accuracy experiment uses 40 iterations and 0.0001 ft, retaining original rule evaluation at every routing step. These are experimental profiles, not adopted production settings. The routing minimum is `min(0.5, requested_step)` seconds. Numeric `ROUTING_STEP` values are seconds in the verified SWMM 5.2.4 parser; fractional seconds must not be inserted into an integer `hh:mm:ss` parser.

Each experiment records its configuration before simulations, guards rainfall hashes, refuses to overwrite results, runs one SWMM process and has a 30-minute limit. Partial results are written after every episode. Complete runs contain cumulative volumes, per-outfall CSO, continuity, runtime and sampled actual/target gate and pump positions. The tighter-solver experiment also preserves per-node flood volumes and peak depths.

The **new numerical screening criteria**, recorded before the first experiment, require both adjacent refinements to satisfy:

- Absolute nodal flooding difference at most 1 m³.
- CSO and total-overflow differences each at most the larger of 1 m³ or 1% of the finer result.
- Absolute routing continuity error at most 1% at both resolutions.

These are screening criteria for numerical reliability, not altered G0–G3 thresholds or a relaxed flood non-regression rule. Passing three-parent diagnostics would still not certify the full research protocol.

## Default solver: failed

All 21 runs completed in `runs/hydraulic_validation_20261011/fine_routing_v2`. Only **5 of 14** adjacent comparisons pass. The first attempt (`fine_routing`) failed during initialization before any diagnostic episode; its failure record points to the corrected run.

For the first parent, native flooding changes from 3.96 to 3.57 to **79.14 m³** as the routing step decreases. Fixed half-open and gate-3530-closed results on this parent are stable with native pumps retained. However, on the third parent fixed half-open flooding changes from **45.54 to 111.90 to 433.35 m³**. The final case has **7.49%** routing continuity error. Hence neither small steps alone nor the first parent's stable fixed-gate results certify this model.

## Tighter solver: also failed

All 21 runs completed in `fine_tight_solver`. Again only **5 of 14** adjacent comparisons pass. Worst absolute routing continuity error is **3.02%**, compared with 7.49% for the default solver. Lower maximum error does not establish convergence.

The first parent's native 0.25-second flooding falls to **2.95 m³**, but its 0.5-second continuity error is **1.91%**. On the third parent, native CSO is **4,489.03, 1,429.12 and 1,510.23 m³** at 1, 0.5 and 0.25 seconds. Fixed half-open flooding is **5.13, 129.26 and 386.60 m³**. Thus adopting the single favorable 1-second controlled result would be unjustified.

Per-node evidence gives a concrete follow-up: at 0.25 seconds, the third parent's controlled flooding includes **246.98 m³ at 3529_A** and **118.42 m³ at 3529**, immediately upstream of bypass gate 35291_B. Earlier mild-case flooding is concentrated at JCT-2114 downstream of the Puritan–Fenkell pumps. Neither region may be ignored in a safety shield. These observations locate the symptoms; they do not establish that the physical geometry is wrong.

The native pump rules, storage/conduit connections, orifice flows and downstream boundary conditions need targeted hydraulic diagnosis. SWMM also reports a raised crest for 35291_B and minimum elevation drops for Connection/Connection_2; these are existing model warnings, not proof of the cause. Do not silently change geometry, suppress flooding, or calibrate a controller to exploit numerical errors.

The comparison figure and machine-readable summary are in `runs/hydraulic_validation_20261011/fine_comparison/`. Both profiles are shown, including unfavorable cases. The figure is descriptive, not a confidence interval or independent-event significance test.

## Fixed-rule-cadence probe: also failed

Six additional runs in `fixed_rule_probe` keep rule evaluation at one second while varying routing resolution. This changes the controller timing and is **not** a replacement for original native control. The preselected cases are the first parent's native gates and the third parent's fixed half-open gates; the same numerical screen is used.

Only **1 of 4** adjacent comparisons passes. First-parent flooding is **3.89, 3.62 and 57.73 m³**; third-parent controlled flooding is **27.28, 250.18 and 442.32 m³**. The latter 0.25-second case has **7.32%** continuity error and **6.15% of routing steps not converging**, according to the preserved SWMM report. Fixing rule cadence alone is not sufficient. The reports also show oscillatory flow in fixed-command gate links, so distinguishing actual hydraulic oscillation from numerical error requires examining routing-step flows and heads, not just 15-minute commands.

**Decision after all 48 simulations:** no tested profile is certified numerically reliable. Stop before onset rebuilding, rule calibration, or full training. The next diagnostic should trace heads, link flows, pump actions and residuals around 3529/3529_A, 3530/3530_B, the storage connections, and JCT-2114. Preserve the original geometry and native comparator while testing a documented numerical correction. A physical geometry/boundary change requires model evidence; do not infer it from a desirable CSO percentage.

## Source verification

The pinned solver source is commit `27dc6990cda8bce21f6c16ddae631b37e7510ffc` (OWA v5.2.4). Copies of `project.c`, `datetime.c` and `dynwave.c` are preserved with the earlier hydraulic source files.

- [Input option parsing](https://github.com/pyswmm/Stormwater-Management-Model/blob/27dc6990cda8bce21f6c16ddae631b37e7510ffc/src/solver/project.c): numeric routing steps are seconds; rule time uses an integer-second time parser.
- [Dynamic-wave iterations](https://github.com/pyswmm/Stormwater-Management-Model/blob/27dc6990cda8bce21f6c16ddae631b37e7510ffc/src/solver/dynwave.c): iterations stop at head convergence or the trial limit; the engine supports sub-second routing, down to a 0.001-second minimum.

## Reproduction

Use fresh output directories; the diagnostic refuses overwrites.

```powershell
.\.venv-win\Scripts\python.exe -m research.fine_routing --out runs/fine_repeat
.\.venv-win\Scripts\python.exe -m research.fine_routing --tight-solver --out runs/tight_repeat
.\.venv-win\Scripts\python.exe -m research.fine_routing --fixed-rule-second --timing-probe --out runs/timing_repeat
.\.venv-win\Scripts\python.exe -m research.report_fine_routing runs/fine_repeat runs/tight_repeat --out runs/convergence_figure
.\.venv-win\Scripts\python.exe -m pytest -q
```

Original native rules remain the primary reference. A fixed rule cadence, if tested, is a separately labelled changed-controller diagnostic and cannot silently replace that reference. Large training and onset rebuilds remain blocked until the simulation is reliable; no claim of better-than-literature performance is supported by these diagnostics.

Validation after implementation: **62 tests passed**, including the v7 golden trajectory and new option-patching/convergence-screen tests. Removed three generated files belonging to an inactive process (1,231,340 bytes), after checking their absolute paths and saving SHA-256 hashes in `runs/hydraulic_validation_20261011/cleanup_orphans.csv`. Diagnostic evidence, source data and model files are retained.

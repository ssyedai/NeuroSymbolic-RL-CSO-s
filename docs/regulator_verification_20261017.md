# Regulator convergence verification — 2026-10-17

The experimental regulator update is **not adopted**. It passes 48/48 isolated steady-flow cases but fails both full-network routing-refinement comparisons. Zero flooding alone does not establish trustworthy control results. Production training remains blocked on numerical validation.

## Candidate and scope

`research/prepare_regulator_engine.py` extends the prior coupled storage/weir update to orifices and non-outfall junction endpoints. It adds flow-aware iteration checks, prevents head-only bypass of these links, and uses finite-difference outgoing-flow sensitivity in the ordinary nodal depth update. The original damping, discharge equations, small-head cutoff, iteration cap and head tolerance remain unchanged. This is an experimental solver change, not an RL improvement or a validated replacement for SWMM.

The separate source/build and all raw evidence are retained under `runs/hydraulic_validation_20261016/`; that directory records the execution date. No installed DLL or original physical model was replaced. Each simulation runs serially in one process. No test-split data were used.

## Isolated verification

The existing 24-case weir matrix passes 24/24. Independent rechecking confirms matching original/candidate input hashes and the original acceptance decisions.

`research/orifice_reproduction.py` adds 24 synthetic, rain-free, steady fully submerged orifice cases: inflows 5/65 CFS, junction/storage endpoints, SLOT/EXTRAN, and 1/0.5/0.25-second routing. The analytical reference uses Cd 0.4, area 7 × 14.14 square feet and gravity 32.2 ft/s². References at or below SWMM's 0.0001-foot head cutoff are explicitly rejected; these cases therefore do **not** verify crossing that cutoff or reversing flow.

Acceptance remains late-time maximum flow error ≤1% of reference flow, absolute integrated volume error ≤1%, absolute routing continuity error ≤1%, and zero flooding. Original engine: 20/24 pass. Candidate: 24/24 pass. Original failures are the three 5-CFS junction/SLOT resolutions and the 65-CFS junction/SLOT 1-second case.

The independent comparison script checks complete case coverage, finite values, matched input hashes and recomputed decisions. Evidence: `orifice_comparison/summary.json`, `orifice_baseline/`, `orifice_regulator/`, and `weir_regulator/`. The original engine passes 36/48 across both matrices; the candidate passes 48/48. This is limited numerical verification under steady boundaries.

## Full-network transfer fails

The same fixed TRAIN storm, `USC00200230_20100719__T10`, was simulated with native gates/pumps, physical rainfall, SLOT, 40 trials and 0.0001-foot head tolerance. All three generated input hashes match the preceding coupled-weir probe. Complete 72-hour simulations produced:

- 1 second: CSO 4740.918192 m³; flooding 0; routing error −1.380450%; nonconverging steps 22.05%.
- 0.5 second: CSO 4357.981096 m³; flooding 0; routing error −1.035833%; nonconverging steps 13.91%.
- 0.25 second: CSO 4109.487505 m³; flooding 0; routing error −0.792812%; nonconverging steps 21.93%.

Total undesired overflow equals CSO here because nodal flooding is zero. All discharge occurs at 65 in these runs; accounting still includes all four confirmed untreated outfalls.

Adjacent CSO differences are 382.937095 m³ (8.79% of the finer result) and 248.493591 m³ (6.05%). Both exceed the unchanged tolerance of max(1 m³, 1% of the finer result). The two coarser runs also exceed the 1% continuity limit. Result: **0/2 comparisons pass**. Evidence: `network_regulator_probe/results.csv`, `summary.json`, per-run INP/RPT files and `run_config.json`.

The 0.25-second report still ranks 1360_B highest in flow instability (index 36), followed by 35444 (11) and W1 (10). Largest local continuity errors include 35441 (+5.03%), 3545 (+2.42%) and 1360 (−1.53%). These rankings guide diagnosis; they do not establish a unique cause. Outfall node nonconvergence labels must not be interpreted as causal attribution because this experimental global flow check and existing node flags have different semantics.

## Next diagnostic boundary

The prior coupled-engine routing trace (`coupled_gate_trace/`) shows rapid reversals at 1360_B despite an unchanged gate target. The steady isolated matrix does not cover unsteady head differences near zero. The next bounded numerical experiment should prescribe changing boundary heads through the small-head cutoff and reversal, verify final-head flow residuals and volume balance, and compare original/candidate engines on identical inputs. Do not alter the physical cutoff, relax acceptance thresholds, select a favorable resolution, or treat lower numerical CSO as learned-policy improvement.

No new G0–G3 approval, protocol freeze, thesis superiority claim or cleanup of research evidence follows from these experiments.

Regression validation: `.venv-win/Scripts/python.exe -m pytest -q` completed with **70 passed**, including golden compatibility and new analytical-reference/fail-closed verification tests.

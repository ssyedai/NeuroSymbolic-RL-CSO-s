# Residual attribution after the conduit surface-transition repair

The full-network hydraulic gate remains failed. This diagnostic identifies remaining numerical failures; it does not establish controller performance or authorize training.

## Exact replay

Read-only node residual bins and final-flow failure counters were added to the separate surface-transition candidate. The 0.5 and 0.25 second simulations reproduce every recorded numeric final metric exactly, using byte-identical TRAIN inputs and the same 288 calls to `swmm_stride(900)`. Their runtimes were 145.344 and 262.7 seconds. All four untreated outfalls are included. No test events were used.

At 0.5 seconds, 148,652 of 518,400 steps fail the combined stopping checks. Storage 35440 fails continuity on 141,617 steps, junction 1360 on 106,278, and storage 35442 on 31,681. Gate 1360_B fails its final-head flow check on 92,166 steps. Counts overlap and must not be added as independent failures.

At 0.25 seconds, 184,335 of 1,036,800 steps fail. The corresponding continuity counts are 175,368, 117,957, and 4,083. Gate 1360_B has 88,747 final-flow failures. Thus smaller time steps reduce the failure fraction but do not eliminate the residual problem.

## Effect on the verified upstream cycle

For the 0.5-second simulation, the sum of absolute qualified continuity residuals before 82,800 seconds changes as follows:

- Junction 3517: 2182.618485 to 0.000830 ft³.
- Junction 3528: 2714.982894 to 36.522316 ft³.
- Junction 3534: 1849.094992 to 2.605237 ft³.
- Junction 3536: 2097.801027 to 5.111349 ft³.

These sums measure residuals in the solver's discrete nodal equation. They are not measured water losses, and cannot be directly subtracted from CSO volume. Their decrease supports the specific surface-transition repair, but does not explain the entire remaining network discrepancy.

## Remaining numerical question

The current node update uses a diagonal regulator slope. The storage-to-outfall bracket solves one weir contribution with other contributions held fixed; it is not a simultaneous solution for junction 1360 and storages 35440/35442. Strong coupling near the small-head orifice regime is therefore a candidate explanation for slow iteration, not yet a proven cause of the CSO discrepancy.

The completed bounded diagnostic increased MAX_TRIALS from 40 to 200 while preserving equations, native controls, rainfall, head tolerance, and the 1% time-step acceptance criterion. Byte comparisons confirm that MAX_TRIALS is the only input change in each matched case.

At 0.5 seconds, CSO is 3881.484684 m³, flooding is zero, routing error is -0.600236%, and nonconverging steps fall from 28.68% to 4.20%. CSO changes by only -0.433050 m³ relative to 40 iterations. Runtime is 202.516 seconds.

At 0.25 seconds, CSO is 3802.639402 m³, flooding is zero, routing error is -0.525224%, and nonconverging steps fall from 17.78% to 4.18%. CSO changes by -17.409018 m³ relative to 40 iterations. Runtime is 358.953 seconds.

The matched 200-iteration refinement difference is **78.845283 m³ (2.073436%)**, exceeding the unchanged 38.026394 m³ limit. CSO and total undesired overflow fail; flooding and routing-error checks pass. The 1-second 200-iteration case was not run because the required finest pair already fails. This does not establish a pass for either the complete refinement sequence or the hydraulic gate.

**Decision: reject the larger iteration budget as a sufficient remedy.** The existing candidate remains unadopted. Under AGENTS.md section 4.9, references, controllability, calibration, training and test evaluation remain blocked. A smaller fraction of unconverged steps does not demonstrate accurate CSO volumes.

The largest storage-35440 residual bins in the 0.5-second replay occur around 58–60 hours; earlier localization of the preceding candidate found major overflow discrepancies around 23 and 31.5 hours. That earlier localization must be repeated on the current candidate before claiming the same source. The next investigation should align cumulative CSO, control transitions, conduit regimes and endpoint residuals in those current-candidate divergence windows, then test a targeted repair. A simultaneous endpoint solve remains a hypothesis, not a demonstrated solution.

## Reproduction and evidence

`research.prepare_failure_trace` and `research.prepare_balance_bins` generate the instrumented source. `research.run_window_trace` records exact replay checks. `research.report_surface_attribution` refuses to summarize unless both replays match, and writes `runs/hydraulic_validation_20261019/surface_failure_attribution/attribution_summary.json`.

The instrumented DLL is under `surface_diagnostic_build`; source and patches are preserved under `surface_failure_source` and `surface_diagnostic_source`. No installed engine or model file was replaced. The 90 software tests pass independently of the hydraulic gate.

The matched iteration runs are in `surface_trials200_05` and `surface_trials200_025`. `research.report_iteration_sensitivity` checks that only MAX_TRIALS changed, applies the original limits, and writes `surface_iteration_sensitivity.json` with evidence hashes. No controller-performance, novelty or literature-superiority claim follows from these diagnostics.

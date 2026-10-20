# Forward-conduit surface transition: verification and rejection

**The candidate is rejected for production use: neither network refinement comparison passes. Training and later thesis experiments remain blocked.** The installed engine and original model are unchanged.

## Verified mechanism

Six logging-only replays (two overflow-window runs, two full-event residual-bin runs, one upstream-window run and one iteration trace) exactly reproduce their original 12 numeric final metrics. These comparisons establish recorded-output equivalence, not equality of every internal state.

At 79,239.5 seconds, junction 3528 enters a repeating four-iteration cycle. Incoming conduits 35171 and 35271 switch between downstream-critical (enum 6) and subcritical (enum 3) flow. The effective nodal area changes between 2234.926 and 12278.813 square feet. The final continuity residual is 69.245674 cubic feet. The final four head values reproduce those four iterations earlier within 9.44e-12 feet. This happens before CSO begins.

In the pinned `dwflow.c`, for forward flow with a downstream offset, the transition fraction between the smaller and larger normal/critical depths is `(ycMax-y2)/(ycMax-ycMin)`. The subcritical downstream surface allocation is multiplied by that fraction. At the lower boundary, the critical branch gives zero downstream area while the subcritical fraction approaches one. At the upper boundary the fraction approaches zero and then returns to the default one above the band. The upstream critical allocation is twice the corresponding subcritical allocation. Direct compiled queries confirm finite jumps at both boundaries.

A separate 200-iteration diagnostic at 0.5 seconds reduced nonconverging steps from 28.94% to 4.38%, but CSO changed only from 4110.206305 to 4098.401137 cubic metres. Routing error was -0.712639%, and large upstream residuals persisted. This was a single-resolution sensitivity experiment, not a convergence certificate. Once the explicit branch mechanism was identified, the paired cap-only experiment was superseded by the transition candidate.

## Candidate and direct checks

The candidate uses `f=(y2-ycMin)/(ycMax-ycMin)` within the existing forward transition band, whose denominator is strictly positive. Downstream allocation becomes `base_area2*f`; upstream allocation becomes `base_area1*(2-f)`. These join the critical branch at the lower boundary and ordinary subcritical allocation at the upper boundary. The numerical surface-allocation model changes; no extra physical storage is claimed. Reverse-flow behavior is not extended. The conduit momentum formula and physical geometry remain unchanged.

The candidate inherits the rejected conduit-bypass formulation, including the alternative continuous near-zero SIDE-orifice law, regulator checks, node continuity check and storage/outfall bracket solve. It is not stock SWMM.

Separate reference and candidate DLLs expose a read-only query of their compiled surface-allocation function. Checks use actual conduits 35171 and 35271, representative flows from the failed trace and depths 1e-7 feet either side of both boundaries. All six groups pass: four boundary checks and two groups of unchanged outside-band/reverse-flow controls. Original jumps exceed one square foot (5973.882 at the lower 35171 boundary); candidate jumps are below the declared 0.1-square-foot limit. This is a branch-continuity test, not a transient conduit validation.

The existing 24 steady-weir, 24 steady-orifice and 12 reversing-orifice cases pass: **60/60**. An initial reversing-suite invocation failed before simulation because its prior directory lacked a `candidate/` subdirectory. The corrected invocation used the original synthetic inputs and passed 12/12; the failed setup record is retained separately.

## Full-network decision

The fixed TRAIN storm `USC00200230_20100719__T10` used unchanged native rules and byte-identical physical-rain inputs at three maximum routing steps:

- 1 second: CSO 3802.124691 cubic metres, flooding zero, routing error -0.535215%, nonconverging steps 31.77%.
- 0.5 seconds: CSO 3881.917734 cubic metres, flooding zero, routing error -0.604832%, nonconverging steps 28.68%.
- 0.25 seconds: CSO 3820.048420 cubic metres, flooding zero, routing error -0.523176%, nonconverging steps 17.78%.

The adjacent differences are **79.793043 cubic metres (2.06%)** and **61.869314 cubic metres (1.62%)**. Both fail the unchanged limit of max(1 cubic metre, 1% of the finer result). Flooding and routing-error criteria pass. All CSO is at outfall 65; total undesired overflow equals CSO here because flooding is zero. Simulation runtime totals approximately 468 seconds, within the 900-second budget.

The finer discrepancy is smaller than the preceding 3.20%, but this does not constitute acceptance. The local discontinuity and its continuous replacement are verified; remaining network sensitivity is unresolved. No candidate is installed, no references are rebuilt, and no training or test-set evaluation follows. This is the measured stop condition required by AGENTS.md section 4.9. A transient conduit/junction verification and investigation of remaining regulator failures are needed before adoption.

## Evidence and scope

Evidence under `runs/hydraulic_validation_20261019/`: `window_trace/`, `balance_bins/`, `upstream_trace/`, `upstream_iteration/`, `trials200_05/`, `surface_boundary_checks/`, `surface_weir/`, `surface_orifice/`, `surface_reversing_verified/`, and `network_surface_transition/`. Corresponding source folders preserve patches and configurations. `research.prepare_surface_transition` produces the candidate; `research.verify_surface_transition` queries the compiled implementations. One simulation process ran at a time, retaining the INP internal thread setting.

Software regression verification: **90 tests passed**, including golden compatibility. These are distinct from the 60 hydraulic cases and six compiled boundary-check groups. Original physical-model calibration limits and prior test exposure remain unchanged. Later thesis stages remain incomplete; no literature-superiority or novelty claim is made. See `docs/internal_balance_diagnosis_20261019.md` for time-localized residual evidence and `docs/literature_positioning_20261019.md` for the targeted literature update.

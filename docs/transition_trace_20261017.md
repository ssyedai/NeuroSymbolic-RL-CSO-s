# Internal transition trace — 2026-10-17

Read-only instrumentation confirms that **head convergence alone can accept a large flow mismatch**, while the experimental flow-aware solver still accepts time steps after exhausting its iteration budget. No hydraulic equation was changed in this investigation.

## Verification and scope

Four 600-second isolated runs replay the existing junction/storage cutoff-crossing cases at 0.25-second routing, once per baseline/candidate engine. These are synthetic fixed-gate cases, not rainfall scenarios or controller evaluations. All **2399 sampled routing states per run and every recorded system total match the corresponding uninstrumented run exactly**. Inputs are byte-identical. Independent trace DLLs leave the installed engine unchanged.

`research/prepare_transition_trace.py` adds only logging to separate source copies. It records existing raw flow evaluations rather than calling the hydraulic functions again. Logging is restricted to the one-orifice S/O/W reproduction and routing times 0–5 s and 60–62 s: 29 steps per run. Fields include iteration index, heads before the raw flow calculation, prior/raw/used flow, orifice area, effective nodal area, depth before/after the time step, old/current net inflow, head/flow/combined convergence flags, bypass status, gate setting and candidate slope.

`research/run_transition_trace.py` verifies exact hydraulic equivalence. `research/report_transition_trace.py` checks iteration ordering and aligns final outfall heads with recorded routing states (time conversion tolerance 1e-7 s). It derives branch labels from the logged raw flow and computes the final-head constitutive residual without evaluating or mutating the live engine.

The canonical evidence is `runs/hydraulic_validation_20261017/transition_trace_v2/`: configuration and source snapshots, `equivalence.csv`, raw iteration logs, annotated logs, per-step exit records and `analysis.json`. The initial `transition_trace/` attempt had repeated CSV headers on reopening append-mode files; v2 corrects header placement. Both attempts preserved hydraulic outputs, but only v2 is used for the analysis. Source patches and build configurations are retained beside the run directory.

## First transition: 1.5 seconds

The first iteration evaluates a head gap near −0.0000833 ft and obtains zero raw flow. The outfall boundary is updated during the node-depth stage; the next iteration sees the gap near −0.0001000 ft. Floating-point values just outside the cutoff produce raw reverse flow **−3.177243 CFS**.

In the baseline junction case, relaxation turns this into **−1.588621 CFS** and the depth update moves the gap to **+0.007801 ft**. The following raw flow is **+28.063142 CFS**. Existing reversal handling clamps the used flow to **+0.001 CFS**, after which subsequent iterations swing between forward and reverse branches with much larger raw flows. This is a computed transition sequence, not a changing gate command.

The candidate initially holds the gap closer to the cutoff, but retains relaxed nonzero flow when the next raw evaluation is zero. For example, −1.588621 is halved to −0.794311 and then −0.397155 CFS. The junction subsequently crosses to forward flow and invokes the same reversal clamp. In the storage case, repeated halving and re-entry into the flowing branch can prevent the flow guard from settling before the iteration cap.

## Exit behavior in the recorded windows

- Baseline junction: 12/29 steps reach the 40-iteration cap; 17 declare convergence. Maximum final-head residual among declared-converged exits is **118.729941 CFS**.
- Baseline storage: all 29 steps declare convergence after two iterations. Maximum final-head residual is **1.603078 CFS**.
- Candidate junction: 2/29 steps reach the cap; 27 declare convergence. Maximum residual among those declared-converged exits is **0.031570 CFS**. Successive converged time steps can still alternate flow direction, so iteration convergence does not establish temporal convergence.
- Candidate storage: 3/29 steps reach the cap; 26 declare convergence. Maximum residual among declared-converged exits is **0.002893 CFS**. At 60.00, 60.25 and 60.50 s the solver exits at the cap with head convergence true and flow convergence false; residuals are **0.905502**, **1.858576** and **2.689339 CFS** respectively.

For a concrete baseline failure at 60.00 s, raw junction flow is approximately **−118.732678 CFS**, but the used flow is **−0.001 CFS** and the solver declares head convergence. The final head gap remains about **−0.139646 ft**. The flow-aware guard prevents this particular false acceptance in the candidate, but the full 600-second crossing cases still fail the preceding diagnostic.

Counts and maxima here apply only to the two recorded windows. They must not be substituted for whole-run nonconvergence percentages or full-network performance.

## Surface-area hypothesis corrected

The logged orifice computational area switches between **0.02 ft²** in the cutoff branch and **0 ft²** in the fully open flowing branch. The pinned `xsect.c::xsect_getWofY` returns zero width for `RECT_CLOSED` at exactly full depth; the physical opening width must not be substituted for this computational width.

Despite that switch, the effective junction area remains **12.566 ft²**, its minimum-area floor. The storage case remains **24231.285 ft²**. Thus a large effective-area jump does **not** explain these isolated transitions. This qualifies the previous area-switch hypothesis; other gate openings or network configurations are not covered by that conclusion.

## Decision and next technical step

Do not change the discharge law or adopt either solver configuration on this evidence. Two checks are now clearly distinct: (1) acceptance of an iteration after the final head update, and (2) stability across successive time steps. The current source continues after the iteration cap, even when the candidate's flow flag is false.

The next bounded experiment should test explicit rejection/retry of unconverged steps, with state restoration and post-update flow-residual verification, on the isolated reproduction first. Merely increasing the iteration cap or applying more damping is not supported as a fix by these traces. Even successful retries must then demonstrate routing-step convergence; the candidate's alternation across converged time steps remains a separate concern. No new training, test-split evaluation or thesis improvement claim follows.

Regression validation: **74 tests passed**, including golden compatibility and a new test ensuring declared head convergence does not hide a final-head flow mismatch in the trace analysis.

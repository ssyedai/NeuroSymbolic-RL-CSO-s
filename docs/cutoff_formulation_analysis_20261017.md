# Cutoff equation analysis and alternative formulation — 2026-10-17

**The failed isolated storage step has no exact branch-consistent solution under the original cutoff.** A separate continuous near-zero formulation removes this mathematical gap. It improves the unsteady diagnostic, but still fails two of twelve water-balance checks when combined with a final-head convergence check. It is not adopted and does not authorize full-network training.

## Why retrying could not guarantee success

Let `g = H_new − H_tail_new`, storage area `A = 24231.285 ft²`, cutoff `e = 0.0001 ft`, and `K = 0.4 × 7 × 14.14 × sqrt(64.4)`. The fully submerged, fully open discharge law is zero for `|g| ≤ e`, otherwise `q(g) = K sign(g) sqrt(|g|)`. With no lateral inflow or losses, the constant-area trapezoidal storage equation is:

`g + alpha q(g) = b`, where `alpha = dt/(2A)` and `b = H_old − H_tail_new − alpha q_old`.

On the zero-flow branch, the left side spans `[-e,e]`. The negative-flow branch approaches `−e − alpha K sqrt(e)` from below but cannot attain it, because the flowing branch requires `g < −e`. The positive-flow branch similarly begins strictly above `e + alpha K sqrt(e)`. Therefore two nonempty intervals of `b` have no solution. This is a discontinuity in the equation, not merely a poor iteration starting point.

At the final rejected storage attempt:

- `dt = 0.001953125 s`.
- `b = −0.00010005510813255726 ft`.
- Reverse-flow limit: `−0.0001001280483457435 ft`.
- Zero-flow limit: `−0.0001000000000000000 ft`.

The target lies strictly between these limits. The one-sided balance residuals are approximately **−0.001767435 ft³** and **+0.001335341 ft³**. A numerical root finder must not interpret that sign jump as a root. The gap is much larger than floating-point roundoff at these heads.

The proof applies to the isolated constant-area storage discretization and recorded accepted predecessor, not every Detroit node or every time step. It does not exclude approximate solutions at finite tolerances. `research/cutoff_root.py` produces the hashed certificate in `runs/hydraulic_validation_20261017/root_certificate/`.

## Explicit alternative, separate from the physical reference

`research/prepare_continuous_orifice.py` creates a separate engine with the below-threshold law `q = K g / sqrt(e)` for fully submerged SIDE orifices, retaining the original square-root law above `e`. The two branches are continuous and monotone. Consequently `g + alpha q(g)` is continuous and strictly increasing, and the isolated scalar equation has a unique root for every finite target `b`.

This is a **changed hydraulic formulation**, not an invisible numerical repair. In particular, a small head gap inside the former dead band now produces nonzero flow. The derivative used inside this interval is changed consistently. Other orifice regimes and the weir equations remain unchanged. No installed DLL, original INP, native control rule or production default is replaced.

The unsteady verification uses the same 12 physical inputs as the prior matrix, with two endpoint types, two boundary amplitudes and three routing steps. The constitutive reference now uses the declared alternative law; numerical tolerances, water-balance criterion and flooding criterion remain unchanged. Comparing those results is a formulation diagnostic, not a CSO reduction attributable to a controller.

## Results and remaining failure

Continuous law with the prior regulator iteration: **10/12 pass**. Storage crossing cases at 1 and 0.5 s fail final-head flow residuals: **0.260649** and **0.075264 CFS**, against the unchanged 0.05 CFS limit.

`research/prepare_postcheck_engine.py` then adds a final-head flow check after node depths are updated. It temporarily evaluates each weir/orifice at the updated state, restores its link and subtype fields, and requires residual ≤max(0.001 CFS, 0.1% of flow). Existing iteration caps and head tolerance are unchanged. This is a separate convergence-check diagnostic on the continuous formulation.

With that check, **all 12 final-head flow checks pass**, but **only 10/12 complete numerical checks pass**. The remaining failures are junction crossing cases:

- 1 s: balance residual **+0.050953 ft³**, gross throughput **2.382598 ft³**, allowed residual approximately **0.023826 ft³**.
- 0.25 s: balance residual **−0.085141 ft³**, gross throughput **0.894240 ft³**, allowed residual **0.01 ft³**.

The limits are unchanged: max(0.01 ft³, 1% of gross throughput). Small normalized system continuity percentages do not override these absolute/throughput failures. No further runs are advanced on the assumption that this candidate is validated. A residual check alone does not establish conservative nodal accounting or time-step convergence.

Evidence is in `runs/hydraulic_validation_20261017/continuous_probe/` and `continuous_post_probe/`, including input hashes, DLL/source hashes, configurations, raw traces, reports and case-level results. Source modifications and build records remain in the corresponding source/build directories. The next hydraulic investigation is the relationship between junction minimum computational area and reported storage/accounting in the isolated model; any proposed fix must preserve physical geometry and be independently validated.

## Effect on the thesis execution sequence

Fresh native references, onset/controllability studies, calibrated rules, pilot training, full training and held-out comparisons remain dependent on a validated hydraulic formulation. They have not been run on the failing candidate. Prior TEST exposure remains disclosed; validation 2021–2022 and test 2023–2026 remain as selected by the user. Extreme-return-period claims remain suspended until the NOAA table is verified. No claim of superiority over literature is established by solver diagnostics.

Final regression validation: **79 passed**. A local, hash-verified 90-file synthetic evidence archive is available at `runs/hydraulic_validation_20261017/cutoff_review_evidence.zip`; it contains the pre-packaging report snapshot, inputs, traces and patches, but no original rainfall, full network or installed engine. Nothing was sent externally. The remaining execution dependencies are recorded in `docs/thesis_execution_remaining_20261017.md`.

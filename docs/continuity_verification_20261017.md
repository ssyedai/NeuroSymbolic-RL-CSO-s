# Junction continuity verification — 2026-10-17

The isolated junction water-accounting discrepancy is resolved in the separate diagnostic formulation: **60/60 isolated cases pass their original acceptance criteria**. This is not yet approval for production hydraulics or training. The formulation includes the explicitly disclosed continuous near-zero orifice law; it must not be presented as unchanged SWMM.

## Finding and change

The existing stopping criteria checked changes in head and agreement between link flow and the final head. These did not require the nodal continuity equation itself to be satisfied. With the candidate's diagonal update and relaxation, small head changes and acceptable constitutive flow could coexist with a residual in the volume equation that accumulated over steps.

`research/prepare_continuity_engine.py` adds the check

`abs(surface_area × (new_depth − old_depth) − 0.5 × dt × (old_net_inflow + new_net_inflow)) ≤ 1e-6 ft³`.

It applies to the ordinary non-surcharged, non-ponded depth update at nodes away from dry/flooded bounds. Other branches retain their existing treatment. The check changes convergence detection, not node depths, reported storage volumes, physical geometry or mass-accounting totals. It tightens the stopping criterion; the 40-trial cap, head tolerance, existing flow check and external acceptance limits are unchanged. Hitting the cap can still return an unresolved step, so independent checks remain necessary. Per-node legacy convergence statistics do not separately attribute this added residual failure.

## Isolated evidence

- Unsteady cutoff/reversal matrix: **12/12 pass**, independently recomputed from saved traces and matching input hashes.
- Steady orifice matrix: **24/24 pass**, using the original criteria and matched inputs.
- Steady weir matrix: **24/24 pass**, using the original criteria and matched inputs.

For example, the crossing storage case at 0.25 s has a final raw system balance residual of approximately **−0.000001517 ft³**, versus **−0.080664 ft³** in the preceding continuous-law candidate without the continuity check. This is numerical verification, not a learned-control improvement.

An independent constant-area scalar solution further checks the six storage cases. For the continuous law, solve `g + alpha q(g) = b`. Inside the linear branch, `g = b/(1 + alpha K/sqrt(e))`; outside it, solve the quadratic in `sqrt(abs(g))`, using a cancellation-resistant formula. This provides an independent trajectory for the same trapezoidal discretization and sampled boundary heads.

Across all six storage cases, maximum head disagreement is **3.502e-9 ft** and maximum flow disagreement is **0.000386899 CFS**. This verifies the isolated discrete equation; it is not proof of temporal accuracy for arbitrary networks. Junction computational minimum area is not treated as independently measured physical storage.

Reproduction/verification code: `research/prepare_continuity_engine.py`, `research/continuous_orifice_probe.py`, `research/verify_continuity_probe.py`, and the existing steady-case runners. Evidence directories under `runs/hydraulic_validation_20261017/`: `continuity_probe/`, `continuity_steady_orifice/`, `continuity_steady_weir/`, plus `continuity_verification_bundle.json`. Configurations preserve DLL/source/input hashes. The source and DLL remain separate from installed SWMM.

## Full-network prerequisite

The same fixed TRAIN parent, `USC00200230_20100719__T10`, completed at 1, 0.5 and 0.25 seconds, using native control and the same physical rain inputs as previous diagnostics. All four confirmed CSO outfalls are included; all CSO happens at 65 in these runs.

- 1 s: CSO **4411.619762 m³**, flooding **0**, routing error **−1.045890%**, nonconverging steps **35.08%**.
- 0.5 s: CSO **4255.869012 m³**, flooding **0**, routing error **−0.866105%**, nonconverging steps **30.20%**.
- 0.25 s: CSO **4064.979502 m³**, flooding **0**, routing error **−0.665539%**, nonconverging steps **25.94%**.

Adjacent CSO differences are **155.750750 m³ (3.66%)** and **190.889510 m³ (4.70%)**. Both exceed the unchanged max(1 m³, 1% of finer result) limit. The 1-second run also exceeds the 1% continuity limit. **0/2 comparisons pass.** Total undesired overflow equals CSO here because flooding is zero.

The 0.25-second report retains local continuity errors at 35441 (+5.03%), 3545 (+2.42%), 3534 (−1.25%) and 1360 (−1.22%). These indicate further network investigation, not a uniquely established cause. A stricter stop check does not prevent SWMM from returning an unconverged time step after its iteration cap. The isolated repair therefore does not establish full-network reliability.

Evidence: `runs/hydraulic_validation_20261017/network_continuity_probe/`, including all three inputs, reports, results, configuration and failed refinement summary. Simulation runtime totaled approximately 247 seconds, serial execution. No references, controllability eligibility, calibration, training or test-set comparisons are approved by isolated results alone. Per the project's failure-gate rule, later experiments remain blocked rather than relaxing numerical limits.

Regression validation: **80 tests passed**, including golden compatibility and the independent scalar solution across both constitutive branches.

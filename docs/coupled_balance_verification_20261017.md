# Coupled endpoint verification — 2026-10-17

The independent three-node balance experiment does **not** reproduce the large full-network discrepancy. All **36 cases** satisfy the added trajectory accuracy checks, but only **18/36** complete without any unconverged step. This is a diagnostic result, not hydraulic acceptance or a controller improvement.

## Experiment

A small node feeds two evolving constant-area reservoirs through fully submerged SIDE orifices with the 1360/1360_B dimensions and discharge coefficient. The small node is tested both as a junction and as a storage node with area 12.566 ft². Both reservoirs use 24,231.285 ft². These equal constant areas are a synthetic simplification, not the actual tabular storage geometry. A disconnected dry outfall satisfies SWMM validation and exchanges no water.

The matrix spans 1, 0.5 and 0.25-second steps, initial head offsets 0.00005 and 0.001 ft, and inflows 0, 0.2 and 65 CFS. Each case runs 600 seconds with 40 trials and the existing diagnostic engine. The engine includes the previously disclosed continuous near-zero orifice law; it is not installed or adopted. No rainfall, TRAIN/VAL/TEST scenario or control policy is modified.

The independent solver simultaneously solves all three trapezoidal continuity equations using the incidence matrix and a damped Newton solve with analytical discharge derivatives. It uses relative heads to reduce cancellation, starts with zero link flows as SWMM does, and requires volume-equation residuals below 1e-9 ft³. Tests verify each node's equation, closed-system conservation, known forced volume addition and equal-head equilibrium.

## Results and limits

- No inflow: **12/12 trajectory checks pass**, **6/12** cases have no unconverged step. Maximum head error is 4.624e-8 ft; maximum flow error is below 0.001055 CFS.
- 0.2 CFS: **12/12 trajectory checks pass**, **12/12** have no unconverged step. Maximum head error is below 3.285e-8 ft; maximum flow error is below 0.000327 CFS.
- 65 CFS: **12/12 trajectory checks pass**, **0/12** have no unconverged step. Maximum head error is below 3.644e-8 ft; maximum flow error is below 0.000020 CFS.

The recorded `verified` field in these diagnostic results means only the stated trajectory criteria: maximum head error ≤0.0001 ft, maximum flow error ≤0.05 CFS, final-head constitutive disagreement ≤0.05 CFS, and zero flooding. It does **not** assert that every step converged or that the thesis hydraulic gate passed. Counts of unconverged steps are recorded separately.

For example, the high-inflow, small-offset, 1-second storage case has 590/600 unconverged steps, but its small-node maximum continuity residual is only 4.084e-6 ft³. The analogous network checks reach residuals of order 1–2 ft³ at the dominant nodes. This shows why iteration failure frequency alone is insufficient to quantify hydraulic error. No threshold is relaxed based on this observation.

Physical-storage variants have absolute raw system balance residuals below 0.001767 ft³. Junction variants reach 10.238 ft³ at 65 CFS; the junction's computational minimum area is not physical storage and must not be added to reported storage capacity. These cases verify the head-update equations, not physical junction storage. The small reported routing-error percentage is not a substitute for this raw accounting distinction.

## Decision

The simple simultaneous-head coupling is accurate against its discrete reference. The next reproduction must retain the real tabular curves (35440 uses 7M_2; 35442 uses 7M_1), actual invert levels, changing wetting/submergence regimes and surrounding conduit/weir interactions. The current test deliberately stays fully submerged and omits those interactions. It cannot identify which omitted feature causes the network failure.

Full-network refinement remains **0/2**, with the previously measured **3.66% and 4.70%** CSO differences. Production hydraulics, training permission and acceptance limits remain unchanged. The independent discrete solution is not proof of temporal accuracy.

Evidence: `runs/hydraulic_validation_20261017/coupled_balance_probe/`, `coupled_balance_forced/`, and `coupled_balance_high_inflow/`. Each contains input hashes, configurations, sampled and reference trajectories, engine failure counters and results. Reproduce with `python -m research.coupled_balance_probe --dll <failure-trace-DLL> --out <new-directory> --inflow <0|0.2|65>`. Runs were serial and each matrix took approximately 2–3 seconds of runner time.

The optional extra-object sampling in `research/isolated_swmm_dll.py` preserves its existing default output. Software regression suite: **83 passed**, including golden compatibility and three independent coupled-balance tests.

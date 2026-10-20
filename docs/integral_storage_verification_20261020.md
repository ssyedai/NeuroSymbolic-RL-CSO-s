# Integrated storage-volume verification

## Goal and scope

The research goal remains interpretable seven-gate control that prioritizes nodal flooding, reduces untreated CSO through 54, 65, 54_B and 65_B, and reduces their combined undesired volume. This investigation concerns hydraulic validity before controller training. It does not establish an RL performance gain.

## Current-candidate localization

The latest surface-transition candidate was replayed with read-only cumulative observations. Both 0.5- and 0.25-second replays reproduce all saved numeric final metrics exactly. The final discrepancy is 61.869314 m³, entirely at outfall 65. Its largest interval contribution is 91.661093 m³ between 81,900 and 82,800 seconds; the next is -39.481444 m³ between 113,400 and 114,300 seconds. Absolute interval differences sum to 353.437177 m³, showing cancellation.

Separate detailed-window logging also reproduces both runs exactly. The first positive weir-35444 flow in those windows is at 82,206.0 seconds for the coarser run and 82,250.25 seconds for the finer run. Maximum final-head flow residuals in the windows are 0.007094 and 0.055504 CFS. These observations localize the difference but do not establish a unique cause.

The additional control-change logger produced only headers. It used a NaN-initialized sentinel, while the upstream Release /fp:fast option permits assumptions that invalidate NaN-dependent equality guards. That is a suspected logging defect, not a proven hydraulic cause. The generator now uses a finite -1 sentinel, but that correction has not been replay-verified. Empty logs are explicitly invalid and cannot be interpreted as absence of control changes. The existing window logs remain useful and numerically verified.

## Accounting defect and correction

The ordinary depth update approximated storage change as A(y_new) times (y_new - y_old). This differs from the physical change V(y_new) - V(y_old) when the area varies over the step. The 7M_1 and 7M_2 tables have sharp area transitions at depths 11.5–11.6, 17.5–17.6 and 18.5–18.6 feet.

The separate candidate uses the integrated volume curve for storage units. At each iteration its balance increment is:

`V(y) - V(y_old) + A_extra * (y - y_old)`

Here A_extra is the nonnegative adjoining-conduit/minimum-area contribution left after subtracting the storage's own current area from the effective nodal area. It remains frozen during that iteration. This same increment enters the Newton residual, storage/outfall scalar bracket, and final ordinary-node continuity check. The local derivative remains the current surface area plus the existing regulator slope term.

This changes the numerical storage balance without introducing another discharge law or changing geometry. Flooding and EXTRAN surcharge branches retain their existing implementation. Verification here uses nonponding configurations; ponding behavior has not been validated. The candidate inherits earlier experimental surface-allocation and near-zero orifice changes, so it remains a separate alternative engine, not stock SWMM.

## Independent verification

Six synthetic three-storage cases use the actual 7M tabular geometry, a constant-area source, two fully submerged orifices, constant 65 CFS inflow, initial depths 17.4/18.4 feet, and routing steps 1/0.5/0.25 seconds. The independent reference integrates the piecewise-linear area table analytically and solves simultaneous trapezoidal volume continuity by Newton iteration with line search. It does not call the SWMM depth solver. Its volume derivative was independently checked against the area curve; a first-step residual is below 1e-12 ft³.

Using the existing head/flow criteria (0.0001 ft / 0.05 CFS and zero flood), the preceding candidate passes 2/6; the new candidate passes 6/6. The maximum head error falls from 0.0036341315 ft to 0.0000000549 ft. The maximum new flow error is 0.00003496 CFS. Synthetic routing errors fall from as much as 0.124428% to the reported 0.000001% floor. Inputs are identical between each matched before/after case.

All existing 24 weir, 24 orifice, and 12 reversing-orifice cases pass, for 60/60 additional isolated checks. These do not substitute for the required full-network refinement test.

Six additional 300-second draining cases start at depths 17.7/18.7 feet with a -65 CFS external withdrawal. All actual and independent-reference endpoint depths remain above the seven-foot orifice crown, so the fully submerged reference is applicable throughout. All six pass; the largest head error is 0.000000534 ft and largest flow error is 0.00002210 CFS. In total, 72 valid isolated cases pass (60 prior, six filling, six draining).

An initial 600-second draining fixture withdrew 39,000 ft³ from only 35,295.7032 ft³ of initial water in the 17.7-foot cases. It left the fully submerged reference's valid regime and is retained as an invalid fixture, not counted as a hydraulic pass. A subsequent template error retained a literal END_TIME_VALUE token and SWMM rejected the INP before simulation. That setup failure is also retained. The corrected 300-second fixture uses the same accuracy thresholds and explicitly checks the reference's physical regime. See the saved fixture-validity/setup-failure records.

## Network decision

All three fixed-TRAIN native runs finished using byte-identical inputs to the preceding candidate:

- 1 second: CSO/total undesired overflow 3837.263033 m³, flood zero, routing error -0.578979%, runtime 105.219 seconds.
- 0.5 seconds: CSO/total undesired overflow 3906.101835 m³, flood zero, routing error -0.624355%, runtime 193.891 seconds.
- 0.25 seconds: CSO/total undesired overflow 3807.796750 m³, flood zero, routing error -0.517739%, runtime 341.782 seconds.

The adjacent CSO/total differences are **68.838802 m³ (1.762340%)** and **98.305085 m³ (2.581679%)**, exceeding their respective 39.061018 and 38.077967 m³ limits. Both fail. Flood differences and routing-error criteria pass. All CSO is at 65; the other three untreated outfalls are included and have zero discharge in this particular diagnostic. Zero flood on this storm does not establish controller safety on other storms.

**Decision: the integrated-volume correction is verified locally but insufficient to validate the full engine.** No production adoption, rebuilt references, calibration, training or test evaluation follows. AGENTS.md section 4.9 requires stopping and reporting the failed gate rather than loosening thresholds. The later thesis stages remain incomplete.

The finer discrepancy increases from the prior candidate's 1.619595% to 2.581679%; this is not a CSO-performance gain. The corrected physical storage balance cannot establish correctness of adjoining conduit accounting, native control transition timing, or coupled regulator iteration. Those must be resolved in a new bounded investigation before adoption; the existing invalid control-change logs provide no evidence about transition timing.

Software regression: 90 tests passed; the golden-default test also passed after updating the training-block explanation to this report. An explicit early-entry check verifies that `v8_complete` still raises before any simulation or run allocation. The original installed engine and model remain unchanged.

## Evidence

All new numerical evidence is under `runs/hydraulic_validation_20261020`: `surface_stride_localization`, `surface_control_trace`, `tabular_before`, `tabular_after`, `tabular_draining_valid_scope`, `integral_weir`, `integral_orifice`, `integral_reversing`, and `network_integral_storage`. Source, patch and build metadata are preserved under `integral_storage_source` and the trace-source directories.

`research.prepare_integral_storage` generates the candidate. `research.tabular_balance_probe` provides the independent verification. The original model hash remains `186a0cfc57e59d1b815b224a89ddb506a72a1dc608585845c49043c1dfc4f125`. No installed engine was replaced and no test-split storm was used.

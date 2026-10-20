# Coupled storage/weir update — 16 October 2026

The experimental update passes **all 24 isolated equilibrium cases**, but **fails the full-network routing-refinement screen** on the previously failing TRAIN storm. It is not adopted. These results establish a successful local numerical experiment, not a validated sewer model or an RL performance improvement.

## Candidate and scope

The separate engine retains the weir-flow stopping criterion and bypass correction from `docs/flow_guard_verification_20261016.md`. It adds a local sensitivity term to the ordinary, unsurcharged storage-depth iteration. For each adjoining weir, finite differences of SWMM's own flow function estimate outgoing-flow sensitivity to the storage's depth. Both link ends are handled; perturbations are restored and the base flow is recalculated to restore link fields before the normal update.

The depth update uses a diagonal Newton correction for the same continuity fixed point. In compact notation, with `A` the current computational surface area, `y_old` the previous timestep depth, `y_last` the current iterate, `dV` SWMM's trapezoidal net inflow volume, and `S` the nonnegative local outgoing weir sensitivity:

`y_new = y_last + [A (y_old − y_last) + dV] / [A + 0.5 dt S r]`

Here `r` is 1 for the first iteration and the existing flow-relaxation parameter thereafter. SWMM's existing depth relaxation follows this correction. The finite-difference increment is **1e-7 ft**. Discharge formulas, original damping **0.5**, head tolerances, maximum iterations, physical geometry and native control rules are unchanged. This is a diagonal approximation, not a full network Jacobian. It currently addresses storage/weir coupling, not orifice/junction coupling or all nonlinear hydraulic regimes.

`research/prepare_coupled_weir_engine.py` prepares and hashes a separate source copy from OWA revision `27dc6990cda8bce21f6c16ddae631b37e7510ffc`. The only engine source file changed is `dynwave.c`. Nothing is installed over the production simulator.

## Isolated verification

The same 24 input files and predeclared criteria are used. Input hashes match the baseline case by case:

- **12/12 free-flow cases pass**, preserving steady flow.
- **12/12 submerged cases pass**, including all four previously failing 1-second cases.
- Maximum late submerged-flow range is approximately **1.26e-7 CFS**.
- Maximum late residual between the computed flow and discharge recalculated from final stored heads is approximately **1.25e-7 CFS**.

Thus the improvement is not merely a smoother time series or a changed convergence flag. It agrees with the known equilibrium and flow equation in this small model. These steady tests do not by themselves validate transient interactions in a sewer network.

Evidence: `runs/hydraulic_validation_20261016/weir_coupled/` and `coupled_comparison/`. The comparison's historical image filename is `flow_guard.png`, but its title and JSON label correctly identify the coupled storage update.

## Full-network transfer check

The probe uses only `USC00200230_20100719__T10`, selected from TRAIN before rainfall loading, with provenance verification, physical rainfall, original native gates and pump interlocks, SLOT, 40 iterations, and 1e-4 ft head tolerance. Each 72-hour episode uses all 288 calls to `swmm_stride(900)`.

The new separate-DLL runner was first checked against the existing installed-engine results. At all three resolutions, baseline CSO, nodal flooding and routing continuity match the previous records **exactly**. Baseline and candidate generated INPs also have identical hashes. The ctypes declarations and node-statistics layout were checked against the pinned toolkit headers; cumulative volumes are converted from ft³ to m³. Outfall CSO includes 54, 65, 54_B and 65_B. Interior node flooding is summed from node statistics; system flooding is retained separately.

Candidate full-network results:

- **1 s:** CSO/total overflow **4436.405663 m³**, nodal flooding **0**, routing continuity **−1.099713%**, nonconverging steps **7.35%**.
- **0.5 s:** CSO/total overflow **4199.970745 m³**, nodal flooding **0**, routing continuity **−0.847614%**, nonconverging steps **1.63%**.
- **0.25 s:** CSO/total overflow **4055.799456 m³**, nodal flooding **0**, routing continuity **−0.683040%**, nonconverging steps **1.21%**.

Adjacent CSO differences are **236.434919 m³ (5.63%)** and **144.171289 m³ (3.55%)**, relative to the finer run. Both exceed the unchanged 1% tolerance; the 1-second continuity error also exceeds 1%. **0/2 refinement comparisons pass.** No thresholds were loosened and no failed resolutions were excluded. Lower or higher CSO relative to another numerical profile is not a controller gain.

At 0.25 seconds, the report still ranks **1360_B** as the most unstable link (index 48), followed by 35444 (11) and W1 (10). Local continuity errors remain high at junctions **35441 (5.03%)** and **3545 (2.42%)**. These report statistics guide further diagnosis; they do not prove the location of a unique defect. The node nonconvergence table must also be interpreted cautiously: its existing head-based flags do not identify which weir failed the new global flow check.

Evidence: `network_dll_baseline/`, `network_coupled_probe/`, and `network_coupled_probe/binding_verification.json` under `runs/hydraulic_validation_20261016/`. The six network simulations ran sequentially, with a 15-minute cap per three-run probe. Original physical-model files and research splits were preserved.

Code validation: **68 repository tests pass**, including the v7 golden test. The 24 isolated and six network simulations are additional empirical verification; they are not counted as repository unit tests.

## Decision and next step

The stopping check plus local coupled update resolves the isolated equilibrium problem. It is insufficient for the full network, so production adoption and RL training remain blocked. The next targeted diagnosis is the remaining **1360_B orifice–junction–storage interaction**, including changing tailwater and flow reversals. Any extension must retain the now-passing isolated matrix and then pass the unchanged full-network screen. Full G0–G3, onset, controllability and rule calibration still need re-establishment before thesis claims.

Reproduction commands use `.venv-win/Scripts/python.exe`:

```powershell
python -m research.prepare_coupled_weir_engine --source <pinned-original-source> --out <fresh-source>
cmake -S <fresh-source> -B <fresh-build> -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTS=OFF -DBUILD_DOCS=OFF
cmake --build <fresh-build> --config Release --parallel 2
python -m research.weir_reproduction --out <fresh-isolated-results> --dll <fresh-build>/src/solver/Release/swmm5.dll
python -m research.report_flow_guard --baseline runs/hydraulic_validation_20261012/weir_isolated --candidate <fresh-isolated-results> --out <fresh-comparison> --label "Coupled storage update"
python -m research.network_dll_probe --dll <fresh-build>/src/solver/Release/swmm5.dll --out <fresh-network-results>
```

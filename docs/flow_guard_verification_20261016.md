# Flow-aware convergence experiment — 16 October 2026

The added weir-flow check improves the isolated verification results, but **does not pass the full matrix**. It is retained as an experimental source patch, not installed or adopted for research runs. No full-network training or test-split evaluation was performed.

## What changed

A separate copy of OWA SWMM commit `27dc6990cda8bce21f6c16ddae631b37e7510ffc` changes only `src/solver/dynwave.c`:

- Before flow under-relaxation, compare each weir's newly calculated constitutive flow with its flow from the previous iteration.
- Require the absolute difference to be at most `max(0.001 CFS, 0.001 × max(|new flow|, |previous flow|))`. Thus the relative tolerance is 0.1%, with a 0.001 CFS floor.
- Require both the existing nodal-head criterion and this flow criterion before terminating the iteration.
- Recompute weirs even when the existing head-only link-bypass test would skip them. Otherwise skipped flow evaluations could incorrectly leave the new criterion satisfied.

The new flag resets once per iteration and accumulates failures across weirs. The relevant non-conduit flow loop is serial. The negated tolerance comparison rejects NaN. The original relaxation parameter (0.5), discharge equations, model geometry, head tolerances and maximum iteration counts remain unchanged. This check covers weirs; it is not a general convergence proof for all network components.

## Matched verification results

The candidate was run on the same **24 isolated inputs** used in the previous comparison. Input SHA-256 hashes match case by case. Original equilibrium acceptance criteria are unchanged, and the comparison recomputes the decision from numerical outputs rather than trusting stored pass flags.

- Free-flow cases: **12/12 pass**, unchanged from baseline; late flow remains exactly steady in the recorded outputs.
- Submerged cases: **8/12 pass**, compared with **4/12** for the original engine.
- All 0.5- and 0.25-second submerged cases pass under both accuracy profiles and both surcharge methods.
- All four 1-second submerged cases fail. Consequently the full matrix is **20/24**, not a successful production qualification.

For the EXTRAN, 40-trial, 1e-4 ft head-tolerance case at 0.5 seconds, the late flow range falls from **82.189904 CFS to 0.095488 CFS**. The candidate's maximum deviation from the known 65 CFS equilibrium is **0.047976 CFS**, and its discharged-volume error is approximately **−0.041813%**. At 0.25 seconds the corresponding flow range is about **0.217 CFS**, still inside the original equilibrium criterion. These are numerical verification improvements, not CSO-control gains.

At 1 second, the 40-trial candidate instead has a **106.685560 CFS** late flow range, maximum equilibrium-flow error **54.856569 CFS**, volume error **−1.304160%**, and **58.50%** nonconverging steps. With 100 trials and 1e-7 ft head tolerance, the flow range is about **104.871 CFS**, volume error **−1.344356%**, and nonconverging steps **57.33%**. SLOT gives the same isolated-model results. The new criterion exposes failure and forces more iteration, but cannot make an unstable iteration converge; at 1 second the flow oscillations are worse than baseline.

## Additional residual check and limitations

The stopping check compares the newly computed flow against the prior iteration's flow **before the subsequent node-depth update**. It is not an exact constitutive-residual check at the final stored node heads. The report separately recomputes discharge from those final heads to expose that distinction.

At passing 0.5/0.25-second EXTRAN settings, maximum late final-head constitutive residuals are about **0.075–0.098 CFS**. At the failed 1-second settings they reach approximately **110 CFS**. These residuals are diagnostic additions, not a retrospectively changed acceptance threshold. The candidate's reported nonconvergence percentage includes the new global flow condition, while individual-node convergence flags remain the existing head-based flags; node convergence tables should not be interpreted as identifying the offending weir.

No thresholds were loosened, no failed cases were removed, and no production model or installed engine was changed. The next justified step is a robust coupled flow/depth update, or explicit rejection and retry of unconverged timesteps, first tested against all isolated cases. Merely increasing the iteration limit or claiming success from the finer cases is not supported by these results. Full-network validation remains necessary even after the isolated matrix passes.

## Files and reproduction

`research/prepare_flow_guard_engine.py` prepares the separate source copy with exact-match patching and upstream hashes. The candidate source, patch, configuration and build are under `runs/hydraulic_validation_20261016/engine_flow_guard_source/` and `engine_flow_guard_build/`. The DLL was compiled in x64 Release using the same compiler configuration as the baseline.

```powershell
python -m research.prepare_flow_guard_engine --source <pinned-original-source> --out <fresh-source-copy>
cmake -S <fresh-source-copy> -B <fresh-build> -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTS=OFF -DBUILD_DOCS=OFF
cmake --build <fresh-build> --config Release --parallel 2
python -m research.weir_reproduction --out <fresh-run-folder> --dll <fresh-build>/src/solver/Release/swmm5.dll
python -m research.report_flow_guard --baseline runs/hydraulic_validation_20261012/weir_isolated --candidate <fresh-run-folder> --out <fresh-comparison-folder>
```

Use the repository's `.venv-win/Scripts/python.exe`. Each run remains a synthetic hydraulic unit experiment with no rainfall or research split. The experiment configuration and DLL hash are recorded before execution; simulations run sequentially in one process.

The completed candidate results, all reports, inputs and routing-step traces are in `runs/hydraulic_validation_20261016/weir_flow_guard/`. The comparison CSV, JSON summary and inspected scientific figure `flow_guard.png` are in `runs/hydraulic_validation_20261016/flow_guard_comparison/`. The original baseline evidence remains unchanged.

Validation: **68 repository tests pass**, including the v7 golden test and new comparison-integrity tests rejecting changed inputs, duplicate/missing cases and non-finite safety measurements. The original Detroit INP SHA-256 remains `186a0cfc57e59d1b815b224a89ddb506a72a1dc608585845c49043c1dfc4f125`.

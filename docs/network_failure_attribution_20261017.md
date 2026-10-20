# Full-network convergence attribution — 2026-10-17

Read-only instrumentation identifies the 1360–1360_B–35440 junction/orifice/storage coupling as the dominant location of unresolved iterations in the separate diagnostic formulation. This localizes a numerical failure; it does not establish its unique cause or validate the formulation for research runs.

## Controlled replay

The fixed TRAIN storm `USC00200230_20100719__T10` was replayed at 0.25-second routing resolution, native controls, 40 trials and the same physical-rain input. The diagnostic DLL adds exit counters to the preceding continuity-check candidate. It performs no extra hydraulic evaluations and changes no stopping criteria or equations. The candidate itself still includes the previously disclosed alternative continuous near-zero SIDE-orifice law and is not unchanged SWMM.

Every saved result field other than wall time exactly matches the uninstrumented run, including input hash, CSO **4064.979502296459 m³**, flooding **0 m³**, and routing error **−0.665539205074%**. This is exact agreement of recorded metrics, not a comparison of every internal state or the entire time series. Runtime was approximately 135 seconds, one simulation process. The installed engine was not replaced.

## Actual final-iteration failures

Of **1,036,800 routing steps**, **268,943 (25.94%)** exited unconverged. The recorded failures are checks on the final iteration of each step, not counts of every failed inner iteration.

- Storage **35440** fails the continuity residual check on **267,882** steps, approximately **99.61%** of all unconverged steps. Its maximum final-iteration residual is **1.763536 ft³**. Its head-change check fails on zero steps.
- Junction **1360** fails continuity on **230,238** steps, with maximum residual **2.299846 ft³**; its head-change check fails on only **37** steps.
- Storage **35442** fails continuity on **9,412** steps, with maximum residual **1.913786 ft³**.
- Orifice **1360_B** fails the final-head flow check on **164,558** steps, with maximum absolute flow disagreement **0.471785 CFS**.
- Weir **35444** fails that flow check on **3,902** steps and **W1** on **3,021**. Their maximum disagreements are **28.051474** and **0.857901 CFS**, respectively. Rarer failures can have larger residuals than the most frequent failure.
- The pre-update regulator-flow check fails on **168,424** steps.

Counts overlap and must not be summed into a total or interpreted as causal shares. Continuity residuals are absolute per-step equation residuals, not signed cumulative water losses. The head criterion alone misses the dominant unresolved balance. The legacy report's outfall convergence ranking does not attribute the added checks.

## Decision and next diagnostic

The existing full-network refinement result remains **0/2 passes**: adjacent CSO differences **3.66%** and **4.70%**, exceeding the unchanged 1% criterion. All 60 isolated cases passing does not override this failure. No reference rebuild, controllability eligibility, rule calibration, RL pilot or test evaluation is released by this diagnostic.

Next, reproduce the **coupled** junction–orifice–storage system with both endpoint heads evolving and the second branch toward 35442 represented. Earlier scalar storage tests prescribe the opposite boundary head and do not verify this coupled network iteration. Trace continuity residuals, head corrections and both endpoint sensitivities at failed iterations, then compare against an independent coupled balance solution before changing the update. Slow coupled iteration is a hypothesis to test, not an established explanation. Any candidate must retain the existing isolated tests and full-network refinement criteria.

## Evidence and reproduction

Code: `research/prepare_failure_trace.py` and `research/run_failure_attribution.py`. Source/configuration: `runs/hydraulic_validation_20261017/failure_trace_source/`. Build: `failure_trace_build/`. Results, report, configuration, copied runner and counters: `network_failure_attribution/` under the same dated directory.

```powershell
.\.venv-win\Scripts\python.exe -m research.run_failure_attribution --dll runs/hydraulic_validation_20261017/failure_trace_build/src/solver/Release/swmm5.dll --prior runs/hydraulic_validation_20261017/network_continuity_probe --out <new-output-directory> --step 0.25
```

The runner raises if any recorded hydraulic result differs from the prior run. Attribution CSV SHA-256: `f9537d4b71e2d358bb4fdaa1f58825adbe9709adf004df1e40e41b51bf11ac2e`. The latest full software regression result remains **80 passed** from the preceding continuity verification; this logging-only replay does not claim a new full-suite run.

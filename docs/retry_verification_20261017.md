# Rejection/retry with restored state — 2026-10-17

**Rejection and exact replay work, but retrying does not solve every cutoff crossing.** The junction case reaches the 62-second diagnostic horizon after five rejected steps. The storage case stops at 5.755859375 seconds after eight rejections, including a minimum-size step that declares convergence while retaining a 3.177879 CFS final-head flow mismatch. No hydraulic equation was changed and no production solver is adopted.

## Implementation and restoration

`research/prepare_retry_engine.py` exposes two diagnostic-only functions on a separate copy of the experimental regulator engine: set a bounded routing step and read the most recent combined convergence flag. The setter is restricted to two-node, one-orifice, pollutant-free, fixed-step models and steps between 0.001 and 0.25 seconds. The runner restricts use further to the existing synthetic S/O/W inputs. It is not a general SWMM rollback API.

The installed toolkit cannot change routing step while running through its existing parameter setter; the pinned source was checked before adding this separate API. No discharge, relaxation, cutoff, head-tolerance or iteration-cap equation was modified. With the new step setter unused, both full 600-second crossing runs exactly reproduce every sampled state and system total from the preceding candidate engine. Evidence is in `equivalence.json`.

`research/retry_orifice.py` accepts a step only when the solver's iteration flag is true **and** its flow agrees with the independent fully submerged final-head formula within **0.05 CFS**. Finite values and the fully submerged branch are required. The initial step is 0.25 seconds; rejection halves it down to a predeclared floor of **0.001953125 seconds** (seven halvings). Accepted steps retain the reduced size; there is no step-size growth in this bounded test. The maximum attempt count is 20,000 and wall budget is 600 seconds, serial execution only.

Routing mutates time, controls, boundary state, statistics and accounting before returning. Restoring only node/link heads and flows would therefore be incomplete. This experiment discards a rejected simulation, reopens the original input and replays the entire accepted step-size sequence. Every replayed state—including all available system routing totals—is compared exactly with its original accepted state. Any mismatch raises an error. Requested and actual time advancement are also checked. Rejected elapsed time and rejected accounting never enter the accepted history. At a failed minimum-size step, replay restores the last accepted state before stopping.

This intentionally expensive replay method validates a restoration strategy for tiny reproductions. It does not provide an efficient in-memory snapshot facility for the Detroit model, nor prove equality of every unexposed engine variable. Exact replayed outputs/accounting and full restart are the evidence available here.

## Results

An initial 5-second experiment completed all four cases. The follow-up extended the same cases to 62 seconds to include the previously observed later transition; it retained the same acceptance threshold and step floor.

- Junction, inside-cutoff boundary: completes 62 seconds in 248 accepted steps; no rejection, zero flow and zero balance residual.
- Junction, crossing boundary: completes 62 seconds in **7753 accepted steps**, with **5 rejected/restored attempts**. Smallest step: **0.0078125 s**. Maximum accepted final-head residual: **0.000388849 CFS**. System balance residual: **+0.000119850 ft³**. Gross sampled link throughput: **0.013120488 ft³**.
- Storage, inside-cutoff boundary: completes 62 seconds in 248 accepted steps; no rejection, zero flow and zero balance residual.
- Storage, crossing boundary: stops at **5.755859375 s**, with **25 accepted steps** and **8 rejected/restored attempts**. The last attempted endpoint is **5.7578125 s** at the minimum step. Its solver convergence flag is true, but final-head flow residual is **3.177879 CFS**; the independent check rejects it. Maximum residual in the retained accepted prefix is **0.002892532 CFS**.

The incomplete storage prefix also fails the retained volume check: balance residual **−0.082402211 ft³** over **7.189668821 ft³** gross throughput, exceeding max(0.01 ft³, 1% throughput), approximately 0.071897 ft³. The large initial stored volume can make the engine's normalized continuity percentage look tiny; the raw residual and throughput check remain necessary. Zero flooding does not override these failures.

The report independently recomputes every acceptance decision, checks attempt counts, reconstructs the accepted timeline and verifies that the saved final state excludes rejected results. All rejected attempts and their convergence flags are retained. Completion of the short junction test is not proof of a physically accurate unsteady trajectory, resolution convergence, or improved CSO control; its very small throughput warrants further scrutiny.

## Decision

The retry mechanism correctly refuses the unresolved storage step. **Do not lower the step floor, increase iteration counts, or loosen the residual threshold merely to force completion.** The next useful diagnostic is a scalar continuity/flow residual analysis at the failed storage transition: determine whether a branch-consistent solution exists under the current discontinuous cutoff, before changing solver updates or the discharge law. Retain full-network training suspension.

## Evidence and validation

Canonical outputs are under `runs/hydraulic_validation_20261017/retry_probe_62s/`: `run_config.json`, `equivalence.json`, `results.json`, per-case attempt CSVs, frozen runner and report code, inputs, and `verification.json`. The initial short experiment remains in `retry_probe/`. The separate source, API patch and build are in `retry_source/` and `retry_build/`.

Run from the repository root in PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m research.retry_orifice --dll runs/hydraulic_validation_20261017/retry_build/src/solver/Release/swmm5.dll --prior runs/hydraulic_validation_20261017/reversing_orifice --out runs/retry_repeat --horizon 62
.\.venv-win\Scripts\python.exe -m research.report_retry_orifice --run runs/retry_repeat
```

Regression suite: **77 passed**, including golden compatibility, rejection/restoration, minimum-step stopping, detection of corrupted replay accounting, and finite final-flow acceptance tests. No TEST rainfall was read and no G0–G3 gate was relaxed.

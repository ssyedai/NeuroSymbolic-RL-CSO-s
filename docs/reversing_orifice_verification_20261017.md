# Reversing flow near the 1360_B cutoff — 2026-10-17

> Follow-up: `docs/transition_trace_20261017.md` verifies read-only internal traces. The area-switch hypothesis below is qualified: fully open RECT_CLOSED computational width is zero, and the effective nodal area stays constant in these isolated cases. The traces distinguish false head-only convergence from iteration-cap exits and time-step alternation.

The targeted reproduction is complete. **Both engines pass 6/6 inside-cutoff controls and fail 6/6 cutoff-crossing cases.** The experimental regulator update is not adopted. The reproduction demonstrates an unsteady failure mode without rainfall, RL, gate movement or the full sewer network; it does not establish the unique cause of the network's CSO nonconvergence.

## Reproducible experiment

`research/reversing_orifice.py` creates a fully open side orifice with the 1360_B dimensions (7 × 14.14 ft), coefficient 0.4, invert 601.292 ft and native travel-time parameter 0.117 h. With no commands, travel time does not cause the oscillation. Its upstream node is either a junction or constant-area storage (24231.285 ft²). The downstream node is a prescribed time-series boundary with no flap gate, allowing reverse flow. This prescribed boundary replaces the real adjacent storage for isolation; it is not a physical reconstruction of that part of Detroit.

The boundary oscillates linearly about 616.56779 ft: starting at the centre, first peak at 15 s, alternating peaks every 30 s, returning to the centre at 600 s. Amplitudes are ±0.00005 ft (inside-cutoff control) and ±0.001 ft (crossing test). Actual upstream head remains a computed state. Boundary interpolation was checked against every sampled outfall head to within 1e-8 ft, and both endpoint heads stayed above the orifice crown.

The matrix is 2 endpoint types × 2 amplitudes × 3 routing steps (1, 0.5, 0.25 s) × 2 engines = **24 serial simulations**. Each uses SLOT, 40 trials, head tolerance 0.0001 ft, no variable routing step, no lateral inflow, no controls and no rain. The engines are the previously verified separate baseline build and the experimental regulator build. Installed SWMM, original model and research splits are unchanged.

Before execution, `run_config.json` recorded the matrix, DLL/source hashes, versions, 600-second wall-time budget, one-process limit and diagnostic criteria. Actual simulation-loop wall time was under one second. Each engine received identical input bytes at each case; saved files were independently hash-checked afterward.

Reproduce from the repository root in PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m research.reversing_orifice --baseline runs/hydraulic_validation_20261012/engine_baseline_build/src/solver/Release/swmm5.dll --candidate runs/hydraulic_validation_20261016/engine_regulator_build/src/solver/Release/swmm5.dll --out runs/reversing_orifice_repeat
.\.venv-win\Scripts\python.exe -m research.report_reversing_orifice --run runs/reversing_orifice_repeat
```

## Checks and results

For fully submerged, fully open flow, the pinned `link.c::orifice_getInflow` branch returns zero when |head difference| ≤ 0.0001 ft. Above this cutoff, the signed reference is `0.4 × 7 × 14.14 × sqrt(64.4 × |head difference|)`. Its limiting magnitude just outside the cutoff is **3.177243 CFS**. The flow formula is discontinuous here.

The diagnostic requires maximum final-head flow residual ≤0.05 CFS after 60 seconds, zero flooding, absolute SWMM routing error ≤1%, and absolute system water-balance residual ≤max(0.01 ft³, 1% of gross link throughput). These are predeclared diagnostic checks, not replacements for G0–G3 or the full-network refinement screen. Gross throughput is a rectangular integral of sampled absolute flow; the raw balance residual is also retained. System balance includes all inflow terms, total initial/final storage, outflow, flooding and losses, rather than substituting the upstream node's volume for system storage.

- Inside-cutoff controls: both engines return zero flow, zero gross throughput and zero system balance residual at every resolution and endpoint type. Both pass 6/6.
- Crossing tests: both engines fail all six final-head flow checks. Zero flooding occurs in every run.
- Junction at 0.25 s: baseline maximum residual is **118.743 CFS**; candidate maximum residual is **40.265 CFS**. The candidate reverses non-negligible flow **2155 times across 2160 late samples**, despite no gate commands. Its routing error is only **0.123%**, illustrating why continuity alone is insufficient.
- Storage at 0.25 s: baseline maximum residual is **1.605 CFS**; candidate maximum residual is **3.179 CFS**. Candidate system balance residual is **−0.804 ft³** over **872.266 ft³** gross link throughput. Both pass this balance check but fail flow consistency.
- Junction at 1 s: baseline maximum residual reaches **605.668 CFS**, with **2.108%** routing error. The candidate reduces the maximum residual to **70.625 CFS**, but still fails, with **1.139%** routing error.

The report recomputes each decision from the saved routing trace. It also counts flow directed against the final head gradient, excluding negligible flow and the cutoff band. At 0.25 s the candidate junction has two such samples. The main problem is broader than wrong-direction flow: a correct sign does not establish a correct magnitude.

![Matched cutoff-crossing traces](../runs/hydraulic_validation_20261017/reversing_orifice/cutoff_crossing.png)

The figure shows 60–75 seconds of the 0.25-second cases. All decisions use the entire recorded interval after the first 60 seconds, not just the plotted window.

## Interpretation and next step

The previously passing steady tests kept the reference head gap above the cutoff. They did not test transitions between zero flow and flowing states. This matrix exposes that missing coverage. The cutoff also changes the orifice's computational surface area to `FUDGE × length`; otherwise its side-orifice area contribution is width × equivalent length. This source-level discontinuity is a hypothesis to examine alongside the flow jump, not a separately demonstrated cause.

The storage case is especially informative: a slowly changing boundary can require less exchange than the minimum nonzero branch permits. Rapid switching may then arise from the discontinuous equation itself. Thus a stringent instantaneous residual at every transition is not, by itself, proof that an exact smooth unsteady solution exists or that all switching is erroneous. The junction's much larger residuals and routing-step dependence still prevent accepting the candidate.

The next bounded technical step is to instrument iteration-level head, raw flow, relaxed flow, branch selection and computational surface area through one transition. Use that evidence to assess a solver that explicitly handles switching between the zero-flow and flowing branches, including convergence after the final head update. Any smoothing of the physical discharge law must be a separately labelled formulation change with its own validation; do not silently modify the cutoff or loosen thresholds. Do not resume full-network training on this evidence.

Evidence directory: `runs/hydraulic_validation_20261017/reversing_orifice/` contains configurations, frozen runner/binding/report copies, both engines' inputs/reports/compressed traces, `results.csv`, `summary.json`, independently recomputed `verification.json`, direction checks and the figure. Regression suite: **73 passed**, including golden compatibility, cutoff symmetry/boundary tests, prescribed-boundary timing checks and water-balance failure checks.

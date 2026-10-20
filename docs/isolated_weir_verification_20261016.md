# Isolated submerged-weir verification

Report completed 16 October 2026 from the diagnostic runs retained under `runs/hydraulic_validation_20261012/`. These are synthetic hydraulic verification cases, not observed storms, amplified rainfall scenarios, or controller evaluations.

## Finding and decision

The installed SWMM engine fails to maintain a known steady equilibrium in several deeply submerged-weir cases. A separately compiled, unmodified source build reproduces the installed engine's results exactly. A stronger-damping experiment does not solve the problem and is rejected for production use. The original Detroit model, installed engine, rainfall splits and controller defaults are unchanged.

There were **72 short simulations**: 24 with the installed engine, 24 with the unmodified source build, and 24 with an experimental build. Each engine was tested with two tailwater conditions, EXTRAN and SLOT, two accuracy profiles, and routing steps of 1, 0.5 and 0.25 seconds. Each simulation lasts 600 simulated seconds and runs sequentially in one process.

For both the installed and rebuilt baseline engines:

- All **12 free-flow cases pass** the predeclared equilibrium checks.
- Only **4/12 submerged cases pass**: 100 trials, 1e-7 ft head tolerance, and 0.5/0.25-second routing under either surcharge formulation.
- Submerged flow has a maximum late-window range of **82.189904 CFS** despite a constant inflow of **65 CFS**. Maximum absolute discharged-volume error is **5.016400%**.
- EXTRAN and SLOT produce identical results in this small unsurcharged-storage model. This does not imply equivalence in the full sewer network.

The complete installed/source-baseline `results.csv` files have identical SHA-256 hashes. The comparison therefore establishes more than agreement in the displayed rounded numbers.

The experimental source changes only `OMEGA` in `dynwave.c`, from 0.5 to 0.1. All 12 free-flow cases still pass, but **0/12 submerged cases pass**. Maximum submerged flow range increases to **276.793059 CFS**, even though maximum absolute volume error falls to **0.111305%**. Better integrated volume balance is insufficient evidence of a stable hydraulic solution.

## Reproduction model and reference

The model contains one constant-area storage, one transverse weir, one fixed-stage outfall with a flap gate, and a constant 65 CFS external inflow. There are no pumps, controls, rainfall, or RL components. Storage area is 24231.285 ft², matching the original storage curve's local plateau; invert is 582.792 ft. Weir width is 95 ft, coefficient 3, crest elevation 609.272 ft and opening height 10 ft. These local dimensions are retained; the constant-area storage and fixed boundary explicitly simplify the full network.

The submerged boundary is fixed at 616.567790 ft. The free-flow control uses 604 ft. Initial upstream head is the bisection solution of the same transverse-weir discharge relation at 65 CFS. The submerged equilibrium head is **616.567835394153 ft**, only about **0.000045394 ft** above tailwater. The free-flow reference additionally matches the independent closed-form solution `crest + (65 / 285)^(2/3)`.

Since inflow equals outflow at this initial state, the exact continuous solution remains steady. The expected 600-second outflow is 39000 ft³. SWMM's initial zero-flow/trapezoidal startup causes a small half-step volume offset: free-flow errors are at most 0.083333%, with essentially zero net mass residual when compared with SWMM's recorded inflow. This startup convention cannot explain the sustained late-window oscillations.

The checks were set before running: after 300 seconds, maximum instantaneous flow error must be at most 0.65 CFS (1%); total discharged volume must be within 1%; absolute routing continuity error must be within 1%; flooding must be zero. These are verification criteria, not replacements for thesis G0–G3.

## Why reported convergence can mislead

In the installed baseline's submerged EXTRAN, 0.5-second, 40-trial, 1e-4 ft case, SWMM reports **0% nonconverging steps**, an **82.19 CFS** late flow range, and approximately **−0.092%** global continuity error. The expected head difference is smaller than the head tolerance. Therefore head-iteration convergence does not ensure accurate flow in this regime.

Global continuity includes substantial initial storage. The baseline's worst mass residual is about **5.10% of recorded inflow**, even though global continuity percentages are much smaller. The report script now retains this additional diagnostic instead of relying only on the global percentage.

## Correction to the earlier source hypothesis

The earlier report correctly observed that the Villemonte correction does not update the free-weir derivative in `link.c`. However, `dynwave.c::setNodeDepth` uses surface area, net flow and under-relaxation for this ordinary, unsurcharged storage; it does **not** use `sumdqdh` in that branch. SLOT also uses that ordinary depth-update branch. Thus the derivative mismatch is **not an established cause** of this isolated instability, and a derivative-only patch is not justified by these experiments.

The source supports investigating the coupled flow/depth iteration and its stopping criterion. The damping ablation shows that simply lowering the relaxation parameter is insufficient. This evidence does not yet establish a validated solver repair or explain every full-network discrepancy.

## Provenance and implementation

The source build uses OWA/PySWMM commit `27dc6990cda8bce21f6c16ddae631b37e7510ffc`, compiled with MSVC 19.44.35226, Visual Studio 17 2022 generator, x64 Release, CMake 4.2.1. The downloaded archive SHA-256 is `77dffe350b749c4fdd7066b705fb4daf5b261c00f963e6e1dfa651433c23f48d`. The independent DLL binding's signatures, enumeration values and routing-total structure were checked against the pinned headers; no installed library was replaced.

Primary sources: [pinned OWA engine source](https://github.com/pyswmm/Stormwater-Management-Model/tree/27dc6990cda8bce21f6c16ddae631b37e7510ffc), [EPA SWMM software and documentation](https://www.epa.gov/water-research/storm-water-management-model-swmm). The baseline rebuilt here is the OWA source revision, not a separately validated EPA binary or a claim about an unreleased engine version.

Repository commands (use `.venv-win/Scripts/python.exe`):

```powershell
python -m research.weir_reproduction --out <fresh-output-folder>
python -m research.weir_reproduction --out <fresh-source-output-folder> --dll <separate-swmm5.dll>
python -m research.report_weir_reproduction runs/hydraulic_validation_20261012
```

`research/prepare_weir_engine.py` makes a separate source copy and records the exact one-line damping patch and upstream hashes. It never installs an engine. Source preparation and DLL compilation are diagnostic operations only.

Results, configurations, per-step traces, reports and input hashes are retained in `weir_isolated/`, `weir_source_baseline/`, and `weir_source_damped/`. The combined comparison and scientific figure are in `weir_comparison/`. The full test suite passed **66 tests**, including the v7 golden test and new equilibrium-reference tests.

## Next technical step

Use the compact reproduction to evaluate a flow-residual-aware stopping criterion or a robust coupled nonlinear update. Any candidate must first pass all isolated cases, preserve free-flow behavior, and then pass the unchanged full-network TRAIN-only routing-refinement screen. Do not promote a candidate based on low continuity error alone. Only after reliable hydraulics should corrected onset, controllability, rule calibration and RL pilots resume. No claim of superiority over literature is supported yet.

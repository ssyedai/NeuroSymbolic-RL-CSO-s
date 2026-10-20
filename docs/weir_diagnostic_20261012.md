# 7 Mile submerged-weir diagnostic — 12 October 2026

> **Follow-up correction, 16 October 2026:** The isolated reproduction and source-build comparison are complete; see `docs/isolated_weir_verification_20261016.md`. The derivative mismatch below is not an established cause: the ordinary storage-depth update does not use that derivative. Stronger damping also failed verification. Historical observations below are retained with this qualification.

The instability has been localized to a specific hydraulic interaction, but no production correction is certified. This investigation uses only amplified TRAIN parent `USC00200230_20100719__T10`, physical rainfall, all four untreated outfalls, and the original native gate and pump rules. The original INP is unchanged. Numerical experiments are separate from controller performance claims.

## Routing-step evidence

`runs/hydraulic_validation_20261012/seven_mile_native/` contains the configuration, source snapshots, report, compressed routing-step trace, summary and `weir_trace_0.25.png`. The full 72-hour run used SLOT, 0.25-second routing, 40 trials and 0.0001 ft head tolerance. It reproduces the earlier stride-based totals: CSO **4515.512844 m³**, nodal flooding **0 m³**, routing continuity **−1.0403304%**. All CSO was through outfall 65.

Across the recorded windows (16–17 and 22.5–29 hours), weir **35444**, from storage 35440 to outfall 65, changes by up to **86.980574 CFS in one 0.25-second step**. Around that jump, upstream and downstream water levels differ by approximately 0.0001 ft. Gate 1360_B stays fully open; all six recorded link targets remain constant in these windows. This rules out command chatter as the immediate explanation in the recorded interval, not elsewhere in the storm.

The storage-volume balance proxy accumulates +4307.776 ft³ at 35440 and −1.483 ft³ at 35442 over the recorded windows. This proxy compares node volume changes with trapezoidal inflow minus outflow; it is not an exact global continuity residual because the dynamic-wave computation includes connected-link storage. Node outflow already includes losses; no evaporation is subtracted twice. The pinned engine's `table_getStorageVolume` uses trapezoidal integration of tabular storage area, so that review found no storage-curve integration defect.

## Source-supported hypothesis

Pinned OWA SWMM 5.2.4 commit `27dc6990cda8bce21f6c16ddae631b37e7510ffc`, saved under `runs/hydraulic_validation_20261010/sources/`, provides the relevant `link.c`, `dynwave.c`, `node.c` and `table.c` implementations. In `weir_getInflow`, `weir_getFlow` sets the free-weir head derivative before the Villemonte submergence correction is applied to flow. That branch does not then recompute the derivative for submergence.

Weir 35444 has width 95 ft, coefficient 3, crest elevation 609.272 ft and crown 619.272 ft. Recorded heads near 616.568 ft are below the crown: this is the submerged-weir branch, not the fully surcharged equivalent-orifice branch.

For a transverse weir with fixed downstream depth `d`, the branch computes `Q = 285 h^1.5 [1 − (d/h)^1.5]^0.385`. At upstream head 616.567871 ft and downstream head 616.567790 ft, the free derivative is about **1154.715 CFS/ft**, while the derivative of this submerged formula is **386123.070 CFS/ft**, about **334 times larger**. A centered finite difference with 1e-7 ft increment gives 386123.168 CFS/ft. These are formula diagnostics, not reconstructed internal iteration states or proof of a solver defect. They explain why head convergence alone can permit large flow changes near equal water levels.

## Reproduction

Run from the repository root using `.venv-win/Scripts/python.exe`:

```powershell
python -m research.trace_hydraulics --native --seven-mile --surcharge-method SLOT --tight-solver --routing-seconds 0.25 --out <fresh-trace-folder>
python -m research.report_seven_mile <fresh-trace-folder>
python -m research.fine_routing --native-probe --surcharge-method SLOT --max-trials 100 --head-tolerance 0.0000001 --out <fresh-probe-folder>
```

The probe evaluates 1, 0.5 and 0.25-second routing, with the existing acceptance criteria: both adjacent comparisons must keep flooding within 1 m³; CSO and total overflow within max(1 m³, 1% of the finer result); absolute routing continuity within 1%. There is one simulation process and a 30-minute diagnostic cap. No thresholds are relaxed.

## Implications

The completed three-run probe with 100 trials and 1e-7 ft head tolerance **fails both adjacent refinement checks (0/2 pass)**:

- At 1 second: CSO/total overflow **3986.442975 m³**, flooding **0**, continuity **−0.624086%**, nonconverging routing steps **24.86%**.
- At 0.5 seconds: CSO/total overflow **3864.868813 m³**, flooding **0**, continuity **−0.487381%**, nonconverging steps **20.04%**.
- At 0.25 seconds: CSO/total overflow **3645.960486 m³**, flooding **0**, continuity **−0.2880%**, nonconverging steps **21.29%**.

CSO changes by 121.574162 m³ (3.15%) and 218.908326 m³ (6.00%) relative to each finer run. Both exceed 1%. Acceptable global continuity and zero flooding therefore do not establish numerically stable CSO. The stricter head tolerance also exposes frequent iteration-limit failures. This experiment does not establish that still smaller steps or more trials would solve the problem.

The machine-readable evidence is in `runs/hydraulic_validation_20261012/weir_accuracy_probe/`: `results.csv`, `summary.json`, configurations, snapshots and SWMM reports. Its inherited summary wording refers generically to three parents, but the configuration and all three rows correctly identify a single fixed TRAIN parent. Future summaries use sample-neutral wording. Total probe runtime was approximately 251 seconds; the earlier routing trace took 77 seconds. Generated simulation files were cleaned automatically; `runs/_physical_inp` is empty after completion.

Gate 1360_B routes water into the affected storage, but closing it to hide numerical oscillations would conflate hydraulic repair with control optimization. Changing the weir geometry, tailwater boundary or engine derivative requires separate justification and validation. The next justified investigation is an isolated submerged-weir reproduction and a verified solver comparison, preserving the physical model before considering production adoption. Fresh onset, controllability, rule calibration and RL pilots remain blocked by numerical validity.

Code validation: **64 tests passed**, including the v7 golden test. The trace CLI now supports native control and the 7 Mile subsystem; explicit accuracy overrides are bounded, recorded and limited to generated diagnostic INPs.

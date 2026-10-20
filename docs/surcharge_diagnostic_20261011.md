# Routing-step and surcharge diagnostic — 11–12 October 2026

This follows the failed refinement studies in `fine_hydraulic_validation_20261011.md`. The objective is to identify numerical instability before evaluating any controller improvement. All rainfall is prebuilt TRAIN T10, with full four-outfall CSO accounting. No test rainfall or test results are read.

## Routing-step evidence

`research.trace_hydraulics` traces nodes 3528_A, 3529, 3529_A, 3530, 35390, 35391, JCT-2114 and JCT-2112, plus their key connecting links and pumps. The preselected event is 2010-07-19 T10, with all seven gate targets fixed at 0.5 and original pump interlocks active. Recorded windows are 16–17 and 22.5–29 hours, chosen from the previously observed flooding intervals. Cumulative totals cover the full 72 hours.

The diagnostic uses direct `swmm_step` calls, rather than 900-second stride calls. This distinction is explicit: the 1-second direct result is 2,816.80 m³ CSO and 35.50 m³ flooding, versus 2,926.31 and 45.54 in the earlier stride run. At 0.5 and 0.25 seconds, direct totals reproduce the earlier stride results. Therefore the trace is evidence about the same instability, but the 1-second paths are not claimed to be identical.

At node **3529_A**, the largest recorded adjacent-step head changes are **15.05, 15.60 and 15.60 ft** at steps 1, 0.5 and 0.25 seconds. The largest bypass-flow changes are **389.74, 428.23 and 391.06 CFS**. The bypass target never changes in the recorded windows. Neither Puritan–Fenkell pump changes actual setting in the 30-second window surrounding any of these largest head jumps.

The jumps repeatedly approach the connecting-pipe crown at **603.49 ft** and the node flooding elevation at **619.09 ft**. This is consistent with unstable surcharge calculations; it is not evidence that an RL policy commanded the oscillation. The exact engine source (`dynwave.c`, pinned SWMM 5.2.4 commit) uses a separate EXTRAN head update above the highest connected pipe crown. That update is not under-relaxed in the same way as its free-surface update. This identifies a numerical mechanism to test, not proof that every flood volume is an artifact.

Raw compressed traces, complete totals, hashes, SWMM reports and `head_flow_jumps.png` are in `runs/hydraulic_validation_20261011/routing_trace/`. `research.report_routing_trace` excludes gaps between recorded windows when calculating adjacent-step jumps.

## Controlled numerical experiment

EPA documents two surcharge formulations. EXTRAN switches to a surcharge head algorithm; SLOT gives full conduits a virtual surface width so the regular head calculation can continue. SLOT is a supported numerical alternative, not a new physical storage tank or an RL contribution. See the [EPA SWMM 5.2 manual](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10145M6.TXT) and [hydraulics addendum](https://www.epa.gov/system/files/documents/2022-02/swmm5-reference-manual-ii-addendum-20220210mas2wr-1.pdf).

The opt-in `--surcharge-method SLOT` changes only generated diagnostic INPs. The original model, geometry, native rules, gate travel times, rain and production defaults remain intact. It repeats the same 21-run matrix and previously recorded convergence screen: three TRAIN parents, native and static-half control, plus gate 3530 closed on the first parent, at 1/0.5/0.25 seconds. Native pump rules remain active and rule evaluation remains at every routing step. No threshold is loosened.

Even a successful numerical screen would not establish real-world calibration, G1/G2/G3 completion, or RL superiority. Any adopted hydraulic formulation must be used consistently for native, rules, hindsight and learned controllers, with fresh reference caches and a recorded protocol deviation. Existing EXTRAN performance cannot be pooled with SLOT results.

## SLOT with default solver accuracy

All 21 runs completed in `slot_convergence`. **7/14** adjacent comparisons pass, compared with 5/14 for the earlier EXTRAN study. Flood volume is zero in every sampled SLOT case, and the worst absolute continuity error decreases from **7.49% to 1.75%**. These observations are promising numerical evidence but **do not pass the screen**.

In particular, native CSO for 2010-06-04 is **4,823.64, 4,310.75 and 3,840.62 m³** at 1/0.5/0.25 seconds; 2010-07-19 is **5,339.86, 5,142.25 and 4,976.46 m³**. The latter event's fixed-half CSO is **2,017.85, 2,038.25 and 1,958.48 m³**. These remaining differences prevent adoption of the default-accuracy SLOT profile.

The study is followed by the same 21 cases with SLOT plus 40 solver trials and a 0.0001 ft head tolerance, recorded separately in `slot_tight_convergence`. This is an adaptive diagnostic follow-up, not a pre-registered thesis result. Acceptance thresholds are unchanged. The EXTRAN/SLOT comparison figure is in `surcharge_comparison/routing_convergence.png` under the hydraulic validation run directory.

## SLOT with tighter solver accuracy: failed

All 21 runs completed. **6/14** adjacent comparisons pass; the worst absolute continuity error is **1.0403%**, still above the unchanged 1% criterion. All sampled flood totals are zero, but that does not compensate for unreliable CSO totals.

On 2010-07-19, native CSO is **3,720.37, 3,946.61 and 4,515.51 m³**, while fixed-half CSO is **2,101.30, 2,175.18 and 2,072.89 m³** at 1/0.5/0.25 seconds. On 2010-06-04 native CSO is **3,706.28, 4,149.44 and 3,843.75 m³**. The profile therefore remains unsuitable for production reference rebuilding or training.

The finer native report shifts the next diagnostic focus to the 7 Mile subsystem: local continuity errors are **+5.03% at 35441**, **+2.42% at 3545**, **−1.53% at storage 35440**, and **−1.48% at 1360**. Gate link **1360_B** has a reported flow-instability index of **50**. Local continuity percentages have node-specific denominators; do not confuse them with the system-wide −1.0403% error. These identify investigation targets, not proven causes or justification for changing physical geometry.

**Decision:** keep every tested profile experimental. The original model and production defaults remain unchanged. Before selecting a numerical profile, trace the 7 Mile gate/storage/weir interaction and its mass balance, including 1360/1360_B, 35440/35442, W1 and 35444. Do not start onset rebuilding or full RL training using the profile with the most favorable CSO number.

## Matched local trace and verification, 12 October

A fourth full-horizon trace repeats the 0.25-second fixed-half case with SLOT and default solver accuracy. It reproduces the stride result: **1,958.48 m³ CSO, zero flooding and +0.2898% continuity error**. Across the same recorded time windows, the largest 3529_A head jump falls from **15.6001 ft to 0.0006263 ft**, and the largest bypass-flow step change falls from **391.06 to 2.524 CFS**. This supports a local numerical-oscillation diagnosis. It does not resolve the native/whole-model convergence failures above or establish which formulation matches field observations.

`surcharge_comparison/matched_trace.png` plots EXTRAN and SLOT using an identical 30-second window centered on the EXTRAN peak and shared axis scales. Raw SLOT data and its complete configuration are in `slot_routing_trace/`. Thus the comparison does not depend on choosing different favorable times for the two methods.

This task completed **46 new simulations**: 3 EXTRAN traces, 21 default-accuracy SLOT cases, 21 tighter-accuracy SLOT cases and 1 matched SLOT trace. **63 tests pass**, including the v7 golden trajectory, selective surcharge-option edits, and rejection of missing continuity or duplicated convergence evidence. Generated temporary hydraulic files were cleaned per episode; original models, rainfall, historical results and diagnostic evidence remain available.

## Reproduction

Use fresh output directories; scripts refuse to overwrite research evidence.

```powershell
.\.venv-win\Scripts\python.exe -m research.trace_hydraulics --out runs/trace_repeat
.\.venv-win\Scripts\python.exe -m research.report_routing_trace runs/trace_repeat
.\.venv-win\Scripts\python.exe -m research.fine_routing --surcharge-method SLOT --out runs/slot_repeat
.\.venv-win\Scripts\python.exe -m research.fine_routing --surcharge-method SLOT --tight-solver --out runs/slot_tight_repeat
.\.venv-win\Scripts\python.exe -m research.trace_hydraulics --surcharge-method SLOT --routing-seconds 0.25 --out runs/slot_trace_repeat
```

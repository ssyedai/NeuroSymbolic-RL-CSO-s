# Hydraulic validation — 11 October 2026

## Findings and changes

The next validation step found and repaired a control-ownership error in the opt-in complete-overflow environment. The old environment issued commands every 15 minutes while leaving the INP's native rules active. Consequently, the logged requested action was not necessarily the target or actual setting used by SWMM. In the diagnostic, settings differed from commands by up to 1.0, the complete gate range. Earlier controlled-run results must not be interpreted as the performance of the commanded seven-gate policy alone.

The complete-overflow environment now removes the `[CONTROLS]` rules **only in generated controlled-episode INP files**. The original model is unchanged. True-native episodes retain every native rule. In controlled episodes the seven gates belong to the external controller and the three pumps receive ON commands, as specified by the existing seven-dimensional policy interface. This pump policy differs from native control and is explicitly recorded; a future pump-policy ablation is needed to attribute native-versus-agent gains specifically to gate intelligence.

The model has nonzero movement times: 1360/1360_B/3530/3530_B take 0.117 h (7.02 min), 35263 takes 0.07 h (4.2 min), and the bypass gates 35281_B/35291_B take 0.3 h (18 min) for a full movement. A 15-minute command interval therefore does not guarantee an immediately reached bypass position. Logs now distinguish `actions_projected` (command), `actions_target` (SWMM target), and `actions_actual` (position). The ownership check compares targets to commands; position lag is retained rather than disabling actuator physics.

These corrections apply to the explicitly opted-in complete-overflow environment. v7 defaults and its golden trajectory are preserved. The baseline namespace advances to `v6|physrain|nativefix|all4outfalls|gross_outward|nodeflood|external_control|72h`. Earlier caches and rule calibrations must not be reused for controlled-run comparisons.

## Volume discrepancy resolved

SWMM 5.2.4's cumulative node inflow at an outfall is not always outward discharge. The engine also accumulates the magnitude of reverse inflow there. This matters at the JCT boundary outlets, which lack flap gates. The four untreated outfalls have flap gates in this model; the environment now checks that assumption and refuses this accounting method if they are removed.

A routing-step diagnostic ran a fixed, prebuilt TRAIN storm, `USC00200230_20100719__T10`, under native control for all 259,200 seconds (26,769 routing steps). It separately integrated positive outward flow and negative boundary inflow. Results:

- System outward discharge: **115,067.652065 m³**.
- Independently integrated outward discharge: **115,067.652065 m³**.
- Cumulative inflow summed across outfalls: **115,195.662409 m³**.
- Reverse inflow at JCT-2112: **128.010344 m³**, explaining the difference to numerical precision.
- Reverse inflow at the four untreated outfalls: **zero** in this check.

The correction uses system gross outward discharge minus the four protected untreated outlets to calculate treated-route outward volume. Reverse boundary inflow is reported separately. It is not counted as treatment capture or undesired overflow. The environment still reports total undesired overflow as the user's specified CSO plus nodal flooding.

The source also confirms that node flood-volume statistics accumulate the routing-step right endpoint, while system mass-balance totals use the previous and current half steps. Ponded water can further distinguish flooding at a node from water lost from the network. They are different quantities/accumulations and must not be forced to match by changing tolerances. For the routing-step diagnostic above, both flood totals equal **31.637070 m³**. In the earlier 15-minute-stride diagnostic, some flood totals differ. Node-statistic flooding remains the operational safety metric; system flooding and continuity remain separate diagnostics.

Direct routing-step execution and 15-minute `swmm_stride` execution yield somewhat different numerical results because stride boundaries constrain the routing steps. For this same native storm, the prior stride run reported about 38.89 m³ flooding and 1,084.74 m³ CSO; direct routing reported 31.64 m³ flooding and 1,083.50 m³ CSO. This is numerical sensitivity, not a controller improvement. All method comparisons must use identical integration/control settings, and a routing-step convergence study remains necessary near the 10 m³ safety tolerance. No continuity acceptance threshold was loosened.

Evidence: `runs/hydraulic_validation_20261011/accounting_check.json` and `run_config.json`. The source files are saved under `runs/hydraulic_validation_20261010/sources/` and pinned to the OWA 5.2.4 release commit `27dc6990cda8bce21f6c16ddae631b37e7510ffc`:

- [Routing integration](https://github.com/pyswmm/Stormwater-Management-Model/blob/27dc6990cda8bce21f6c16ddae631b37e7510ffc/src/solver/routing.c)
- [Node system-outflow semantics](https://github.com/pyswmm/Stormwater-Management-Model/blob/27dc6990cda8bce21f6c16ddae631b37e7510ffc/src/solver/node.c)
- [Cumulative mass balance](https://github.com/pyswmm/Stormwater-Management-Model/blob/27dc6990cda8bce21f6c16ddae631b37e7510ffc/src/solver/massbal.c)
- [Node flood statistics](https://github.com/pyswmm/Stormwater-Management-Model/blob/27dc6990cda8bce21f6c16ddae631b37e7510ffc/src/solver/stats.c)

## Gate experiment and limits

`research.gate_sensitivity` uses the first three sorted TRAIN T10 parents from the existing manifest. No TEST rainfall or results are loaded. It compares native and static half-open control, then changes one gate at a time to zero or one while keeping the remaining gate commands at 0.5. This is a local sensitivity experiment around a fixed operating point, not a globally optimal schedule or a learned controller. It guards manifest hashes and records native/external ownership, pump policy, per-outfall CSO, nodal flooding, peak depths, reverse boundary inflow, continuity and target tracking.

The first sweep, saved at `runs/hydraulic_validation_20261011/gate_sensitivity.csv`, exposed the ownership failure and is retained as diagnostic evidence. The corrected sweep is saved separately under `runs/hydraulic_validation_20261011/owned_gates/`. These datasets must not be pooled. A generated summary accompanies the completed corrected sweep; it requires all 48 combinations before reporting completion.

The corrected sweep completed **48 simulations**, with maximum target-command error **zero**. Static half-open control reduced CSO from **216.99 to 0 m³** on the second training parent and from **1,084.74 to 0 m³** on the third; their flooding was also zero under static control. On the first parent, native already had zero overflow, whereas static half-open control produced **8,209.73 m³ CSO**. None of the 15 non-native candidates on that parent met the full flood/CSO/total-overflow scorecard. These results establish useful variation and the need for storm-dependent control; they do not demonstrate learned-policy generalisation.

The three static half-open runs have routing continuity errors between −0.285% and +0.340%. However, closing gate 3530 while keeping the others at 0.5 produces errors as large as **−10.117%**. That configuration's apparent hydraulic performance cannot be used uncritically in a controllability optimum. The sweep is diagnostic evidence, not a hydraulic-validity certificate. `research.routing_convergence` separately tests native runs at maximum routing steps of 10, 5, 2 and 1 seconds while retaining the 15-minute decision/report interval. Results are under `convergence/`; they must be reviewed before choosing simulation resolution or rebuilding onset references.

## Resolution check: not converged

The completed native study contains 12 runs; the fixed-command study contains 16. On parent 2010-06-04, native CSO changes from **216.99 m³ at 10 s to 2,916.65 m³ at 1 s**. On 2010-07-19 it changes from **1,084.74 to 3,192.45 m³**, while flooding changes from **38.89 to 66.22 m³**. Even the change from 2 s to 1 s adds 339.49 and 260.87 m³ CSO on those two parents.

The original `RULE_STEP=00:00:00` means native rules are evaluated each routing step. Thus this is sensitivity of the coupled hydraulic/native-control simulation, not a clean separation of hydraulic truncation error from control timing. Changing rule cadence would change the native reference and must be recorded, not silently called the same native controller.

To isolate that confound, fixed external commands were also tested. On 2010-07-19, half-open control changes from **zero CSO and zero flooding at 10 s** to **942.75 m³ CSO and 28.41 m³ flooding at 1 s**. Its flooding changes by 28.41 m³ even between 2 s and 1 s, exceeding the absolute 10 m³ tolerance used by the safety scorecard. Therefore the earlier zero-overflow outcome is **not robust to numerical resolution**, and no controller superiority should be claimed from the coarse sweep. Good continuity alone is insufficient: that 1-second run has only +0.036% continuity error.

Closing 3530 produces −10.117% continuity error at 10 s and −10.200% at 1 s. Refining time alone does not resolve that configuration. An explicit `native_pumps=True` diagnostic ablation now leaves original pump interlocks active while externally controlling only the seven gates, and skips forced pump writes. Its default is **False**, so the prescribed pumps-ON stack and v7 defaults remain unchanged. Native pump rules are retained independently of gate rules; mixed gate/pump action rules fail closed rather than being partially rewritten. Ablation evidence is in `pump_interlocks/` and must be treated separately from the pumps-ON experiment.

The four-run pump ablation isolates the persistent continuity problem. For the first parent with 3530 closed, at 1-second routing, native pump interlocks change continuity from **−10.200% to +0.194%** and CSO from **10,261.66 to 20,868.51 m³**. At 10 seconds the error changes from −10.117% to +0.199%. This supports retaining pump safeguards when studying seven-gate control; the forced-pumping configuration's lower CSO must not be credited as reliable mitigation. It does not prove the remaining hydraulics are converged or every native pump rule is optimal.

**Decision:** hydraulic validation is not yet passed. Do not launch a full onset rebuild, certify G2 controllability, calibrate a production shield or retrain using whichever resolution produces the best percentages. First establish a stable hydraulic/control discretisation and a physically valid pump policy on TRAIN events, freeze it, then rebuild identical references for every method. `convergence_summary.json` preserves all comparisons. No G0–G3 thresholds or flood tolerances were loosened.

## Reproduction

```powershell
.\.venv-win\Scripts\python.exe -m research.check_routing_accounting
.\.venv-win\Scripts\python.exe -m research.gate_sensitivity --out runs/new_gate_check
.\.venv-win\Scripts\python.exe -m research.summarize_gate_sensitivity
.\.venv-win\Scripts\python.exe -m research.routing_convergence
.\.venv-win\Scripts\python.exe -m research.routing_convergence --controlled
.\.venv-win\Scripts\python.exe -m research.routing_convergence --controlled --native-pumps
.\.venv-win\Scripts\python.exe -m research.summarize_routing_convergence
.\.venv-win\Scripts\python.exe -m pytest -q
```

The fixed convergence commands refuse to overwrite existing results. Preserve/archive their output directory before an intentional rerun; the gate diagnostic accepts a fresh `--out` path. The summary command reads the canonical corrected sweep directory. Tests include golden compatibility, complete-volume identities, physical command tracking, restoration of native rules between episodes, and selective retention of pump rules.

Full training remains disabled. First complete hydraulic sensitivity and integration-convergence checks, then rebuild G1 onset and G2 flood-feasible search with the new accounting/control semantics. Any parent with zero native CSO has no positive CSO-reduction headroom under that reference; retain it for safety evaluation rather than manufacturing a percentage improvement.

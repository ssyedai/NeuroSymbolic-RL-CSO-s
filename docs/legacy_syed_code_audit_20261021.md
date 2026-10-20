# Audit of the shared Syed code, old model, and old report

## Short answer

Do not train from the shared script. It contains useful clues, but it is not a safe or reproducible training program. The current v8 pipeline already keeps the useful parts and fixes the important errors.

The old report file does not prove that a run completed. It is exactly 16,384 bytes and ends in the middle of the Analysis Options section. It therefore cannot be used to confirm overflow, flooding, continuity, the routing step, or controller performance.

Only the SWMM model is authoritative here. Any controller timing or deadband not present in that file must be called a modelling assumption, not a real GLWA operating rule.

## Files checked

- Shared Python text: SHA-256 `1466729d40d4111da0f461f7f68a6884d5cb2923d09c4a5304b2c2a06a82951e`.
- Local old Python text: SHA-256 `ad16571293e9063d758e5f25822168e63c90151dda058c9e331ad84bc62f3259`.
- Old INP: SHA-256 `186a0cfc57e59d1b815b224a89ddb506a72a1dc608585845c49043c1dfc4f125`. It is byte-for-byte the same as the root model.
- Old report: SHA-256 `b4cecbba9a00dcdbba2d8ee185f20c9af7fc6a89c43e3dc85cee2df9d6a6220b`.
- The notebook contains seven successive trials. Stored outputs include `NameError`, `MultiSimulationError`, `KeyError`, `FileNotFoundError`, and an interrupted training run. It is development history, not verified experimental evidence.

The shared text and the local old text differ mainly in the input-file path, rainfall-file path, and whitespace. Their control and reward logic are the same.

## What is useful in the shared code

1. It confirms the seven gate IDs and three pump IDs used by the same-site work.
2. It uses a 900-second, or 15-minute, external action interval. This matches Syed et al. 2025 and is suitable as a controlled ablation. It does not establish the cadence of the native controller.
3. Its 0.05 actuator grid is useful for generating surrogate-model samples.
4. It shows that a 10-actuator policy was considered. The primary safe design should still control seven gates and leave the three pump interlocks native. A 10-actuator policy belongs only in a labelled ablation.

## Why the shared script cannot be trusted as written

1. `env.close()` is called before `env` is created.
2. `rand_num` and `test_rainfall5` are used but are not defined in the shared file.
3. `node_object`, `link_object`, and `subcatch_object` are local variables in `__init__`, but `step` and `reset` use them as if they were global. A clean run raises `NameError`.
4. `reset` creates a new SWMM `Simulation` but does not rebuild the node, link, rain-gauge, gate, and pump objects. Those objects remain tied to the closed simulation.
5. The state is read before `sim.__next__()`, while the reward is read after it. The stored transition therefore pairs an old state with a new reward.
6. The script writes gate and pump targets without removing the INP control rules. SWMM rules and the external controller can command the same actuator.
7. The reward counts only links `35391` and `35444`. It omits untreated bypass outfalls `54_B` and `65_B`.
8. The reward adds instantaneous overflow flow and instantaneous flooding flow. It does not integrate event volume and does not make flooding a hard safety constraint.
9. Flooding and CSO have equal weight. That conflicts with the requested priority: prevent added flooding first, then reduce CSO.
10. The observation box says every value is between 0 and 1000, although link flow can be negative and many variables have different scales. The raw full-network vector is also unnormalised.
11. There is no parent-event split, validation-only checkpoint selection, seed control, provenance check, native-reference cache version, or reproducible run record.
12. The 291-line shared file generates random trajectories. It does not contain a complete trained actor/critic workflow.

## Rainfall-unit finding

The INP uses `FLOW_UNITS CFS`, so PySWMM's rain-gauge setter expects a rainfall rate in inches per hour. The shared code writes spreadsheet values directly to that setter.

The old CSV has 288 values, a maximum of 25, and a raw sum of 474.083269. The old workbook has 288 values, a maximum of 5, and a raw sum of 706.5. Neither file gives a unit column or a data dictionary, so their physical meaning cannot be proved from the files alone.

If a value is a 15-minute depth in millimetres, the correct rate is `value / 6.35` inches per hour. Writing the value directly makes the rate 6.35 times too large. The current research path avoids this error by writing pre-built physical-rain time series into a temporary INP and never using the rain-gauge API override.

## What the old `.rpt` file does and does not show

It shows:

- SWMM 5.2 build 5.2.4 and PySWMM Toolkit API 1.0;
- one rain gauge, 19 subcatchments, 47 nodes, and 52 links;
- rain gauge `Design_RG`, time series `9_12_08`, `INTENSITY`, 60-minute interval;
- warnings about minimum elevation drops for `Connection` and `Connection_2`, and a raised crest for `35291_B`.

It does not contain the end-of-run continuity table, node flooding summary, outfall loading summary, pump summary, control-action summary, or a completion time. It also ends before the routing-step line is printed. The file is therefore incomplete.

A complete SWMM report can contain routing settings, continuity, flooding, and outfall totals. It will not normally prove the real PLC scan interval, undocumented deadbands, minimum pump on/off time, or whether a Python controller competed with native rules. Those need the controller specification or explicit code/run records.

## Physical control policy kept in v8

The primary controller is seven-dimensional. Pumps remain under the INP interlocks. This avoids asking the learner to rediscover basic treatment and dewatering safety.

Flood safety is checked in cubic metres for every event. A checkpoint is rejected if it adds more than `2% + 10 m3` flooding relative to the same storm's native run. When the native run is flood-free, the agent must also be approximately flood-free.

The gate shield follows the network graph. Each gate uses its own upstream depth-risk nodes and its reachable storage and overflow path. Direct bypass gates stay closed unless an upstream flood emergency requires relief.

Storage is now measured against capacity below the first overflow crest. In this model, that usable volume is only about 31.7% to 37.0% of the full-depth volume for the four storage nodes, and 34.5% in total. Using full-depth capacity would wrongly report spare storage after spilling had already started.

The 10-actuator ablation now gives the policy real ownership of the pumps and removes the native pump rules for that ablation. Previously, the three learned pump outputs were silently forced to one and never reached SWMM. The primary seven-gate design is unchanged.

## Priority of remaining experiments

1. Highest priority and highest scientific risk: resolve the native switching/time-step problem. The model's native result changes by 1.422% between 0.5 and 0.25 seconds, above the fixed 1% limit, and the 0.125-second result reverses direction. Frozen controls pass, so the remaining problem is native switching, not a general reason to loosen the limit.
2. High impact and moderate cost: rebuild the CSO-onset table using complete four-outfall volumes after the reference gate passes.
3. High impact and high cost: run flood-feasible hindsight search on train and validation parents only.
4. Medium impact and high cost: calibrate the rule shield on train and stop on validation; keep it only if it improves the default rules without a flood regression.
5. High impact and high cost: run one 300-episode pilot for each primary method and ablation. Stop any method with non-finite values, a saturated safety multiplier, rising flood cost, or validation performance below random gates.
6. Only after those checks: freeze the protocol, tag it, and evaluate the untouched test parents with at least three seeds, preferably five.

## Controlled comparisons

- Seven gates with native pumps versus the corrected 10-actuator policy.
- Storage based on usable capacity below the overflow crest versus the old full-depth calculation.
- Full topology-aware shield versus no topology.
- Full controller versus no storage-first term, no safety multiplier, no shield, and no causal rain features, one change at a time.
- Training on observed storms, flat two-times storms, return-period/onset ladders up to 100 years, and the separate 1000-year diet.

Every comparison must use the same parent split, rainfall manifest, true-native run, hindsight run, flood limit, evaluation code, and seed set.

## Current stop condition

The code is ready for reproducible checks, but official training is still blocked by the unchanged native-control refinement gate. With only the model file, there is no evidence that can turn a model-based deadband or cadence into the true operating rule. A model-based controller envelope can be studied and labelled as such, but it cannot silently replace the true-native comparator required by the protocol.

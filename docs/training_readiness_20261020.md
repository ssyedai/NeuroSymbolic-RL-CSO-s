# Training-readiness diagnosis and controlled experiment plan

## Decision

The implementation is prepared for a valid full-objective experiment, but the
research is not yet authorized to train. The hydraulic/native-control gate is
failed. The code now enforces that stop through
`research.readiness.assert_hydraulic_training_ready` rather than relying on a
human remembering the latest report.

This document distinguishes verified software corrections from unverified model
performance. No performance gain is claimed.

## Research objective and validity conditions

The primary safety constraint is

`flood_agent <= 1.02 * flood_native + 10 m3`,

with the same 10 m3 limit when native flooding is effectively zero. Subject to
that constraint, the controller minimizes cumulative untreated discharge at the
four confirmed outfalls (`54`, `65`, `54_B`, `65_B`). Storage-first behavior is
evaluated by the temporal implication that CSO can occur only when relevant
storage is at least `1-delta` full. Treated discharge and capture ratio are
reported as secondary resource-use outcomes; they cannot compensate for a flood
or CSO regression.

The true native reference is the original INP `[CONTROLS]` behavior on the same
storm. Controlled episodes remove gate rules from generated episode INPs, retain
the original pump-only interlocks, and give the seven-dimensional policy
exclusive gate ownership. Reference episodes do not write target settings.

## Root causes found

1. **Native hybrid-control sensitivity (blocking, causally isolated).**
   The best 0.5-to-0.25-second native comparison differs by 57.118 m3 or
   1.422%, above the unchanged 1% limit. A third 0.125-second refinement changes
   CSO by 239.396 m3 (6.339%) in the opposite direction, so no real observed
   convergence order exists. Predicate tracing localises the critical branch to
   the 35281_A flow crossing that closes gate 35281_B 46.25 seconds apart.
   PUMP29 chatter occurs later and is not causal for this residual. With all
   controls frozen, the same 0.5-to-0.25-second hydraulic comparison differs by
   only 0.238% and passes unchanged output, flood and continuity criteria. This
   isolates native switching semantics as the blocker and prevents a
   resolution-independent native comparator. See
   `native_control_resolution_20261020.md`.

2. **Incomplete historical objective (fixed in code, not yet re-evaluated).**
   Earlier paths sampled two weirs and omitted untreated bypass outfalls. Every
   official v8 variant now uses cumulative SWMM volume accounting for all four
   confirmed CSO outfalls and all non-outfall node flooding.

3. **Competing controller ownership (fixed).** Historical controlled episodes
   could retain native gate rules while the agent also wrote gate targets.
   Generated research INPs now remove gate rules only, retain pump interlocks,
   and record control ownership.

4. **Safety objective mismatch (fixed).** The cost critic mixed approximate
   flood volume with an uncalibrated depth-margin term and a fixed cost limit.
   Its cost is now physical flood volume, and its per-event budget is derived
   from the native flood non-regression cap.

5. **Confounded ablations (fixed).** `plain` and `lag_only` retained the
   storage-first reward; `v8_notopo` switched to the entire v7 stack; and the
   10-D environment retained a 7-D agent. These now preserve the same complete
   environment and change only the named factor.

6. **Invalid or non-reproducible selection/resume (fixed).** v8 safety-feasible
   selection is mandatory; validation subsampling is split-seed invariant and
   final validation is uncapped; best-score keys agree; replay, Python/NumPy/
   Torch RNGs, safety critics, multiplier, and sampler state are checkpointed.

7. **Potential train/test access (fixed).** Training loads only IDs declared
   train or validation and uses a run-local baseline cache. Test evaluation is a
   separate command that requires an ancestor `protocol-v1` tag.

8. **Baseline state leakage (fixed).** B0 calibration/static episodes explicitly
   disable the shield and restore its previous state, preventing baseline
   generation from silently disabling the training shield.

9. **SAC action-density error (fixed for v8 only).** The `[−1,1]` to `[0,1]`
   affine Jacobian term was omitted. v8 opts into the corrected log density;
   v7 retains historical behavior for golden compatibility.

10. **Onset and search assumptions (guarded/fixed).** Onset now evaluates the
    full dose grid and stops on non-monotone CSO response. Controllability and
    rule calibration use complete cubic-metre accounting and safety-first
   ranking; infeasible schedules cannot establish controllability.

11. **Storage availability above an overflow crest (fixed).** The complete
    controller previously used full-depth storage capacity in its symbolic
    state and per-gate shield. In this model, only about 34.5% of that total
    volume lies below the first overflow crests. The complete controller now
    uses per-unit and total usable capacity below those crests, while retaining
    the full-depth ratio as a separately named diagnostic.

12. **Inactive outputs in the 10-actuator ablation (fixed).** The 10-D agent
    previously learned three pump outputs that were forced to one and never
    applied while native pump rules remained active. The labelled 10-D ablation
    now removes native actuator rules and gives the external policy exclusive
    ownership of all seven gates and three pumps. The primary controller remains
    seven-dimensional and retains the native pump interlocks.

## Prioritized experiment plan

1. **Resolve native-control/hydraulic acceptance.** Obtain documented PLC scan
   interval, pump minimum-on/off times, and gate hysteresis/deadbands. Reproduce
   the native refinement study with all four CSO outfalls. Pass only at at most
   1% difference with unchanged zero-flood and continuity criteria. Expected
   scientific impact: critical; compute: hours; risk: high because changing
   control semantics changes the comparator.

2. **Rebuild G1 onset under the accepted engine/reference.** Reject a parent if
   its CSO dose response is non-monotone. Pass only if median onset is at most 4
   and fewer than 30% lack onset by the cap. Impact: critical; compute: hours.

3. **Rebuild G2 flood-feasible hindsight.** Train/validation only, static search
   followed by CMA where prescribed. A rung below 5% is excluded from training;
   any rung median below 10% fails G2. Impact: critical; compute: tens of minutes
   per storm; risk: low after hydraulic acceptance.

4. **Calibrate B3 rules.** Optimize on train, early-stop on validation, and retain
   B3 only if it is flood-feasible and improves on default B2 validation score.
   Impact: medium; compute: high; risk: moderate overfitting controlled by the
   parent split.

5. **Run G3 pilots.** One seed, 300 episodes per Tier-1/ablation variant. Require
   finite training, non-saturated lambda for at least half the episodes, falling
   cost, and validation performance above random gates. Do not scale failed
   variants. Impact: high; compute: approximately three hours per run.

6. **Freeze protocol, then scale.** Commit and tag `protocol-v1` before opening
   test rainfall. Run at least three, preferably five, seeds. Use parent-event
   hierarchical bootstrap, paired tests, and Holm correction. Observed and
   amplified families remain separate.

## Controlled ablations

- Full v8 versus SAC-plain: shield, rain features, storage reward, and Lagrangian removed.
- Full v8 versus SAC-Lag-only: Lagrangian retained; shield, storage reward, and rain features removed.
- `v8_notopo`: global shared context replaces gate-specific graph reachability.
- `v8_nostore`: only the storage-first reward weight is zero.
- `v8_nolag`: only multiplier learning is disabled.
- `v8_noshield`: only action projection is disabled.
- `v8_norain`: only causal rain features are removed.
- `v8_10d`: the actor/critics/replay and environment all use ten policy dimensions.

Each comparison uses the same scenario manifest, split, cumulative-volume
objective, native reference, validation events, budgets, and seed set.

## Evidence boundary

The full software suite passes, but passing software tests does not pass the
hydraulic gate. Historical v8 checkpoints and result tables used incomplete
overflow accounting and cannot verify the corrected controller. No official
training or test-set result should be reported until G0-G3 are re-established
under the accepted four-outfall reference.

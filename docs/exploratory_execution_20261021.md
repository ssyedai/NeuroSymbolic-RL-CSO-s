# Exploratory v8 execution — 21 October 2026

## Decision

The exploratory pipeline now runs end to end through preprocessing, scenario
generation, controllability search, rule calibration, baseline evaluation, a
20-episode SAC smoke run, and deterministic checkpoint replay. It is **not
ready for scaled training**. The smoke run failed G3, and the native hydraulic
reference still fails the unchanged routing-step acceptance check.

Every artifact below is marked
`research_status=exploratory_unverified_native_reference` and
`hydraulic_gate_passed=false`. No test scenario was evaluated. These numbers
are debugging evidence, not controller-performance claims.

Executed training code: Git commit `e86e2f4`. The later B1 dictionary-merge
reporting fix changes no hydraulic calculation and is committed with this
report. Software verification after the fix: 115 tests passed.

## Completed stages

### G1 onset and scenario catalog

- Parents scanned: 416/416; errors: 0.
- Median `k_onset`: 3.7224 (unchanged limit: at most 4).
- Parents with no onset inside the search cap: 0/416 (unchanged limit: below
  30%).
- G1 therefore passes as an exploratory preprocessing check.
- Scenario rows: 2,420 from 416 parents.
- Split rows: train 1,592; validation 289; test 539.
- Minimum independent parents in any split/rung cell: 4.
- Atlas table SHA-256:
  `f6c180e2cb547f0b47f495e66798d0fb2e1c0c63313d7b1f986cb85e2298fb76`.
- Output: `data/useful/exploratory/rain_scenarios/`.

The fixed parent-year split is train 2010–2020, validation 2021–2022, and test
2023–2026. Scenario generation used the test parent rainfall only to construct
and label its predeclared held-out children; no controller fitting, selection,
or controllability eligibility used test outcomes.

### Reduced controllability diagnostic

The smoke screen used 12 train storms, one per available rung, with 8 static
candidates, 2 CMA generations, and population 4. This is deliberately recorded
as `full_protocol_budget=false`, so its failed rungs are **not** removed from
training.

- C1 achievable reduction: 100%.
- T25: 15.11%.
- C1.5: 2.81%; T100: 1.68%; T200: 2.40%.
- C2, C3, T5, T10, and T1000 had no safety-feasible improvement in this small
  search. R/F2 had no usable native-CSO denominator in the sampled events.
- Formal `g2_pass=false` as required for a reduced budget.

Output: `runs/exploratory/controllability_smoke.csv` and its summary/config
sidecars. Sampling limitation: this first reduced sample contained train storms
only. It is diagnostic and cannot support a train/validation controllability
claim.

### Rule calibration and baselines

Rule calibration used four train and four validation storms, two CMA
generations, and population four.

- Candidate validation score: 3.999926.
- Default B2 validation score: 3.999946.
- The candidate remained safety-infeasible (`score > 1`), so
  `b3_beats_b2_on_val=false` and B3 was not used.

On 12 severity-balanced validation scenarios:

- B0 static 0.5: mean CSO reduction −326.61%; flood non-regression 10/12;
  scorecard 3/12.
- B1 native: 0% by definition; flood non-regression and scorecard 12/12.
- B2 default rules: mean CSO reduction −54.16%; flood non-regression 9/12;
  scorecard 3/12.

Negative reduction means more overflow than native. The tuned B3 is omitted
rather than reported as an improvement.

### SAC smoke run and G3

Configuration: V8, D2, seed 0, 20 episodes, 500 random warm-up steps,
`updates_per_step=0.25`, six validation scenarios per checkpoint. The reduced
G2 summary did not exclude any training rung. There were no NaNs.

- Episode 10: selection `-inf`; validation mean CSO reduction −140.3%;
  lambda 0.582.
- Episode 20: selection `-inf`; validation mean CSO reduction −137.2%;
  lambda 0.000.
- Mean episode cost rose from 0.02284 (first five) to 13.0841 (last five).
- Every validation row had intervention rate 1.0.
- No safety-feasible `best_val.pt` was written. The trainer stopped before its
  final aggregate, as designed. `final.pt` is retained only for diagnosis.
- Re-evaluating `final.pt` twice on the same six validation scenarios was
  identical to tolerance `1e-9`.
- That replay had flood non-regression 4/6. C1 CSO was 517.95% worse than
  native; C1.5 6.65% worse; C2 2.65% worse; C3 1.90% better. R/F2 had zero
  native-CSO denominators and were not assigned percentage reductions.

Run: `runs/exploratory/exploratory_v8_smoke_s0/`.

## Root cause of the G3 intervention failure

Topology identifies gates 35281_B and 35291_B as direct routes to untreated
outfalls 65_B and 54_B without downstream storage. `CompleteOverflowKB`
therefore forces those gates closed whenever there is no upstream flood
emergency. SAC emits continuous sigmoid/tanh actions strictly inside (0, 1),
while `intervention_rate` counts any gate change above `1e-6`. Consequently at
least one direct-bypass gate is changed on virtually every step, even if the
learned value becomes very small. Entropy training also has little reason to
drive an action that the shield always overwrites exactly to zero.

This makes the current intervention acceptance check structurally infeasible
for the full shield. It must not be “fixed” by raising the allowed 0.5 rate.
The follow-up experiment therefore separates:

1. a declared hard action-space constraint for normally closed direct-bypass
   gates, and
2. dynamic shield interventions caused by changing hydraulic risk.

Both the actor-to-admissible constraint rate and the admissible-to-executed
dynamic intervention rate are logged. This is an opt-in ablation named
`v8_actionmask`; the existing V8 and V7 paths are unchanged.

## Action-mask ablation result

The matched run used the same seed, D2 training pool, 20 episodes, 500-step
warm-up, update rate, and validation cap as the V8 smoke. Gates 35281_B and
35291_B were set to their normally closed admissible value before the dynamic
shield. The shield could still open them for a depth or flooding emergency.

This separation fixed the measurement problem, not the control problem:

- Mean dynamic intervention rate was 0.0295, below the unchanged 0.5 limit.
- Actor-to-admissible constraint rate was 1.0 and total override rate was 1.0.
  These remain visible rather than being relabelled as no intervention.
- The six-storm deterministic validation replay had flood non-regression 4/6
  and scorecard pass 2/6.
- Macro CSO reduction over the four storms with a nonzero native denominator
  was -131.40%; C1 was -518.25%, C1.5 -6.64%, C2 -2.63%, and C3 +1.93%.
- Mean episode cost increased from 0.02296 over the first five episodes to
  13.05641 over the last five. Critical training fields were finite; lambda
  stayed below its cap and ended at zero.
- The episode-20 selection score remained `-inf`; no `best_val.pt` was saved.
- Replaying `final.pt` twice in a fresh process agreed to tolerance `1e-9`.

The result is almost identical to the original V8 run on CSO, as expected:
the ablation changes action ownership/accounting, while retaining the same
normal and emergency executed settings. G3 therefore still fails because cost
does not trend down, flood non-regression is below 95%, and CSO is worse than
native. The 300-episode pilot remains blocked.

Run: `runs/exploratory/exploratory_v8_actionmask_smoke_s0/`. The generated run
is local and ignored by Git.

The run used base commit `ab7402ff3b0918b1f6cef9d526cfdae831ea02ec` plus
the action-mask code diff whose SHA-256 is
`5fcf834edd49bd4bdd4b3781c770736a3a4ca2942567ac16f609b892e22cb1ff`.
Future run configurations record dirty-tree state and the full Git diff hash
automatically.

Reproduce the ablation with:

```powershell
.\scripts\run_exploratory_pipeline.ps1 -Mode smoke `
  -Variant v8_actionmask -RunName exploratory_v8_actionmask_smoke_s0
```

## Native-rule structure and timing follow-up

A second diagnostic tested whether the poor CSO result came from ignoring the
INP's coordinated gate logic. A causal three-action native-rule prior improved
CSO, confirming the structural diagnosis, but failed the unchanged flood and
total-overflow screens. A five-minute control sensitivity improved flood
non-regression from 3/6 to 4/6 validation storms, but still added unacceptable
flooding on C2 and C3. Training-only shield grids found no safe setting at
either 15 or 5 minutes, so both variants are blocked from SAC.

Exact methods and results are in
[`nativeprior_timing_diagnostic_20261021.md`](nativeprior_timing_diagnostic_20261021.md).

## What is intentionally not run

- The 300-episode pilot, multi-seed Tier 1/2 matrix, diet study, protocol tag,
  and test evaluation are not run because both smoke variants failed G3.
- The reduced controllability screen is not promoted to formal G2.
- The unsuccessful theta is not supplied to training.
- The native-rule-prior variants are not trained because their pre-training
  safety screens failed.
- No hydraulic acceptance file is created and no validation threshold is
  relaxed.

Running those expensive stages now would violate the prescribed gate order and
would turn a known structural mismatch into misleading performance output.

# Hybrid native/SAC gate diagnostic (2026-10-21)

## Question

Can the timing problem be avoided by leaving the six fast routing gates under
their original SWMM rules and giving an external controller only gate `35263`?

This is an exploratory TRAIN-only diagnostic. The repository's fixed hydraulic
acceptance gate is still failed, so these values are not performance claims.
No validation or test event was used to select the result.

## Implementation

The opt-in `v8_hybrid_gate2` path keeps these gates under the INP rules:
`1360`, `1360_B`, `35281_B`, `35291_B`, `3530`, and `3530_B`. Pump interlocks
also remain native. Only `35263` is written externally. Its one-dimensional
action is a bounded residual (maximum +/-0.25) around the causal 15-minute
rendering of the original `35263` rule. Existing variants and v7 defaults are
unchanged.

The generated episode INP is checked so that the six owned gate-rule blocks
and pump rules remain, while all three `ShiawasseeGate*` blocks for `35263` are
removed. Mixed-ownership rule blocks are rejected instead of being split.

## Fixed TRAIN screen

Four severity-balanced TRAIN storms were used (`C1`, `C1.5`, `C2`, `C3`). The
same native reference cache and unchanged safety limits were used for all five
constant normalized residual actions.

| Action | Macro CSO reduction | Flood non-regression | Total-overflow non-regression | Scorecard pass | Worst total-overflow delta |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 24.499% | 4/4 | 3/4 | 3/4 | +7,620.076 m3 |
| 0.25 | 25.970% | 4/4 | 3/4 | 3/4 | +7,036.933 m3 |
| 0.50 | 25.970% | 4/4 | 3/4 | 3/4 | +6,818.301 m3 |
| 0.75 | 25.051% | 3/4 | 2/4 | 2/4 | +24,655.875 m3 |
| 1.00 | 22.651% | 3/4 | 1/4 | 1/4 | +19,344.064 m3 |

The centered action is the least-bad setting by worst total-overflow delta, but
it still fails the C3 storm: CSO is 1.700% worse than native and combined
CSO-plus-flood volume is 6,818.301 m3 higher. Larger positive residuals also
cause flood regression. No tested point passes all four scorecards.

## Decision

`v8_hybrid_gate2` is retained as an auditable diagnostic and is blocked from
SAC training. A learned policy was not started because the pre-training safety
screen failed. This preserves the established rule that a failed safety gate
cannot be bypassed by training, validation selection, or a looser threshold.

The next scientifically valid step still requires an independently justified
native control timing/deadband specification or a hydraulically converged
native reference. Until then, official onset rebuilding, controllability,
training, test evaluation, and performance claims remain blocked.

## Reproduction

The outputs are under `runs/exploratory/hybrid_gate2_screen/`. Example:

```powershell
.\.venv-win\Scripts\python.exe -m research.run_baselines_eval `
  --rain-dir data/useful/exploratory/rain_scenarios `
  --split-manifest data/useful/exploratory/rain_scenarios/splits.json `
  --which hybridgate2 --hybrid-action 0.5 --splits train --max-storms 4 `
  --baseline-cache runs/exploratory/hybrid_gate2_screen/baseline_cache.json `
  --out-dir runs/exploratory/hybrid_gate2_screen/train --exploratory
```

Software verification after this change: `127 passed`.

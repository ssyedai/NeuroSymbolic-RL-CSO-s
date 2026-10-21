# Native-rule prior and control-timing diagnostic — 21 October 2026

## Decision

The native-rule prior is **rejected for training**. It improves CSO on several
storms, but neither the 15-minute nor the 5-minute version preserves flooding
and total overflow on the fixed training screen. The repository now blocks both
variants from starting SAC. No test storm was read and no acceptance threshold
was changed.

All results are exploratory because the native hydraulic step-size gate remains
failed. They are debugging evidence, not performance claims.

## Root cause isolated

The failed V8 learner behaved almost exactly like the B2 rule controller. The
problem was therefore upstream of learning. The controller held the paired
routing gates near 0.5/0.5 and normally closed both direct-bypass gates. The INP
does something materially different:

- gates 1360/1360_B and 3530/3530_B are coordinated routes;
- gates 35281_B and 35291_B open under named conduit-flow and storage-head
  conditions; and
- gate 35263 follows three state-dependent rules.

On validation C1, native control produced 1,403.76 m³ CSO, B2 produced
8,558.09 m³, and static 0.5 gates produced 45,755.50 m³. Native mean gate
positions were approximately 0.25/0.74 and 0.83/0.14 for the two routing pairs;
B2 held both pairs near 0.51/0.51. This supports a native-structure prior, but
does not establish that a 15-minute rendering is safe.

## Candidate implemented

`v8_nativeprior` is a three-action diagnostic controller:

1. Seven Mile route residual;
2. gate 35263 residual; and
3. Puritan-Fenkell route residual.

The center action follows a causal rendering of the canonical INP gate rules.
Residuals are bounded to ±0.25. The controller reads only current heads, flows,
and settings—never future rainfall or a cached native trajectory. The original
V7, V8, and true-native paths are unchanged.

The 5-minute sensitivity version keeps the rain input as physical 15-minute
depths. Rain-feature indexing, interval-mean flow conversion, event duration,
and cubic-metre integration were made control-step aware. Its reference cache
uses a separate `ctrl300` namespace.

## Validation-only neutral-prior check

The centered 15-minute prior reduced macro CSO by 33.69% over the four scored
validation storms, but flood non-regression was only 3/6. The centered 5-minute
prior reduced macro CSO by 26.99% and improved flood non-regression to 4/6, but
still failed:

- C1: 99.58% CSO reduction, flood-safe;
- C1.5: 1.45% CSO reduction, flood-safe;
- C2: 2.85% CSO reduction, but 4,314.96 m³ flooding versus 139.04 m³ native;
- C3: 4.08% CSO reduction, but 105,831.92 m³ flooding versus 67,748.56 m³
  native.

These validation checks diagnose transfer only. They were not used to choose
the shield setting.

## Training-only safety grids

Each grid used one training parent from C1, C1.5, C2, and C3. It tested
`theta_f ∈ {0.5, 0.7, 0.9}` and `theta_f_open ∈ {0.5, 1.0}`. Selection was
lexicographic: complete flood non-regression, then complete total-overflow
non-regression, then CSO reduction.

At 15 minutes, no setting passed. The highest-ranked setting
(`theta_f=0.5`, `theta_f_open=0.5`) achieved:

- flood non-regression 3/4;
- total-overflow non-regression 1/4;
- scorecard 1/4; and
- macro CSO reduction 22.98%.

At 5 minutes, no setting passed. The highest-ranked setting was the unchanged
default (`theta_f=0.9`, `theta_f_open=0.5`):

- flood non-regression 3/4;
- total-overflow non-regression 2/4;
- scorecard 2/4; and
- macro CSO reduction 28.87%.

The C2 training storm remained the main flood failure, while C3 increased total
overflow even when its flood volume did not exceed native.

## Consequence

Both `v8_nativeprior` and `v8_nativeprior_5m` are diagnostic-only and raise a
clear error if passed to the training entry point. A lower shield threshold,
faster external control, or longer SAC run cannot be claimed as a fix from this
evidence. The next scientifically defensible options require one of:

1. documented PLC scan/deadband/dwell specifications so the true native
   reference and control timing can be defined;
2. a separately verified predictive safety layer that passes the train and
   validation flood screens before SAC; or
3. a hybrid ownership design that leaves fast safety-critical gates under
   verified native logic and gives the learner only non-conflicting actuators.

Artifacts are local under `runs/exploratory/nativeprior_*`. They remain
separate from official caches and are ignored by Git.

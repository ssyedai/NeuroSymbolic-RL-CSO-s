# Research model card — working diagnostic release

## Intended use

Offline master's-thesis research on interpretable control of a Detroit combined-sewer SWMM model. The proposed controller operates seven gates. This release is not validated for operating a sewer system and does not establish improved performance over published methods.

## Objective and accounting

Prioritize nodal flooding, then CSO, while reducing total undesired overflow. Untreated CSO comprises outfalls 54, 65, 54_B and 65_B. Total undesired overflow equals their outward discharge volumes plus nodal flooding, in m³. JCT treatment conveyance is excluded from CSO. Internal model heads/depths use feet and flows use CFS. Usable storage must be measured at actual storage nodes; a junction's computational minimum surface area is not physical storage capacity.

## Model status

The v8 controller implementation exists; corrected, hydraulically validated multiseed performance evidence does not yet exist. Legacy checkpoints, reference caches, tuned thresholds and pilot results are not accepted under the revised overflow accounting. The explicit complete-overflow training block remains active. Separate experimental DLLs are numerical diagnostics and have not replaced installed SWMM. Some candidates change the near-zero orifice law and must never be described as unchanged native SWMM.

## Explanations required for final release

Save raw and executed gate actions, triggered symbolic rules, measured predicates and thresholds, intervention magnitudes and conflict resolution. Measure whether logged explanations reproduce executed interventions. Feature importance alone does not establish faithful symbolic explanation. Compare against optimized rules, plain SAC and SAC-Lag under identical hydraulic conditions and information availability.

## Release requirements

Pass the declared hydraulic screen, regenerate native references and flood-feasible controllability results, calibrate on TRAIN/VAL only, pass the pilot, freeze a versioned protocol and complete matched multiple-seed evaluation. Report uncertainty by parent storm, including flooding and total overflow rather than CSO alone. Consult the current readiness JSON and dated diagnostic reports for measured status; this card is not a gate certificate.

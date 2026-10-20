# Rule cadence and conduit bypass verification — 2026-10-19

**Neither diagnostic resolves network refinement. No candidate is adopted, and corrected-reference rebuilding and training remain blocked.** Acceptance limits are unchanged.

## Rule-cadence separation

The bracket candidate was replayed on the fixed TRAIN storm `USC00200230_20100719__T10` with native rule expressions evaluated every one second at every routing resolution. This changes native controller timing and cannot replace the true-native comparator silently. Comparison of generated inputs verifies that only `RULE_STEP` changed from the preceding bracket experiment.

- Maximum routing step 1 s: CSO **4200.180987 m³**, flooding **0**, routing error **−0.793780%**.
- 0.5 s: CSO **4173.847457 m³**, flooding **0**, routing error **−0.760445%**.
- 0.25 s: CSO **4035.551481 m³**, flooding **0**, routing error **−0.611792%**.

Only **1/2** adjacent comparisons passes. The finer comparison changes by **138.295976 m³ (3.43%)**. Fixing rule cadence alone is therefore insufficient; it does not prove that control timing has no influence. The original native-rule timing remains the required reference.

Evidence: `runs/hydraulic_validation_20261017/bracket_fixed_rule_probe/`. Reproduce using `research.network_dll_probe --fixed-rule-second` with the separate bracket DLL and a fresh output directory. The default of this new diagnostic flag is false.

## Conduit bypass correction

Source inspection found that `findBypassedLinks()` still marked conduits as skippable when both endpoint head-change checks passed, even when an endpoint failed the added continuity residual check. In a separate candidate, both endpoints must also satisfy the existing **1e-6 ft³** continuity criterion before a link may be bypassed. This does not change discharge equations, physical inputs, thresholds or the iteration cap.

This candidate inherits the preceding bracket solve and the explicitly disclosed alternative continuous near-zero SIDE-orifice law. It is not stock SWMM. Source, configuration and patch are preserved in `runs/hydraulic_validation_20261017/balance_bypass_source/`; its separate DLL is in `balance_bypass_build/`. Installed SWMM is unchanged.

The established isolated suites pass **60/60**: 24 weir, 24 steady orifice and 12 unsteady orifice cases. They are regulator-dominated tests, so passing them does not by itself validate conduit behavior. The full-network run provides the relevant additional test.

With original native-rule timing and the same physical rainfall:

- Maximum routing step 1 s: CSO **4165.833132 m³**, flooding **0**, routing error **−0.782394%**.
- 0.5 s: CSO **4110.206305 m³**, flooding **0**, routing error **−0.715104%**.
- 0.25 s: CSO **3982.707116 m³**, flooding **0**, routing error **−0.586072%**.

Both adjacent comparisons fail: differences are approximately **55.627 m³ (1.35%)** and **127.499 m³ (3.20%)**. The unchanged limit is max(1 m³, 1% of the finer result), plus flooding and continuity requirements. Total undesired overflow equals CSO here because flooding is zero. Improved continuity percentages and lower CSO values are not evidence of control improvement or acceptance.

The routing values are configured maximum steps; the inherited adaptive-step option is retained. All three input hashes match the original-rule bracket runs exactly. Runs used one simulation process at a time and completed within the predeclared 900-second network budget. No validation/test storm was loaded by these diagnostics.

Evidence: `runs/hydraulic_validation_20261019/network_balance_bypass/` and the three dated isolated-test directories. The failure requires further hydraulic investigation; it cannot be repaired by choosing the more favorable resolution or relaxing thresholds.

## Independent research-selection repair

The training and validation ceiling now checks both fitted `T_anchor` and the declared `T` rung/target. Thus a T200 child with a fitted value of 80 cannot enter a 100-year pool. The loader retains `T_target`. Explicit research scenarios with unknown/nonfinite severity are excluded; legacy catalogs without scenario metadata retain their compatibility path. The former test that admitted an observed research scenario with NaN severity was tightened accordingly.

Only D3 can opt into `test_only` training rungs; this never permits test-split storms into training. A research catalog with no separate validation split now raises an error instead of silently using training data as validation. An empty validation pool after the ceiling filter also raises. These changes do not read test results, alter existing rainfall files or bypass the complete-overflow training block.

Verification: **90 software tests pass**, including golden compatibility, the ceiling regressions and the existing diagnostic option tests. These tests verify code behavior, not hydraulic acceptance. Later thesis experiments remain incomplete.

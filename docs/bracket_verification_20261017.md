# Storage/outfall-weir root solve — 2026-10-17

**Decision: reject for production adoption.** The candidate passes all 60 existing isolated checks but only **1/2** full-network refinement comparisons. Training and reference regeneration remain blocked under the unchanged hydraulic acceptance criteria.

## Read-only network diagnosis

The regime logger samples at most one failed final iteration per minute. It reproduced all prior saved hydraulic metrics and aggregate failure counters exactly. This sampling is diagnostic and is not an unbiased estimate of the frequency of each failure regime.

The real storage units also connect through `Connection_2` and weir `W1`; 35440 discharges through weir 35444 to outfall 65. At 83,587 seconds the sampled 35440 balance residual was 1.664284 ft³, and its accumulated local regulator slope was about 2.23 million CFS/ft. Weir 35444's used flow was 25.877810 CFS while its final-head flow disagreement was also approximately 25.877810 CFS. This localizes a sharp near-tailwater transition that was absent from the earlier two-orifice synthetic model. It does not establish that this mechanism alone explains all network error.

Evidence: `runs/hydraulic_validation_20261017/network_regime_trace/`; logging source, patch and configuration in `regime_trace_source/`. The installed solver and model input were unchanged.

## Candidate

In the separate diagnostic source, a bounded scalar solve replaces the diagonal depth correction at a storage node with an outgoing weir to a fixed-within-iteration outfall head. It solves the local depth equation including the nonlinear weir-flow change, retaining the existing link-flow relaxation factor. Temporary evaluations restore node depth, link and weir fields. The bracket is zero to full storage depth; if it does not enclose a root, the previous update remains. The scalar solve uses at most 50 bisections and a 1e-8 ft³ residual target; the outer 40-trial cap and acceptance thresholds are unchanged.

Other links remain coupled through the outer routing iteration. This is not a simultaneous solution of the whole network. The prior explicitly changed continuous near-zero orifice law remains part of this candidate; the weir discharge law itself is unchanged. This must not be represented as a stock SWMM result.

## Tests

The existing steady weir, steady orifice and unsteady orifice suites pass **24/24, 24/24 and 12/12**, respectively. Criteria were not changed. Configurations and sampled traces are in `bracket_weir/`, `bracket_orifice/` and `bracket_reversing/` under the dated hydraulic evidence directory.

The same fixed TRAIN storm `USC00200230_20100719__T10` was replayed with native controls, physical rainfall and all four CSO outfalls. Generated input hashes exactly match the previous candidate at each resolution.

- **1 s:** CSO 4193.611903 m³; flooding 0; routing error −0.787535%; nonconverging steps 31.28%.
- **0.5 s:** CSO 4193.381723 m³; flooding 0; routing error −0.776448%; nonconverging steps 28.57%.
- **0.25 s:** CSO 4036.016573 m³; flooding 0; routing error −0.611957%; nonconverging steps 18.02%.

The first pair differs by **0.230180 m³ (0.00549%)**, passing. The second differs by **157.365150 m³ (3.898%)**, exceeding the unchanged max(1 m³, 1% of the finer result) criterion. Total undesired overflow equals CSO because flooding is zero. Each routing-error magnitude is below 1%, showing again that global continuity alone does not establish temporal convergence. Serial simulation runtime was approximately 431 seconds within the predeclared 900-second budget.

The lower fine-resolution CSO is not a controller improvement. It is unresolved numerical dependence under the same native control. One successful coarse comparison cannot justify selecting the coarse step or skipping the failing finer result.

## Consequence for the requested thesis work

The corrected native reference, onset/controllability screen, rule tuning, training pilot, multiseed studies and final statistics still depend on accepted hydraulics. They were not run on this failing candidate. No production DLL was replaced and no test-set storm was opened by this diagnostic. The existing complete-overflow training block remains in force.

Independent work completed alongside this test: official NOAA Atlas 14 airport-point depths and confidence bounds, a verified conversion utility, parent-event statistics with pairing/accounting checks, and working model/data cards. These preparations do not constitute completed research experiments, final novelty verification or evidence of superiority over literature.

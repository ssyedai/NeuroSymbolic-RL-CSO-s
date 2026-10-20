# Thesis execution dependencies — 2026-10-17

> **Latest decision, 2026-10-20:** Integrated storage-volume correction passes 72/72 valid isolated hydraulic cases but fails both native TRAIN network refinements (1.762340%, 2.581679%; limit 1%). No engine adoption or training. Software: 90 passed and golden compatibility rechecked. See docs/integral_storage_verification_20261020.md.

> **Latest decision, 2026-10-19:** Exact read-only replays identify remaining failures around 1360_B and its endpoints. Increasing MAX_TRIALS to 200 reduces nonconverging steps to about 4.2% but still fails the finest refinement: 78.845283 m3 (2.073436%), limit 38.026394 m3. No engine adoption or downstream experiments. See docs/surface_failure_attribution_20261019.md.

> **Latest decision, 2026-10-19:** A verified upstream conduit-area branch discontinuity causes a repeating junction solver cycle. The continuous-allocation candidate passes six compiled boundary/control groups and 60/60 isolated tests, but fails both network refinements (2.06%, 1.62%). Candidate rejected; training and downstream experiments remain blocked. Software suite: 90 passed. See `docs/conduit_surface_transition_20261019.md`.

> **Latest verification, 2026-10-19:** Fixed one-second rule cadence still fails the finest comparison (3.43%). Requiring node continuity before conduit bypass passes 60/60 isolated checks but 0/2 network comparisons (1.35% and 3.20%). No production adoption or research training. Training/validation severity ceilings now check declared T rungs as well as fitted values, reject unknown research severity, and require a separate research validation set. Software tests: 90 passed. See `docs/balance_bypass_verification_20261019.md`.

> **Latest execution, 2026-10-17:** A bracketed storage/outfall-weir correction passes 60/60 isolated tests but only 1/2 network refinement comparisons. The 0.5→0.25 s CSO difference is 157.365 m³ (3.898%), so no production adoption or training. Official NOAA Atlas 14 tables for Detroit City Airport (42.4072, -83.0089), including 90% bounds, are now verified and selected for future scenario rebuilding under user authorization. Parent-event statistics tooling and model/data cards are prepared. Software suite: 87 passed. See `docs/bracket_verification_20261017.md` and `docs/reproduction_current.md`.

> **Coupled endpoint diagnostic, 2026-10-17:** All 36 synthetic cases meet independent discrete-trajectory checks, but only 18/36 have no unconverged steps. The simplified constant-area system does not reproduce the large network discrepancy. Next: actual tabular geometry, wetting/submergence and surrounding connections. Full-network refinement remains 0/2 and training remains blocked. See `docs/coupled_balance_verification_20261017.md`. Software tests: 83 passed.

> **Network failure attribution, 2026-10-17:** Read-only logging reproduces all prior recorded hydraulic metrics exactly. Of 1,036,800 steps, 268,943 remain unconverged; storage 35440 fails continuity on 267,882 of them (99.61%), while its head-change check always passes. Gate 1360_B has 164,558 final-flow failures. Counts overlap. See `docs/network_failure_attribution_20261017.md`. The next target is coupled junction/orifice/storage iteration; full-network refinement remains 0/2 and training remains blocked.

> Latest evidence: `docs/continuity_verification_20261017.md` supersedes the isolated two-case failure below. All 60 isolated cases now pass, but neither full-network refinement comparison passes. Stage 1 remains incomplete because of network convergence; stages 2–7 remain dependent on it. The latest software regression suite has 80 passing tests.

The user authorized completing the analysis and subsequent research stages. This record distinguishes implemented software from validated experimental evidence. It is not a new protocol freeze or a completion claim.

## 1. Hydraulic validation — blocked by measured failures

Complete: four-outfall accounting, native/external control ownership diagnostics, isolated weir/orifice tests, iteration tracing, verified rejection/replay, and the isolated cutoff no-root certificate. The latest alternative formulation passes all 60 isolated cases, including junction accounting, but fails both full-network refinement comparisons. Read-only attribution localizes most unresolved balance checks to storage 35440 and junction 1360. Remaining: verify their coupled iteration, demonstrate time-step convergence and acceptable continuity on the fixed TRAIN hydraulic screen, then evaluate implications of any formulation change for the physical model. No failing candidate is adopted.

## 2. Reference and controllability rebuilding — waits for stage 1

Recompute true-native and static references with all four untreated outfalls and cumulative volume accounting. Re-establish G1 using corrected CSO, review the scenario manifest and eligibility, then perform flood-feasible hindsight searches on TRAIN/VAL only. Old G1/G2 results are historical evidence, not current approval. Compare native and learned control under exactly the same accepted hydraulic formulation.

## 3. Interpretable controller and pilot — waits for stages 1–2

The v8 stack and diagnostic complete-overflow prototype exist. Calibrate symbolic-rule parameters on TRAIN with VAL early stopping, compare B3 against default rules, and verify the cumulative-metric objective. Required behavior remains flooding first, CSO second, with lower total undesired overflow. Record raw action, executed action, triggered rule, measured predicate, intervention magnitude and any conflict resolution. Evaluate explanation fidelity against executed interventions, not only feature importance. Pass G3 before scaling. The `v8_complete` training path remains explicitly blocked.

## 4. Baselines, ablations and multiple seeds — waits for stage 3

Run the required native/static/rule baselines, hindsight, physical-rain V7, full neurosymbolic SAC, plain SAC and SAC-Lag, followed by the prescribed component ablations and diet study. Target five seeds, minimum three where the agreed protocol permits it. Use the same storms, budgets, information availability, numerical model, objective accounting and checkpoint selection for fair comparisons. Save all flags, seeds, versions and input/model hashes.

## 5. Protocol and data prerequisites — partly confirmed

Confirmed by the user: untreated outfalls 54, 65, 54_B and 65_B; treated JCT outlets; VAL 2021–2022 and TEST 2023–2026; bounded compute chosen by the agent. Official Atlas 14 depths and 90% confidence intervals are now verified at the user-authorized representative Detroit City Airport station. Remaining: rebuild scenarios against that table, obtain optional anchor rainfall, and freeze a reproducibly versioned protocol after the pilot. Existing TEST exposure must be disclosed. No new claim of an untouched holdout is allowed. Previously generated rungs above 100 years remain unverified for claims; the new official table does not retroactively certify them.

## 6. Statistics, literature comparison and final package — waits for valid results

Aggregate children within parent storms, retain observed/amplified separation, and report paired uncertainty across parents and seeds. Include total undesired overflow, all-outfall CSO, nodal flooding, flood non-regression, zero-when-feasible, storage-first behavior, actuator effort and intervention metrics. Produce effect sizes, hierarchical bootstrap intervals, paired tests and multiplicity correction. Complete model/data cards, environment lock and reproduction instructions. Preserve research evidence during cleanup; remove only verified disposable intermediates.

## Literature positioning rechecked

Tian et al.'s interpretability study already examines explanation of drainage-control RL. An interpretable controller alone is therefore insufficient as a novelty claim. Candidate distinction: an operational symbolic safety layer with measurable explanation fidelity, evaluated against rule-only and unshielded methods. [Water Research 249, 120912](https://pubmed.ncbi.nlm.nih.gov/38042066/).

Tian et al.'s multi-RL/MPC work already combines safety prediction with control selection. A predictive safety module must be compared with that approach rather than described as the first reliable RL controller. Its code repository is linked in the paper, but has not been reproduced on this project's corrected model. [Water Resources Research, e2021WR030703](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2021WR030703).

A separate Tian et al. paper uses a Koopman emulator to accelerate RL training and studies interpretability and robustness. It is distinct from the multi-RL/MPC paper and has a different DOI; do not merge their methods or results. [Water Resources Research, e2021WR030939](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2021WR030939).

Tian et al.'s later knowledge-data fusion framework uses engineering knowledge to guide DRL training. A broad claim that adding engineering knowledge is itself novel would overlook this work. [Water Research 289, 124901](https://www.sciencedirect.com/science/article/pii/S0043135425018044).

Yin's Detroit-related work remains especially relevant for matching case geometry, rainfall and discharge definitions. The conference publication and the Journal of Hydrology forecasting/inverse-optimization study should be cited under their actual venues; neither should be relabelled as a Water Resources Research article. Full-text retrieval from the NSF links failed during this follow-up, so the earlier audit's detailed comparison has not been expanded using unavailable material. [2023 conference manuscript](https://par.nsf.gov/servlets/purl/10459969), [Journal of Hydrology 628, 130515](https://par.nsf.gov/servlets/purl/10523713).

Published percentage reductions across different networks and storm definitions are not a common leaderboard. A defensible superiority claim requires matched reimplementations or a clearly limited comparison, with flooding and total undesired overflow reported alongside CSO. Until the hydraulic blocker is resolved, neither novelty nor performance superiority has been established.

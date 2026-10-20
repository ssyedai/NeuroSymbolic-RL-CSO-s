# Thesis audit and corrected overflow objective — 10 October 2026

> **Follow-up, 11 October:** Read `docs/hydraulic_validation_20261011.md` before using any controlled-run numbers below. The follow-up found native rules overriding external commands, reverse JCT boundary inflow in cumulative volume, substantial routing-resolution sensitivity, and a forced-pumping configuration with approximately 10% continuity error. It adds opt-in corrections and diagnostics. Earlier results remain historical evidence, not certified controller performance.

## Assessment

This is a worthwhile master's thesis direction, but the saved results do not yet establish a safe controller or an improvement over the literature. The central contribution should be **flood-constrained, interpretable control of usable storage with complete untreated-discharge accounting**. A neural SAC policy plus a few rules is not, by itself, evidence of novelty or hydraulic safety.

The user confirmed that **54, 65, 54_B and 65_B are untreated CSO outfalls**, and that JCT outlets are acceptable treatment conveyance. In this INP the actual JCT outfalls are **JCT-2112 and JCT-3090**; JCT-2114 is an upstream junction. Gates **35281_B → 65_B** and **35291_B → 54_B** control untreated bypass discharge. This resolves the classification question in AGENTS.md §12. The previous topology statement “no gate reaches a CSO weir without storage” does not mean “no gate can discharge untreated water without storage.” The bypass gates do exactly that.

The primary volume definitions are now:

- `CSO = V54 + V65 + V54_B + V65_B`, in m³.
- `total undesired overflow = CSO + cumulative nodal flooding`, in m³.
- Report nodal flooding separately, including each flooded node. Never hide it in a combined score.
- Treat flood non-regression and zero-when-feasible as feasibility constraints; minimise CSO among acceptable controllers, and require total overflow non-regression for the scorecard.

This is the user's operational definition of total undesired overflow. With surface ponding and re-entry enabled, cumulative flooding plus later outfall discharge can count water more than once. It is not necessarily a unique-water-loss mass balance. Report continuity separately. The hydraulic model also does not establish treatment quality at JCT outlets; that classification is supplied by the user.

## What the saved results actually show

The reproducible audit `python -m research.audit_thesis` reads saved training/validation logs, not final test results. Evidence is under `runs/thesis_audit_20261010/`.

1. `v8_full_s0` has 1,000 training episodes and 20 validation checkpoints. Each validation checkpoint contains 23 scenarios from 16 parents. Every evaluated rung has fewer than three parents, despite the larger catalog. Validation sampling is therefore inadequate for the specified per-rung inference.
2. Flood non-regression ranges from **73.91% to 82.61%**. **None of the 20 checkpoints reaches 95%.** This alone prevents a safe-control success claim. The last checkpoint has about 30.74% event-macro reduction in the *old monitored* CSO metric, which excludes bypass discharge and therefore cannot establish complete-overflow improvement.
3. Lambda is below 50 in 76.4% of episodes, so the literal lambda clause in G3 passes. It is nevertheless at least 49.9 in 81.9% of episodes. Mean episode costs by quarter are 11.15, 8.37, 15.21 and 10.18: no convincing sustained improvement. A required random-policy comparison is still missing. Do not describe the complete G3 gate as demonstrated from these statistics.
4. **5 of 210** saved hindsight candidates violate the specified reference flood bound. A finite flood penalty allowed CSO gains to compensate for flood regressions. These candidates must not be presented as flood-feasible optima. Finite search is a best-found hindsight comparator, not a certified global optimum or rigorous performance bound.
5. The old onset table has 416 parents and median `k_onset=3.7224`; ten unscaled parents already have monitored CSO greater than one in the old units. Thus “all observed rain produces no CSO” is too strong. Onset must be rebuilt with the confirmed four-outfall definition. The old table lacks a clear status field independently certifying the no-onset rate.
6. Legacy totals sum CFS samples at 15-minute endpoints. They are not volumes. Multiplying by 900 seconds converts an approximate quadrature, which can miss short spills. The new diagnostic uses cumulative SWMM node volumes and interval differences. It includes all 288 control intervals rather than 287.
7. The old `store_fill_ratio` sums depths, which is not volumetric utilisation for nonconstant area-depth curves. The four actual storage nodes are 35390, 35391, 35440 and 35442. Outfalls 54/54_B are not storage.
8. All 23 rows at the last saved validation checkpoint lack routing and runoff continuity errors. New diagnostic runs record these after SWMM finalisation.
9. The file named `atlas14_mm.csv` is a local fitted frequency table, not a verified NOAA Atlas 14 table with confidence intervals. The 180-minute row is missing. Existing T200+ labels cannot be presented as certified Atlas 14 extremes. The loader's IDF-derived `T_anchor` can also disagree with the target rung, allowing T200 into a nominal ≤100-year validation pool. Do not use those rungs for new claims until repaired.
10. Existing protocol documentation calls itself frozen, but there is no Git repository/tag and test results have already been examined in previous project work. This audit did not use test rainfall or test performance to choose the candidate. The historical exposure must be disclosed; retaining the split does not make it newly untouched.

## Implemented corrections

Legacy v7 environment behaviour remains the default; the golden trajectory is retained. `CompleteOverflowEnv` and `CompleteOverflowKB` are opt-in research prototypes in `multistorm/complete_overflow.py`, accessible through `adapters.build_v8(..., complete_overflow=True)`.

The new environment counts the four outfalls and every non-outfall node's cumulative flood volume, computes interval-average overflow rates, records per-outfall and per-node volumes, and obtains final continuity errors. Volume is converted from ft³ to m³; model depths remain **feet**. Interval-average peaks and event durations are not routing-timestep extrema or exact durations; the `flow_sampling` field identifies that limitation.

Storage capacity is the integral of each tabulated area-depth curve. A separate “usable” capacity stops at the lowest outgoing weir crest. This is a geometric diagnostic, not a proof of hydraulically accessible capacity: backwater, transfer capacity and timing still matter. The old unqualified full-storage requirement is physically questionable where spill crests are below maximum storage depth. Both physical and usable utilisation should be reported.

The candidate shield closes bypass gates when upstream risk is below the flood trigger, and permits emergency opening. Its trace records the rule, proposed/applied action and trigger state. This explains shield interventions; it does **not** explain all neural actor decisions or guarantee flood prevention. The physical reward has flood and CSO components plus usable-storage shaping, but a weighted reward alone does not enforce strict flood priority.

Other corrections include native-referenced evaluation/aggregation, safety checks on zero-CSO-reference events, optional strict checkpoint rejection, exact-storm hindsight matching, schedule reset between episodes, and SAC-Lag checkpoint persistence of the cost critic, optimiser and lambda. Legacy checkpoints without safety state may be evaluated as policies but cannot safely resume training. New runs no longer evaluate TEST implicitly; research training without explicit test evaluation loads only train/validation rainfall from the fixed split manifest.

Search now offers `safety_first=True` for static/CMA hindsight and rule optimisation. Flood-infeasible candidates rank below all flood-feasible candidates, then total-overflow feasibility precedes CSO ranking. A failed event cannot be averaged away in rule calibration. Defaults remain compatible with earlier searches; existing runners must explicitly adopt the new mode with complete m³ summaries. This has unit tests; full new searches have not been run.

`--variant v8_complete` deliberately stops before training: the new objective invalidates the old onset table, controllability evidence and theta calibration. This prevents accidentally reusing apparently valid gates from a different objective. The executable diagnostic is `python -m research.complete_overflow_check`.

## Small hydraulic diagnostic

The fixed selection is the first three sorted T10 IDs in each existing train and validation split. It uses one SWMM process, physical prebuilt rainfall, the manifest guard, and four policies: true native, unshielded static half-open gates, static with bypass gates closed, and the candidate rules. These are six scenarios, not a trained-RL comparison and not a literature benchmark. The local T10 labels are retained for traceability, not independently recertified as NOAA return periods.

Fresh G0 diagnostics confirm four responsive storage nodes, with maximum wet-minus-dry depth differences of **32.20, 27.34, 30.75 and 29.56 ft**. All seven native initial settings equal 1.0 in both the independent INP run and environment reset. `FLOW_UNITS=CFS`. An initial diagnostic implementation mistakenly compared against the controlled environment's 0.5 defaults; it was corrected to read a separate native simulation, without changing the pass criteria.

Numerical policy results, continuity and accounting residuals are saved in `runs/complete_overflow_check_20261010/diagnostic.csv`; `g0.json`, `run_config.json`, `rule_explanations.csv` and `hydrographs.csv` preserve the evidence. A summary is generated separately after the diagnostic completes. Failures are retained. Do not promote a candidate with worse flooding merely because CSO decreases.

The completed six-event check rejects the candidate as a safe replacement. On the three validation parents, the candidate passes flood non-regression on **1/3**, passes the complete scorecard on **0/3**, and changes the raw half-open action on **100%** of steps. Native versus candidate validation totals are respectively **169,821 versus 180,414 m³ CSO**, **15,084 versus 5,360 m³ flooding**, and **184,905 versus 185,774 m³ total overflow**. The aggregate flood reduction hides serious event-level regressions: on 2021-06-20 native has zero flooding while the candidate adds **614 m³**; on 2021-06-25 flooding rises from **51 to 2,047 m³**. This is not acceptable under the stated priority. Always-closing bypasses also fails two of three validation flood comparisons. No trained model has been improved or declared successful by this diagnostic.

All runs cover 288 intervals. Routing continuity errors range from **−1.97% to +1.46%**, and runoff errors from **−1.28% to −0.21%**. Summed cumulative node outflows differ from the independently accumulated system outflow statistic by up to **0.809%**; flood accounting differs by up to **31.88 m³**. These residuals are reported, not suppressed or silently assigned a passing threshold. Their source and acceptable numerical tolerance need to be resolved before publication-quality comparisons. The new method eliminates the much larger conceptual bypass omission and endpoint-sampling problem but should not be described as exact mass-balance closure.

## Position relative to the literature

Google was attempted as requested but returned an unusual-traffic block. Publisher, institutional and author-deposited records were used instead. This is a targeted review, not a completed systematic novelty search.

- **Tian et al., Water Research 249 (2024), 120912** uses Sobol sensitivity, tree surrogates and conditional probabilities to interpret DQN/PPO drainage control. Its identified failure conditions include full storage, peaks already past actuators, and concentrated inflows. Interpretability alone is therefore not new. Our candidate difference is an operational symbolic safety layer with faithful intervention traces, which still needs quantitative explanation testing. [Paper](https://pubmed.ncbi.nlm.nih.gov/38042066/).
- **Tian et al., Water Resources Research 58 (2022), e2021WR030703** combines multiple RL methods and MPC for reliable CSO/flood mitigation. Reliable control and RL/MPC hybrids are established prior work. A proposed predictive shield must be compared against this family, not called the first safe controller. [Paper](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2021WR030703).
- **Tian et al., Water Research 289 (2026), 124901**, online November 2025, uses knowledge-generated data for pretraining followed by RL fine-tuning. It reports comparable mitigation with about 90% less training time. That number is a training-time reduction, **not a 90% CSO reduction**. Knowledge-data fusion alone is not a new claim. [Institutional record](https://scholars.cityu.edu.hk/en/publications/a-knowledge-data-fusion-framework-accelerates-deep-reinforcement-/).
- **Zhang, Tian and Liao, Water Research 229 (2023), 119498** studies decentralised multi-agent control and communication robustness. Reported reductions depend on the case and reference: 5.62–9.30% CSO against a static benchmark, and 14.39–21.36% CSO/flood volume against existing rules in another case. These percentages cannot be compared directly with this repository's old 30% figure. [Paper](https://www.sciencedirect.com/science/article/pii/S0043135422014439).
- **Yin et al., World Environmental and Water Resources Congress (2023), pp. 711–722** applies RL with SWMM to the Detroit Puritan-Fenkell/7-mile case. This is a conference paper, not a Water Resources Research journal article. It is a particularly relevant comparator because of the case study, but reproducible model/control/rainfall equivalence must be established. [Paper](https://ascelibrary.org/doi/abs/10.1061/9780784484852.067).
- **Yin et al., Journal of Hydrology 628 (2024), 130515**, “Forecasting and optimization for minimizing combined sewer overflows using Machine learning frameworks and its inversion techniques,” develops surrogate/inverse optimisation. It is another relevant local-case comparator; reproduce its rainfall, initial conditions and discharge boundary before claiming superiority. [Author-deposited paper](https://par.nsf.gov/servlets/purl/10523713), [DOI](https://doi.org/10.1016/j.jhydrol.2023.130515).
- **Wu, Tian et al., Water Research, 126788**, available online in 2026 with a 2027 issue assignment, explicitly addresses fuller storage utilisation using DRL and green infrastructure. Maximising storage utilisation alone cannot establish novelty. [Institutional record](https://scholars.cityu.edu.hk/en/publications/toward-the-full-utilization-of-storage-capacity-urban-drainage-sy/).

A defensible candidate contribution is the **combination** of flood-feasible learning/selection, topology-dependent untreated-bypass control, usable-storage semantics and auditable intervention explanations, evaluated with complete accounting. This is a research hypothesis, not a verified first-in-literature claim.

## Next experiment sequence and decision rules

The user confirmed retaining validation **2021–2022** and test **2023–2026** on 10 October 2026, and delegated compute sizing. Start with one SWMM process and a 30-minute diagnostic cap. A later 20-episode integration smoke test is appropriate only after rebuilding the prerequisite evidence; do not launch a multi-day matrix yet.

1. Rebuild G1 onset for the new four-outfall objective using train/validation parents for development. Preserve the threshold median ≤4 and <30% no-onset; stop and inspect physical rainfall if it fails. Never select eligibility using test outcomes.
2. Repair frequency-table provenance and rung/ceiling consistency. Use verified ≤100-year scenarios first; obtain official Atlas 14 durations and confidence intervals before extreme-rung claims. Keep all children with their parent and label every amplified event as amplified.
3. Rebuild G2 with flood-feasible static/CMA search and complete volumes, including native as an available reference comparator. Preserve default/open/closed schedules and failed cases. Calibrate B3 on TRAIN, select on VAL. If rules match RL, report that finding.
4. Replace the global reactive flood switch with a topology-local, short-horizon safety check if the new failures persist. A dry downstream storage node does not imply an upstream junction can safely be held closed for 15 minutes. Test action directions and transport delays; consider shorter control intervals and gate slew limits, recording these as protocol changes. Do not simply increase flood penalties until the figure looks better.
5. Train SAC-plain, SAC-Lag-only, rules and full NS-SAC under the **same complete objective**. Use 3 seeds minimum, target 5. Do not compare a new four-outfall controller against legacy two-weir checkpoint percentages. Select only validation-feasible models, reject missing safety evidence, and report no acceptable checkpoint when none passes.
6. Predeclare per-event and per-node flood constraints, a physical zero tolerance in m³, total-overflow non-regression, continuity acceptance limits, and both physical/usable storage metrics. The prototype interprets the absolute flood tolerance as **10 m³**; this is explicit and does not preserve the much larger implicit legacy CFS-sum tolerance.
7. Freeze the amended protocol before further test evaluation and disclose previous exposure. Evaluate all methods on identical held-out storms; average children within parent before hierarchical event/seed bootstraps, paired tests and Holm corrections. Undefined percentage reduction on zero-CSO reference events remains undefined; report absolute added spill and retain those events in safety and micro totals.
8. Evaluate interpretability: intervention frequency/magnitude, triggered rule and affected nodes, counterfactual changes when a trigger crosses its threshold, fidelity of any actor surrogate, and operator-readable event traces. A rule trace is not proof that the entire actor is transparent.

No honest experiment can guarantee better results than published literature in advance. The thesis should test that hypothesis against matched baselines and report failures and physical limits. Correctly exposing unsafe apparent gains is already a valuable improvement in the research method.

## Cleanup and reproduction

Removed **17,283 generated temporary INP/OUT/RPT files, 11,673,171,403 bytes**, after checking their resolved paths and that no simulation was active. `runs/cleanup_20261010.csv` records them. Two SHA256-identical patch copies were removed while keeping `patches/APP_PATCHES.md`. Raw rainfall, historical results, checkpoints, source and the existing Linux environment were retained. The new complete environment cleans its own generated files on reset/close.

A Windows-compatible `.venv-win` was created; NumPy 1.26.4 resolves the installed Torch 2.2.2 NumPy ABI problem. `requirements-windows-tested.txt` records direct tested versions. This uses existing system packages and is not yet a portable full environment lock.

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\python.exe -m research.audit_thesis
.\.venv-win\Scripts\python.exe -m research.complete_overflow_check
.\.venv-win\Scripts\python.exe -m research.summarize_complete_overflow
```

Verification on 10 October: **60 tests passed**, including the existing v7 golden trajectory, a complete 72-hour native episode, selective loading, physical accounting, flood-first search and SAC-Lag checkpoint restoration. A passing software test suite is not a passing hydraulic efficacy gate.

SWMM implementation references: [PySWMM node statistics](https://pyswmm.github.io/pyswmm/reference/api/api/pyswmm.nodes.Node.statistics.html), [OWA cumulative-node implementation](https://github.com/OpenWaterAnalytics/Stormwater-Management-Model/blob/master/src/solver/toolkit.c), [EPA tabular storage integration](https://github.com/USEPA/Stormwater-Management-Model/blob/develop/src/solver/table.c). Installed PySWMM 2.2.0 methods were inspected before use. The diagnostic compares summed outlet/node volumes against system statistics and reports the residual rather than assuming exact equality.

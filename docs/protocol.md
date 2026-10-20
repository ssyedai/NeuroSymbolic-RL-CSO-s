# Protocol v1 — NS-SAFE-SAC v8 (draft; not frozen)

> **Invalidated before official training, 2026-10-20.** The repository has no
> `protocol-v1` tag and the complete-objective native hydraulic refinement gate
> fails at 1.422% versus the unchanged 1% limit. The existing scenario catalog
> also predates corrected four-outfall onset evidence and the verified Atlas
> table. Preserve the hypotheses and thresholds below as the preregistration
> draft, but rebuild G1/G2/B3 and scenarios after hydraulic acceptance before
> tagging. See `docs/training_readiness_20261020.md`.

> **Latest decision, 2026-10-20:** Integrated storage-volume correction passes 72/72 valid isolated hydraulic cases but fails both native TRAIN network refinements (1.762340%, 2.581679%; limit 1%). No engine adoption or training. Software: 90 passed and golden compatibility rechecked. See docs/integral_storage_verification_20261020.md.

> **Latest decision, 2026-10-19:** Exact read-only replays identify remaining failures around 1360_B and its endpoints. Increasing MAX_TRIALS to 200 reduces nonconverging steps to about 4.2% but still fails the finest refinement: 78.845283 m3 (2.073436%), limit 38.026394 m3. No engine adoption or downstream experiments. See docs/surface_failure_attribution_20261019.md.

> **Latest decision, 2026-10-19:** A verified upstream conduit-area branch discontinuity causes a repeating junction solver cycle. The continuous-allocation candidate passes six compiled boundary/control groups and 60/60 isolated tests, but fails both network refinements (2.06%, 1.62%). Candidate rejected; training and downstream experiments remain blocked. Software suite: 90 passed. See `docs/conduit_surface_transition_20261019.md`.

> **Stride localization, 2026-10-19:** Both read-only replays exactly reproduce all recorded final metrics. The 127.499 m³ finest-step difference is entirely at outfall 65; the largest interval contributions occur at 22.75–23 h (75.847 m³) and 31.5–31.75 h (45.836 m³). Hydraulic acceptance still fails; training remains blocked. See `docs/stride_localization_20261019.md`.

> **Latest verification, 2026-10-19:** Fixed one-second rule cadence still fails the finest comparison (3.43%). Requiring node continuity before conduit bypass passes 60/60 isolated checks but 0/2 network comparisons (1.35% and 3.20%). No production adoption or research training. Training/validation severity ceilings now check declared T rungs as well as fitted values, reject unknown research severity, and require a separate research validation set. Software tests: 90 passed. See `docs/balance_bypass_verification_20261019.md`.

> **Latest execution, 2026-10-17:** A bracketed storage/outfall-weir correction passes 60/60 isolated tests but only 1/2 network refinement comparisons. The 0.5→0.25 s CSO difference is 157.365 m³ (3.898%), so no production adoption or training. Official NOAA Atlas 14 tables for Detroit City Airport (42.4072, -83.0089), including 90% bounds, are now verified and selected for future scenario rebuilding under user authorization. Parent-event statistics tooling and model/data cards are prepared. Software suite: 87 passed. See `docs/bracket_verification_20261017.md` and `docs/reproduction_current.md`.

> **Coupled endpoint diagnostic, 2026-10-17:** All 36 synthetic cases meet independent discrete-trajectory checks, but only 18/36 have no unconverged steps. The simplified constant-area system does not reproduce the large network discrepancy. Next: actual tabular geometry, wetting/submergence and surrounding connections. Full-network refinement remains 0/2 and training remains blocked. See `docs/coupled_balance_verification_20261017.md`. Software tests: 83 passed.

> **Network failure attribution, 2026-10-17:** Read-only logging reproduces all prior recorded hydraulic metrics exactly. Of 1,036,800 steps, 268,943 remain unconverged; storage 35440 fails continuity on 267,882 of them (99.61%), while its head-change check always passes. Gate 1360_B has 164,558 final-flow failures. Counts overlap. See `docs/network_failure_attribution_20261017.md`. The next target is coupled junction/orifice/storage iteration; full-network refinement remains 0/2 and training remains blocked.

> **Continuity-check diagnostic, 2026-10-17:** Adding a strict ordinary-node continuity residual check to the separate continuous-law candidate resolves the isolated balance failures (60/60 combined isolated cases pass). Neither fixed TRAIN network refinement comparison passes (0/2). Acceptance thresholds, original physical inputs, production defaults and research splits remain unchanged; the alternative hydraulic formulation is not adopted. See `docs/continuity_verification_20261017.md`.

> **Alternative-formulation diagnostic, 2026-10-17:** The isolated no-root certificate motivated an explicitly labelled continuous near-zero SIDE-orifice law in separate DLLs. This changes the discharge formulation and is not adopted. Even with final-head convergence checks, two of twelve isolated balance checks fail. Numerical acceptance limits, production hydraulics and research splits remain unchanged. See `docs/cutoff_formulation_analysis_20261017.md`.

> **Retry diagnostic, 2026-10-17:** Isolated step rejection uses full restart and exact replay of accepted history, with unchanged equations and a final-head residual check. One crossing case still fails at the predeclared minimum step and is stopped; no thresholds are loosened. This synthetic diagnostic does not alter splits, thesis scenarios, production solver or freeze status. See `docs/retry_verification_20261017.md`.

> **Read-only solver instrumentation, 2026-10-17:** Four isolated replays preserve exact sampled hydraulic states and system totals while logging internal iterations. No equation, acceptance gate, split or production default changed. Evidence distinguishes head-only false convergence, unresolved iteration-cap exits and temporal alternation; see `docs/transition_trace_20261017.md`. Training remains blocked.

> **Reversing-flow diagnostic, 2026-10-17:** A new rain-free, fixed-gate synthetic matrix isolates cutoff crossings using prescribed tailwater. Both engines fail every crossing case under the predeclared final-head flow check while passing inside-cutoff controls. This is numerical diagnosis, not a new scenario family or thesis performance result. No split, physical model, cutoff, production solver, acceptance gate or freeze is changed. See `docs/reversing_orifice_verification_20261017.md`.

> **Regulator diagnostic, 2026-10-17:** Extending the separate coupled solver to orifices and junction endpoints passes 48/48 isolated steady cases; neither full-network refinement comparison passes (0/2). No production change or new freeze follows. The same TRAIN storm, physical inputs and thresholds are retained; see `docs/regulator_verification_20261017.md`. Unsteady flow near the small-head cutoff remains unverified.

> **Coupled-update diagnostic, 2026-10-16:** A separate engine adds a finite-difference storage/weir sensitivity term while preserving discharge equations and native control. All 24 isolated verification cases pass, but both full-network refinement checks fail on the same fixed TRAIN parent. Six baseline/candidate network runs verify the separate-DLL path and test transfer. No production engine, physical model, selection rule, split or tolerance is changed; no new freeze or control-performance claim follows. See `docs/coupled_weir_verification_20261016.md`.

> **Flow-convergence diagnostic, 2026-10-16:** A separate engine fork adds a 0.1% relative / 0.001 CFS absolute weir-flow iteration check and prevents head-only bypass of weirs. This is distinct from policy thresholds or thesis acceptance gates. The unchanged 24-case isolated verification matrix still fails four cases; the fork is not installed or adopted. Full-network training remains blocked. See `docs/flow_guard_verification_20261016.md`.

> **Verification addendum, 2026-10-16:** Isolated synthetic storage/weir cases are numerical unit experiments, not rainfall scenarios or additions to the research splits. The installed engine, an unmodified separate source build, and an explicitly experimental damping build were compared in 72 short runs. The damping build failed and is not adopted. See `docs/isolated_weir_verification_20261016.md` for the corrected source hypothesis and reproduction. No G0–G3 approval, new protocol freeze or performance gain follows from these results.

> **Submerged-weir addendum, 2026-10-12:** The 7 Mile native trace and 100-trial/1e-7 ft tolerance probe remain diagnostic only. Both routing-refinement checks fail despite zero flooding; details and original-source hypothesis are in `docs/weir_diagnostic_20261012.md`. No geometry, boundary condition, engine implementation, production defaults, split or acceptance threshold is changed. Numerical reductions must not be attributed to the learned policy. Training remains blocked pending reliable hydraulics.

> **Diagnostic addendum, 2026-10-12:** Routing-step traces and explicit SLOT surcharge experiments are documented in `docs/surcharge_diagnostic_20261011.md`. Both SLOT accuracy profiles fail the unchanged numerical screen. These are TRAIN-only experiments; the original INP, reference definition, production defaults and split years are preserved. SLOT results must not be pooled with EXTRAN results or credited as learned-controller gains. No new protocol freeze is claimed.

> **Numerical validation addendum, 2026-10-11:** TRAIN-only diagnostic profiles at 1/0.5/0.25-second routing, native pump safeguards, and an explicit tighter-solver ablation failed the pre-recorded numerical screen. These experiments do not alter production settings, original native rules, policy safety tolerances, or split years. See `docs/fine_hydraulic_validation_20261011.md`; a fixed-rule-cadence probe is separately labelled as a changed-controller diagnostic. This is not a new freeze.

> **Deviation 2026-10-11:** Corrected external control ownership by removing native rules only in generated externally controlled episodes; native runs keep original rules. Controlled pumps remain commanded ON and this difference must be reported. Actual gate travel times are retained and logged. Reverse JCT boundary inflow is separated from treated-route outward volume. The new baseline tag is v6; see `docs/hydraulic_validation_20261011.md`. These are diagnostic repairs, not a new protocol freeze or permission to evaluate TEST.

> **Deviation recorded 2026-10-10 — not a new freeze:** The user confirmed untreated CSO outfalls 54, 65, 54_B, 65_B and prioritised nodal flooding, then CSO, with total undesired overflow = their sum. The original objective omitted bypass flow. Prior G1/G2/G3 evidence and theta are not transferable to this objective. The complete prototype uses cumulative m³, all 288 intervals, a separate usable-storage metric and an explicit 10 m³ absolute flood tolerance. The user confirmed retaining VAL 2021–2022 and TEST 2023–2026. Prior TEST exposure is acknowledged; no new claim of an untouched holdout or a Git-tagged protocol is made. The local `atlas14_mm.csv` has unverified official provenance, so extreme-return-period claims are suspended. See `docs/thesis_audit_20261010.md` and the new diagnostic's `run_config.json`. Historical frozen text follows unchanged for traceability.

**Status: FROZEN for paper runs.** Do not change splits, scenario params, θ, or
selection score without recording a deviation. Test-split evaluation for claims
begins only after this freeze. (No git repo yet — apply `git tag protocol-v1`
after the first commit.)

Where this file and older Stage-10+ notes disagree, **this file + `AGENTS.md` win**.

---

## Gates completed

| Gate | Result |
|------|--------|
| G0 diagnostics | PASS — storage `35390/35391/35440/35442`; native@reset = INP 1.0; CFS |
| G1 onset | PASS — n=416, median `k_onset`=3.72, no-onset=0% (`runs/onset_table.csv`) |
| G2 controllability | PASS — stratified n=210; all rung medians ≥10%; `uncontrollable_rungs=[]` |
| G3 pilot | PASS (smoke) — `v8_pilot_s0` 300 eps; λ 0.48→0.22; val CSO red ~10% |

---

## Hypotheses (v8 — AGENTS.md §8)

- **H1** V8-Full reduces CSO vs true native on TEST-R and TEST-L; macro > 0 with CI excluding 0; flood non-regression ≥ 95%.
- **H2** V8-Full ≥ B3 on TEST-L.
- **H3** V8-Full ≥ SAC-plain and SAC-Lag-only on CSO reduction; fewer storage-first / flood regressions.
- **H4** Each of topology-KB, store-first, Lagrangian, shield contributes on ≥ 1 primary metric.
- **H5** D2 ≥ D1 and D4 on held-out observed; D3 does not improve on D2.
- **H6** Gains concentrate in 5–25 yr; above 100 yr match ref; report ref/hind flood as floor.

---

## Data & scenarios (frozen)

- Gauge: NCEI HPD `USC00200230` (Ann Arbor). Parents: `data/useful/rain_real_full`, year ≥ 2010, total ≥ 12 mm (416).
- Scenarios: `data/useful/rain_scenarios/`
- **val-years:** 2021, 2022
- **test-years:** 2023, 2024, 2025, 2026
- Atlas: `atlas14_mm.csv` (= `configs/pfds_detroit_mm.csv`)
- Ladder train: 5,10,25,50,100; ladder test: 200,500,1000; C mults: 1,1.5,2,3; flat F: 2
- `max_spread=10`, `k_hi=4`, `k_cap=12`, `min_R_anchor_mm=15`
- Topology: `runs/gate_topology.csv` (no gate feeds CSO weir without storage)
- Physical rain only: `physical_rain=True`, `scaling=none`; unique per-process INPs under `runs/_physical_inp/`
- Baseline tag: `v3|physrain|nativefix|kb8`
- Primary reference: TRUE native (`rec["native"]`)

### Test sets (fixed)

- **TEST-R:** family R, split test  
- **TEST-L:** families T≤100 and C, split test  
- **TEST-X:** T200/T500/T1000, split test  

---

## Training (frozen defaults)

- Diet default: **D2_ladder100** (R+T+C, `train_max_T=100`, no test-only rungs)
- Eligibility: G2 uncontrollable rungs excluded (none at freeze)
- θ: `runs/theta.json` (sha256 `b9954934ed35111e73d16bd85bcfcece53d80eb4b391a6e7f314c845b7be9abd`), calibrated CMA early-stop gen 6 on 16 train / 8 val
- Warm-up: 2000 random 7-D steps; `updates_per_step=0.25`
- Selection score: mean over rungs of macro CSO reduction vs native; −100 if flood_nonregress_rate < 0.95 or mean intervention_rate > 0.5
- Seeds: target 5 (minimum 3)
- Episodes: 1000 for full runs; pilot used 300

---

## Tier 1 matrix (must)

B0 static 0.5 · B1 true native · B2 KB-v8 default θ · B3 optimised θ · O1 hindsight  
V7 (physical) · **V8-Full** · SAC-plain · SAC-Lag-only  

---

## Statistics

- Unit of analysis = **parent event** (average children first)
- Hierarchical bootstrap CIs; paired Wilcoxon + Holm across pre-registered comparisons

---

## Deviations log

| Date | Deviation |
|------|-----------|
| 2026-10-09 | G3 pilot run on `rain_scenarios_smoke` (32 storms), not full catalog |
| 2026-10-09 | θ calibrated on 16 train / 8 val (not full sets) for compute |
| 2026-10-09 | G2 used ≤15 storms/rung, static-n=24, skip-CMA |
| 2026-10-09 | No git repo at freeze — tag deferred until `git init` + first commit |

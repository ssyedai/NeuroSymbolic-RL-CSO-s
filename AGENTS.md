# AGENTS.md — NS-SAFE-SAC v8: master implementation plan (read this first)

You are a coding agent working **on top of an existing repository** (SWMM + SAC + neurosymbolic knowledge base for CSO control on a Detroit combined-sewer model). This file tells you what to build, in what order, how to test it, and when to **stop and ask**. Rationale and background live in `docs/v8_guide.md`; **exact edits to `app.py` are in `patches/APP_PATCHES.md`**. Where this file and `docs/v8_guide.md` differ, **this file wins**.

---

## 1. Mission and success criteria

Train a neurosymbolic SAC agent that, **for heavy storms**, controls 7 gates so that
1. **CSO is minimised**, 2. **storage is used before overflow** (overflow only when storage is full), 3. **no flooding is added** (never worse than the true native control; zero flood whenever the reference/hindsight optimum is flood-free).

Real unamplified rain produces **no CSO** in this model, so training and evaluation use **amplified historical rain** (same temporal pattern, larger magnitude) in addition to the real events. Everything is evaluated against the network's **true native control** (the INP's own rules) and against a **hindsight optimum**.

Success = every item in §11 is checked.

---

## 2. Definitions (use these words exactly in code, logs and reports)

| Term | Meaning |
|------|---------|
| **Parent event** | One real observed storm (72 h window, 288 × 15 min). |
| **Amplification factor `k`** | One scalar multiplying every 15-min depth of a parent event. The hyetograph **shape is unchanged**; only magnitude changes. |
| **Return period `T` (yr)**, **AEP** | AEP = 1/T = probability that the rainfall depth for a **given duration** is met or exceeded at a point in any one year. A "1000-yr event" has AEP 0.1%. It is defined **per duration**: a storm can be 1000-yr at 1 h and only 50-yr at 24 h. In this project `T_anchor` = equivalent return period of the **6 h** depth. P(at least one in N years) = 1−(1−1/T)^N (1000-yr: ≈3% in 30 yr). |
| **Family R** | Unscaled observed events (`provenance="observed"`). |
| **Family T** (rung `T<n>`) | Amplified so the 6 h depth equals the design depth of `n` years (Atlas 14 table if given, else Detroit IDF fit ≤ 100 yr). |
| **Family C** (rung `C<m>`) | Amplified to `k = m · k_onset`, where **`k_onset`** is the smallest `k` at which the network starts to spill under true native control. Guarantees CSO exists. |
| **Family F** (rung `F<k>`) | Flat multiplier (e.g. ×2). **Ablation diet only.** |
| **Reference (`ref`)** | True native control run on the same storm. Primary comparator for every % reduction. |
| **Hindsight (`hind`)** | Best open-loop gate schedule found by search on that storm (upper bound; regret reference). |
| **Storage-first** | Property `G( cso_t > ε → store_fill_ratio_t ≥ 1−δ )`. |
| **Flood non-regression** | `flood_agent ≤ flood_ref·(1+2%) + 10`. **Zero-when-feasible**: if `flood_ref ≈ 0` the agent must also have ≈ 0. |
| **Training ceiling `train_max_T`** | Largest `T_anchor` allowed in training data. Default 100. Set 1000 only for diet D3. |

Labelling rule: amplified events are **never** called "observed". Report observed (R) and amplified (T/C/F) results in separate columns/tables.

---

## 3. How the two techniques you were asked to support are handled

- **Amplification (your "2×")** is kept and generalised. A flat ×2 gives an uncontrolled severity mix (≈68% of post-2010 events stay < 1-yr, ≈4% jump past 100-yr). The default scenario set therefore uses **T-anchored** and **CSO-onset-anchored** amplification, which preserve the real pattern and control severity. Flat ×2 (family F) stays available as diet **D1** for comparison.
- **1000-yr events** are **in scope**: they are built (needs the NOAA Atlas 14 depth table; the IDF fit is not used above 100 yr) and **evaluated** on test parents (rungs `T200/T500/T1000`). Whether they are also **trained on** is decided empirically by diet **D3** and by the controllability screen (§6 T09), not assumed. Reason to be careful: the SWMM calibration window only reached about a 1.8-yr storm; at extreme severity flooding becomes physically unavoidable (so "no flood" must mean non-regression), and a few huge returns can dominate learning.

---

## 4. Hard rules (do not violate)

1. **Opt-in only.** Every change to `app.py` is behind a flag whose default reproduces v7. `tests/test_golden.py` must pass after every task.
2. **Physical rain only** in research runs: `physical_rain=True`, `real_only=True`, `scaling="none"`. Never use the legacy path (it passes mm as in/h → ×6.35 inflation).
3. **No on-the-fly scaling or augmentation.** All amplified storms are pre-built files with a manifest entry; `research/guard.py::assert_provenance` runs at the start of audit, training and evaluation.
4. **Split by parent event/year.** Children inherit the parent's split. **Never read the test split** in training, tuning, selection, rule calibration or controllability-based eligibility.
5. **True native reference.** Never use the old cache (`tag` must include `nativefix`).
6. One SWMM simulation per **process**. Parallelise over processes only.
7. Depth units follow the INP (`FLOW_UNITS CFS` ⇒ **feet**). Do not label them metres.
8. Every run writes `run_config.json` (all flags, seeds, git hash, library versions, manifest hash, `theta.json` hash).
9. If a **gate (G0–G3)** fails, **stop and report** with the numbers; do not "fix" by loosening thresholds silently.
10. Do not guess API names: pyswmm calls marked **[VERIFY]** must be checked against the installed version.

---

## 5. Repository map

Unzip the bundle at the repository root.

| Path | Status | Purpose | Tested here |
|------|--------|---------|-------------|
| `app.py` | existing | env, v7 KB, SAC | – (apply `patches/APP_PATCHES.md`) |
| `multistorm/*` (existing) | existing | pipeline from earlier stages | – |
| `research/idf.py` | **new** | Detroit IDF, `T_eq`, AEP language | yes |
| `research/scenarios.py` | **new** | R/T/C/F families, shape filter, parent splits | yes |
| `research/onset.py`, `research/onset_table.py` | **new** | `k_onset` search (CLI needs env) | `onset.py` yes |
| `research/build_scaled_storms.py` | **new** | builds scenario dir + manifest + splits | yes |
| `research/guard.py` | **new** | provenance/hash guard | yes |
| `research/topology.py` | **new** | gate→storage/weir map from INP graph | yes |
| `research/diag_semantics.py` | **new** | Stage-0 diagnostics | syntax only |
| `research/controllability.py` | **new** | hindsight search | yes (fake evaluator) |
| `research/optimize_rules.py` | **new** | calibrate shield θ (B3) | yes (fake evaluator) |
| `multistorm/kb_v8.py` | **new** | topology shield, storage-first reward, cost | yes |
| `multistorm/obsfeat.py` | **new** | causal rain features | yes |
| `multistorm/stl.py`, `metrics_v8.py` | **new** | storage-first metrics, regret, non-regression | yes |
| `multistorm/samplers.py`, `replay.py` | **new** | rung-stratified sampler, ring replay | yes |
| `multistorm/agents_lag.py` | **new** | SAC-Lag agent | **not run here (no torch)**; `tests/test_agents_lag.py` skips until you run it |
| `tests/*` | **new** | `pytest -q` → expect **19 passed, 1 skipped** before torch tests are enabled | – |

Install: `pip install networkx cma pytest` (plus your existing torch/pyswmm stack).

---

## 6. Work breakdown (do in order; `Dep` = dependencies)

### T00 — Setup  (Dep: none)
Unzip bundle; `pip install networkx cma pytest`; `pytest -q`. **Accept:** 19 passed, 1 skipped (or 22+ passed if torch/app import works).

### T01 — Golden freeze  (Dep: T00)
Ensure `tests/test_golden.py` exists and passes on untouched v7 (see earlier Stage 0). **Accept:** passes; committed.

### T02 — Diagnostics  (Dep: T01)  → **GATE G0**
Run `python -m research.diag_semantics`. Save the printed output to `runs/diag_report.txt`; it also writes `runs/diag_nodes.csv`, `runs/diag_links.csv`.
**G0 passes only if all hold:** (a) `storage` node count > 0 and the previous "storage" nodes `54/54_B` are **not** the only candidates; (b) `max|depth(wet)−depth(dry)|` for the chosen storage units is clearly > 0 (storage responds to rain); (c) native-mode initial gate settings equal the INP-native settings (after T03); (d) `FLOW_UNITS` known. If (a) or (b) fails, **STOP**: the storage state used so far is not a storm-responsive storage; report the table.

### T03 — Patch `app.py`  (Dep: T02)
Apply `patches/APP_PATCHES.md` P1–P8 exactly. Add the 5 tests listed at its end. **Accept:** golden test + new tests pass; `python -m research.diag_semantics` shows native-mode initial settings = INP-native.

### T04 — Rebuild references  (Dep: T03)
Apply P9 (`tag="v3|physrain|nativefix|kb8"`); delete the old `runs/baseline_cache.json`. Recompute `native` (true native) and `static` records lazily. **Accept:** cache contains `tag` in keys; native records differ from static where the INP rules differ.

### T05 — Topology  (Dep: T02)
`python -m research.topology` → `runs/gate_topology.csv`. Print the list of gates that reach a CSO weir **without** passing storage. **Accept:** file exists; send the table to the user for confirmation (it replaces the "topology ambiguous" comment for gates 3 and 4).

### T06 — Onset table  (Dep: T03, T04)  → **GATE G1**
```bash
python -m research.onset_table --rain-dir rain_real_full --events rain_real_full/events.csv --min-year 2010
```
Check `A.native_fn(env)` signature **[VERIFY]**; adapt only the wrapper. ~8 s per simulation; ≈ 7–11 runs per parent; run in parallel processes if needed (split `--max-parents`).
**G1 passes only if:** median `k_onset` ≤ 4 **and** < 30% of parents have no onset within `k_cap`. Otherwise the rain is not stressing the network at plausible magnitudes: **STOP**, run the dose–response (scale one event by k ∈ {1,2,4,6.35,10,25.4}) and re-check units/rain injection before building anything.

### T07 — Build scenarios  (Dep: T06; Atlas table optional)
```bash
python -m research.build_scaled_storms --rain-dir rain_real_full --events rain_real_full/events.csv \
  --onset runs/onset_table.csv --atlas atlas14_mm.csv --out rain_scenarios \
  --val-years <Y,..> --test-years <Y,..> --min-year 2010 \
  --ladder-train 5,10,25,50,100 --ladder-test 200,500,1000 --mults 1,1.5,2,3 --flat-factors 2
```
`atlas14_mm.csv`: column `duration_min` (60, 180, 360, 1440) + one column per ARI in years, depths in mm. Without it, rungs > 100 yr are skipped (`needs_atlas14_table` in `rejected.csv`). Val/test years are **chosen by the user**; do not choose them by looking at results.
**Accept:** printed table `split × rung` has ≥ 3 parents per split for every rung used in an experiment; `rejected.csv` reviewed. If `implausible_shape` dominates, raise `--max-spread` (default 10) **and record the value** in `docs/protocol.md`.

### T08 — Loader, guard, CLI flags  (Dep: T07)
Apply P10. In `train_multi.py`, `audit.py`, `evaluate.py` call `assert_provenance(storms, rain_dir)` right after loading. Add CLI flags: `--diet {D1_flat2,D2_ladder100,D3_ladder1000,D4_real,D5_all}`, `--train-max-T` (default 100), `--allow-test-only-rungs` (D3 only), `--primary-observed-only`.
Training pool rule: `split=="train"` and `meta["T_anchor"] ≤ train_max_T` and (`not meta["test_only"]` or `--allow-test-only-rungs`) and eligible by T09. Diet → families: D1: R+F; D2: R+T+C; D3: R+T+C with `--train-max-T 1000 --allow-test-only-rungs`; D4: R; D5: R+T+C+F.
**Accept:** unit test that a tampered file raises; that D2 excludes `T200+` and any `split!="train"`.

### T09 — Controllability screen  (Dep: T05–T08)  → **GATE G2**
Write `research/run_controllability.py` using `research/controllability.py`: for every **train and val** storm, `static_search(..., use_projection=False)` (n=64) then `cma_search` (n_seg=4, iters 25, pop 12) when the static optimum is within 5% of the reference; also run once with `use_projection=True`. `evaluate_fn(policy, storm, use_projection)` is the single-storm path of `multistorm/evaluate.py` (policy needs `select_action(obs, deterministic)`; reset `SchedulePolicy` per episode). Write `runs/controllability.csv` (columns: storm_id, rung, ref_cso, best_static_cso, best_hind_cso, achievable_pct_static, achievable_pct_hind, ref_flood, best_flood).
**G2:** per rung, median `achievable_pct_hind` ≥ 10%. Rungs below 5% are flagged `uncontrollable` and removed from **training eligibility** (kept for test). Never use test-split storms in this step.
Budget ≈ 8 min (static) + ≈ 40 min (CMA) per storm; parallelise.

### T10 — v8 stack  (Dep: T03, T05)
Add `build_v8` and `train_one_episode_v8` from P11/P12 to `multistorm/adapters.py`. Add `--variant {v7,v8,plain,lag_only,...}` in `train_multi.py`. Apply SAC-Lag with `policy_dim=7`.
**Accept (needs torch):** `pytest tests/test_agents_lag.py -q` passes; a 20-episode smoke run completes with no NaN and logs `lam`, `cost`, `intervention`.

### T11 — Rule calibration, baseline B3  (Dep: T05, T08, T09)
Write `research/run_optimize_rules.py` using `research/optimize_rules.py::optimize` with `evaluate_fn(theta, storm)` that builds `KnowledgeBaseV8(theta=theta)`, runs a constant raw action (gates 0.5, shield **on**) and returns `(summary, ref)`. Train storms only; early-stop on val. Save `runs/theta.json` (+ sha256). **Accept:** B3 beats B2 (default θ) on **val**; otherwise report that rule tuning did not help.

### T12 — Training integration  (Dep: T08, T10, T11)
`train_multi.py` for `--variant v8`:
- reference per storm from `bstore.get(storm)["native"]`; `options.reference_cso = native["cso_total"]`;
- `StratifiedSampler` over rungs (`meta["rung"]`); log per-rung stats;
- warm-up 2000 random 7-D steps, then `updates_per_step` (default 0.25; pilot 1.0);
- validation every `eval_every` episodes on VAL (all rungs ≤ `train_max_T`), deterministic policy, no updates, no replay writes;
- **selection score** = mean over rungs of the macro CSO reduction vs native; infeasible (score − 100) if `flood_nonregress_rate < 0.95` **or** mean intervention rate > 0.5 (investigate rather than lower);
- checkpoint metadata: kb version, θ hash, manifest hash, `lam`.
**Accept:** smoke run → `train_log.csv`, `eval_log.csv`, `best_val.pt`.

### T13 — Evaluation integration  (Dep: T12)
In `evaluate()` merge per row: `episode_summary`, `extended_summary` (metrics_ext), `storage_metrics(L)` (stl), `metrics_v8.enrich(s, ref, hind)`; add columns `family, rung, k, T_anchor, parent`. Aggregate with `aggregate()` per `split × rung`. **Accept:** `final_eval.csv` contains all columns in §9; evaluating the same checkpoint twice gives identical numbers.

### T14 — Baselines/comparators  (Dep: T11, T13)
Implement as policies/variants (same evaluation path): **B0** static 0.5 (shield off), **B1** true native, **B2** KB-v8 rules with default θ, **B3** optimised θ, **O1** hindsight (from T09), **V7** (v7 stack retrained under physical rain), **SAC-plain** (`use_projection=False`, no rain features, `w_store=0`, no Lagrangian), **SAC-Lag-only** (no shield, `w_store=0`). Ablations of V8-Full: `−topo` (use v7 rules), `−store_first (w_store=0)`, `−Lagrangian (lam_init=0, lam_lr=0)`, `−shield (use_projection=False)`, `−rain features`, `10-D policy`. Optional comparator: DDPG.

### T15 — Pilot  (Dep: T14)  → **GATE G3**
1 seed × each variant × 300 episodes. **G3 per variant:** no NaN; `lam` below `lam_max` for ≥ 50% of episodes; mean episode cost trending down; validation CSO reduction better than random-gate policy. Variants failing G3 are debugged before scaling.

### T16 — Freeze the protocol  (Dep: T15)
Write `docs/protocol.md`: hypotheses (§8), splits (years), scenario parameters (`max_spread`, `k_hi`, `k_cap`, mults, ladder), ceiling, eligibility rule, θ hash, selection score, seeds, budgets, statistics. `git tag protocol-v1`. **After this tag, test splits may be evaluated; any change is reported as a deviation.**

### T17 — Full runs  (Dep: T16)
Tier 1 (must) and Tier 2 (should) of §7 with **5 seeds** (3 minimum), one process per seed. Then evaluate **best_val** checkpoints on TEST-R, TEST-L, TEST-X (and ANCHOR if available), deterministic.

### T18 — Diet study  (Dep: T17)
Train V8-Full under D1–D4 (D5 optional), 3–5 seeds each; evaluate on the **same** fixed test sets. This answers "does training on 1000-yr help?" empirically.

### T19 — Statistics and reporting  (Dep: T17, T18)
Use `multistorm/stats.py` (hierarchical bootstrap, paired Wilcoxon, Holm). Unit of analysis = **parent event** (children of one parent are **not** independent: average within parent first). Produce tables/figures in §9.

### T20 — Robustness (optional)  /  T21 — Predictive shield (stretch)
Observation noise (σ 2/5/10%), sensor dropout, stuck gate; hot-start look-ahead shield (k = 2–4) on test rungs only. Details in `docs/v8_guide.md` §6.

### T22 — Reproducibility  (Dep: all)
README with one-command reproduction, environment lock, `make` targets, Zenodo-ready archive, data and model cards.

---

## 7. Experiment matrix

| Tier | Runs | Seeds |
|------|------|-------|
| **1 must** | B0, B1, B2, B3, O1; V7 (physical), **V8-Full**, SAC-plain, SAC-Lag-only | 5 |
| **2 should** | V8 ablations (−topo, −store-first, −Lagrangian, −shield, −rain features, 10-D); DDPG | 5 (min 3) |
| **3 diet** | V8-Full × D1–D4 (D5 optional) | 3–5 |
| 4 optional | robustness, predictive shield, grouped year-fold CV | 3 |

Compute ≈ 3 h CPU per run; do the 1-seed pilot (T15) first.

---

## 8. Hypotheses (freeze in T16)

- **H1** V8-Full reduces CSO vs true native on **TEST-R** (observed) and TEST-L; macro reduction > 0 with CI excluding 0; flood non-regression ≥ 95% of events.
- **H2** V8-Full ≥ B3 on TEST-L (else rules explain the gain).
- **H3** V8-Full ≥ SAC-plain and SAC-Lag-only on CSO reduction and has fewer storage-first violations and fewer flood regressions.
- **H4** Each of topology-KB, store-first, Lagrangian, shield contributes on ≥ 1 primary metric.
- **H5** D2 ≥ D1 and D4 on held-out observed events; D3 does not improve on D2 (test of the 1000-yr training question).
- **H6** Gains concentrate in 5–25 yr; above 100 yr the agent matches the reference but cannot remove unavoidable flooding (report `ref`/`hind` flood as the floor).

---

## 9. Evaluation specification

**Test sets (fixed):** TEST-R (family R, split test) • TEST-L (families T ≤ 100 and C, split test) • TEST-X (rungs T200/T500/T1000, split test) • ANCHOR (Sep 2018, Aug 2019) if rainfall is obtained. Same sets for every method.

**Per-event columns (`final_eval.csv`):** `family, rung, k, T_anchor, parent, split`; CSO: `cso_vol_m3, cso_events, cso_hours, cso_peak_cfs, cso_reduction_pct (vs native), cso_delta, pct_achievable_captured, regret_vs_hindsight`; storage: `peak_store_util, suo_onset, fill_during_cso, store_first_viol_rate, rho_storage_first, sat_storage_first`; safety: `flood_total, flood_ratio, flood_nonregress, flood_zero_when_feasible, rho_flood_free, max_depth_ratio_peak`; behaviour: `capture_ratio, actuation_tv, gate_reversals, intervention_rate, intervention_mag`; validity: `routing_error_pct, runoff_error_pct`; `scorecard_pass`.

**Headline metrics:** macro and micro CSO reduction vs native per rung; `pct_achievable_captured` (share of the hindsight-achievable reduction); scorecard pass-rate; flood non-regression and zero-when-feasible rates; storage utilisation at overflow onset (target → 1.0); intervention rate.

**Statistics:** parent-event unit; hierarchical bootstrap CIs (events then seeds); paired Wilcoxon + rank-biserial; Holm across the pre-registered comparisons; ≥ 5 seeds.

**Figures/tables:** scenario overview (`T_eq` before/after, `k` histogram, onset table); CSO reduction by rung with CIs; achievable-captured by rung; storage fill at overflow onset vs reference; example hydrographs (native vs B3 vs V8-Full) for one 10-yr and one extreme event; λ/cost curves; learning curves with seed bands; diet-study comparison; flood non-regression by rung.

---

## 10. Pitfalls (known)

- Old cache or `tag` without `nativefix` ⇒ contaminated native reference.
- `native_mode` before P2 sets gates to 0.5 at start.
- "Storage fill" from `54/54_B` was rain-independent in the v7 cache; do not reuse v7 thresholds (0.85, 0.70, 9500, `cso/5000`, `flood/10000`).
- Children of one parent are correlated: average per parent before testing; never split children across train/test.
- `cost_limit = 0` makes λ diverge; use a small positive limit plus the shield.
- A time limit stored as terminal biases late-horizon values: store `terminated` only.
- `np.random` is used by `RingReplay.sample`; seed numpy/torch/random per run.
- Temp INP files from `write_physical_storm_inp` accumulate; clean per run.
- `implausible_shape` rejections: look at `rejected.csv` before changing `--max-spread`.

---

## 11. Definition of done

- [ ] G0–G3 passed (or stopped and reported with numbers).
- [ ] `tests/test_golden.py` passes with v7 defaults; all new tests pass (`pytest -q`).
- [ ] Scenario directory built; manifest + guard enforced; ≥ 3 parents per split per rung.
- [ ] True-native references, hindsight table, optimised-rule baseline (B3) computed.
- [ ] Protocol frozen and tagged before any test-set run.
- [ ] Tier 1/2 with ≥ 3 (target 5) seeds; diet study D1–D4 complete.
- [ ] Observed (R) and amplified (T/C/F/X) results reported separately; every amplified event labelled with `k` and `T_anchor`.
- [ ] Flood non-regression and zero-when-feasible reported per rung; extreme-rung unavoidable flooding stated.
- [ ] Novelty verification table completed (`docs/v8_guide.md` §4.6) before writing "novel".

---

## 12. Stop-and-ask list (blockers only the user can resolve)

1. Output of `diag_semantics` (G0) and `gate_topology.csv` confirmation.
2. NOAA Atlas 14 depth table (with confidence intervals) for any rung > 100 yr.
3. Validation/test years; compute budget (processes, hours).
4. `multistorm/physical_inp.py`, `adapters.py`, `storms.py`, `evaluate.py`, `train_multi.py` if signatures differ from what the patches assume.
5. Rainfall for the Sep-2018 / Aug-2019 anchor events or the utility gauge record, if obtainable.

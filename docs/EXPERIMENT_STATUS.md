# Experiment status vs guides

> **Training-readiness hardening, 2026-10-20:** 102 tests pass. Every official
> v8 variant now shares cumulative four-outfall m3 accounting, exclusive agent
> gate ownership, native pump interlocks, strict safety checkpoint selection,
> seed-invariant validation, exact replay/RNG resume, and train/test process
> separation. Tracked topology/geometry is bound to the canonical INP hash.
> Stale scenario/onset/Atlas manifests are rejected. These are software
> corrections, not performance results; the hydraulic gate remains failed and
> is machine-enforced. See `docs/training_readiness_20261020.md`.

> **Latest decision, 2026-10-20:** A repaired finite-sentinel logger proves timestep-dependent native target switching (600 changes at 0.5 s; 914 at 0.25 s). Coupled regulator endpoints reduce the finest network discrepancy to 73.056 m3 (1.861%); 200 trials reduce it to 57.118 m3 (1.422%), still above 1%. Fixed one-second rule cadence also fails (1.545%), and adding conduit endpoint terms worsens the result (3.202%). All candidates are rejected; no training. See `docs/coupled_endpoint_verification_20261020.md`.

> **Latest decision, 2026-10-20:** Integrated storage-volume correction passes 72/72 valid isolated hydraulic cases but fails both native TRAIN network refinements (1.762340%, 2.581679%; limit 1%). No engine adoption or training. Software: 90 passed and golden compatibility rechecked. See docs/integral_storage_verification_20261020.md.

> **Latest decision, 2026-10-19:** Exact read-only replays identify remaining failures around 1360_B and its endpoints. Increasing MAX_TRIALS to 200 reduces nonconverging steps to about 4.2% but still fails the finest refinement: 78.845283 m3 (2.073436%), limit 38.026394 m3. No engine adoption or downstream experiments. See docs/surface_failure_attribution_20261019.md.

> **Latest decision, 2026-10-19:** A verified upstream conduit-area branch discontinuity causes a repeating junction solver cycle. The continuous-allocation candidate passes six compiled boundary/control groups and 60/60 isolated tests, but fails both network refinements (2.06%, 1.62%). Candidate rejected; training and downstream experiments remain blocked. Software suite: 90 passed. See `docs/conduit_surface_transition_20261019.md`.

> **Stride localization, 2026-10-19:** Both read-only replays exactly reproduce all recorded final metrics. The 127.499 m³ finest-step difference is entirely at outfall 65; the largest interval contributions occur at 22.75–23 h (75.847 m³) and 31.5–31.75 h (45.836 m³). Hydraulic acceptance still fails; training remains blocked. See `docs/stride_localization_20261019.md`.

> **Latest verification, 2026-10-19:** Fixed one-second rule cadence still fails the finest comparison (3.43%). Requiring node continuity before conduit bypass passes 60/60 isolated checks but 0/2 network comparisons (1.35% and 3.20%). No production adoption or research training. Training/validation severity ceilings now check declared T rungs as well as fitted values, reject unknown research severity, and require a separate research validation set. Software tests: 90 passed. See `docs/balance_bypass_verification_20261019.md`.

> **Latest execution, 2026-10-17:** A bracketed storage/outfall-weir correction passes 60/60 isolated tests but only 1/2 network refinement comparisons. The 0.5→0.25 s CSO difference is 157.365 m³ (3.898%), so no production adoption or training. Official NOAA Atlas 14 tables for Detroit City Airport (42.4072, -83.0089), including 90% bounds, are now verified and selected for future scenario rebuilding under user authorization. Parent-event statistics tooling and model/data cards are prepared. Software suite: 87 passed. See `docs/bracket_verification_20261017.md` and `docs/reproduction_current.md`.

> **Coupled endpoint diagnostic, 2026-10-17:** All 36 synthetic cases meet independent discrete-trajectory checks, but only 18/36 have no unconverged steps. The simplified constant-area system does not reproduce the large network discrepancy. Next: actual tabular geometry, wetting/submergence and surrounding connections. Full-network refinement remains 0/2 and training remains blocked. See `docs/coupled_balance_verification_20261017.md`. Software tests: 83 passed.

> **Network failure attribution, 2026-10-17:** Read-only logging reproduces all prior recorded hydraulic metrics exactly. Of 1,036,800 steps, 268,943 remain unconverged; storage 35440 fails continuity on 267,882 of them (99.61%), while its head-change check always passes. Gate 1360_B has 164,558 final-flow failures. Counts overlap. See `docs/network_failure_attribution_20261017.md`. The next target is coupled junction/orifice/storage iteration; full-network refinement remains 0/2 and training remains blocked.

> **Isolated accounting resolved; network still fails, 2026-10-17:** A local continuity-equation stopping check yields 60/60 passing isolated cases and close agreement with an independent storage solution. The full-network TRAIN probe still fails both refinement comparisons: CSO 4411.62 → 4255.87 → 4064.98 m³, adjacent differences 3.66%/4.70%, flooding zero. See `docs/continuity_verification_20261017.md`; 80 tests pass. No production adoption or downstream training. This supersedes the earlier two-case isolated balance blocker with a remaining full-network convergence blocker.

> **Equation-level blocker established, 2026-10-17:** The failed storage transition lies in a mathematically proven no-root interval of the original cutoff/discrete continuity equations. An explicitly separate continuous-law experiment plus final-head check passes all 12 flow checks but fails two junction water-balance checks (10/12 overall). No production adoption, new references or training follows. See `docs/cutoff_formulation_analysis_20261017.md`.

> **Rejection/retry tested, 2026-10-17:** Exact restart/replay restores accepted state and accounting after rejection. The junction crossing reaches 62 s after five rejections; the storage crossing stops at 5.755859375 s after eight rejections. At the minimum step it declares convergence but fails the final-flow check by 3.177879 CFS. Its accepted prefix also fails the throughput-based balance check. See `docs/retry_verification_20261017.md`; 77 tests pass. Next: branch-consistent scalar residual analysis at the failed storage transition. No production adoption or resumed training.

> **Internal transition trace, 2026-10-17:** Four logging-only runs exactly reproduce all uninstrumented sampled states and totals. Baseline head convergence accepts a 118.73 CFS final-head flow residual; candidate cap exits retain unresolved flow residuals. Effective nodal area stays constant, qualifying the area-switch hypothesis. See `docs/transition_trace_20261017.md`. Next: isolated rejection/retry with state restoration and post-update flow checks; no production equation change or training restart.

> **Reversing-flow isolation, 2026-10-17:** Completed 24 matched synthetic runs with a fully open 1360_B-style orifice and changing tailwater. Both engines pass 6/6 inside-cutoff controls and fail 6/6 cutoff-crossing cases. Candidate junction flow reverses 2155 times across 2160 late samples at 0.25 s. The unchanged cutoff has a 3.177 CFS jump. See `docs/reversing_orifice_verification_20261017.md`; 73 tests pass. Next: iteration-level branch/surface-area tracing at a transition. No production solver adoption or resumed training.

> **Regulator verification, 2026-10-17:** The separate experimental solver passes 48/48 isolated weir/orifice cases but fails both full-network comparisons: CSO 4740.92 → 4357.98 → 4109.49 m³, zero flooding, adjacent differences 8.79%/6.05%. It is not adopted. Training remains blocked. See `docs/regulator_verification_20261017.md`. Next diagnostic: unsteady near-zero-head and reversing orifice flow, with unchanged acceptance thresholds.

> **Coupled update tested, 2026-10-16:** The storage/weir sensitivity update passes all 24 isolated cases, but fails both full-network refinement comparisons on the fixed TRAIN storm: CSO 4436.41 → 4199.97 → 4055.80 m³, flooding zero, adjacent changes 5.63%/3.55%. The new DLL runner exactly reproduces prior baseline results. The candidate is not adopted. See `docs/coupled_weir_verification_20261016.md`. Next targeted diagnosis: 1360_B orifice–junction–storage coupling; retain all existing numerical acceptance criteria.

> **Flow-aware check tested, 2026-10-16:** A separate experimental engine now checks weir-flow iteration residuals as well as head convergence. On 24 matched isolated cases, free-flow passes remain 12/12 and submerged passes improve from 4/12 to 8/12. All four 1-second submerged cases still fail, with worse oscillations; the candidate is not adopted. See `docs/flow_guard_verification_20261016.md`. Next: a robust coupled update or rejection/retry of unconverged timesteps, still on the isolated model before full-network validation.

> **Isolated verification completed, 2026-10-16:** 72 short synthetic cases reproduce submerged-weir instability without RL. The installed and independently built baseline engines produce identical result files: 12/12 free-flow cases pass, only 4/12 submerged cases pass. A separate stronger-damping build fails all 12 submerged cases despite improved volume balance. The earlier derivative hypothesis is qualified because ordinary storage updates do not use it. See `docs/isolated_weir_verification_20261016.md`. 66 tests pass; production hydraulics and RL training remain unchanged. Next: flow-residual-aware convergence or a robust coupled update, first verified on the isolated model.

> **7 Mile weir diagnosis, 2026-10-12:** Native-control routing traces localize 86.98 CFS step changes to submerged weir 35444 at nearly equal storage/outfall heads, with constant nearby control targets. A 100-trial, 1e-7 ft tolerance probe still fails both refinement checks (CSO 3986.44 → 3864.87 → 3645.96 m³; flooding zero). Global continuity improves but does not establish convergence. See `docs/weir_diagnostic_20261012.md`. 64 tests pass; no production hydraulic change or new training is authorized by these results. Next: isolated submerged-weir reproduction and verified solver comparison.

> **Routing trace and surcharge study, 2026-10-12:** Recorded 15.6 ft head jumps near 3529_A with constant gate targets. SLOT trials improve aspects of stability but fail the same convergence screen: 7/14 comparisons pass at default accuracy, 6/14 with tighter accuracy. Native CSO remains resolution-sensitive. See `docs/surcharge_diagnostic_20261011.md`; investigate the 7 Mile gate/storage interaction next. No production hydraulic formulation is adopted.

> **Fine-step validation, 2026-10-11:** Both 21-run TRAIN-only studies (default and tighter solver) fail numerical convergence: only 5/14 adjacent comparisons pass in each. Smaller routing steps and higher solver accuracy are not sufficient. See `docs/fine_hydraulic_validation_20261011.md`. No production resolution is adopted and training/onset rebuilding remains blocked.

> **Additional correction, 2026-10-11:** `docs/hydraulic_validation_20261011.md` documents native-rule interference with external commands, finite gate travel times, and reverse JCT inflow included in cumulative node inflow. The opt-in complete environment now separates native/external control and logs target/actual positions. Earlier controlled runs do not validate the intended commanded policy. v6 references and fresh hydraulic checks are required.

> **Audit correction, 2026-10-10:** The historical status below is superseded for thesis claims by `docs/thesis_audit_20261010.md`. User-confirmed CSO includes 54_B and 65_B as well as 54 and 65. Legacy performance excluded bypass discharge; no saved full-run validation checkpoint meets 95% flood non-regression. G1/G2/G3 and rule calibration must be re-established for the corrected objective. Fresh G0 diagnostic evidence is in `runs/complete_overflow_check_20261010/g0.json`. Existing TEST exposure must be disclosed. The historical numbers below are retained as provenance, not certified current results.

Checked against `AGENTS.md` (NS-SAFE-SAC v8). Date: 2026-10-09.

## Verdict

**v8 pipeline is built and gated through G0 + G1.** A 20-episode smoke train
(`runs/v8_smoke_s0`) completed with checkpoints and `final_eval.csv`. Full Tier 1/2
multi-seed runs, diet study, and protocol tag are **not** finished — they need your
confirmation on splits/topology and a multi-day compute budget.

## Gates

| Gate | Status | Evidence |
|------|--------|----------|
| G0 diagnostics | **PASS** | 4 storage units `35390/35391/35440/35442`; wet−dry Δdepth ≈27–34 ft; native@reset=INP 1.0; CFS |
| G1 onset | **PASS** | n=416, median `k_onset`=**3.72**, no-onset=**0%** (`runs/onset_table.csv`) |
| G2 controllability | **PASS** | n=210 stratified; all rung medians ≥10% (C3 lowest at 17.4%); `uncontrollable_rungs=[]` |
| G3 pilot | **PASS (smoke)** | `v8_pilot_s0` 300 eps done; λ 0.48→0.22; val CSO red ~10%; `best_val.pt` |
| Protocol | **FROZEN** | `docs/protocol.md` (git tag deferred — no repo yet) |
| Tier 1 | **V8-Full s0 done** | test vs native macro **+33.7%** (n=410); vs static ≈ −1.4% (agent ≈ static). λ hit lam_max. |

## Topology — please confirm

`runs/gate_topology.csv`: **no** gate feeds monitored CSO weirs without storage.
Gates 3/4 (`35281_B`, `35291_B`) do not reach weirs `35391`/`35444` (they drain to outfalls).

## Scenario catalog

`data/useful/rain_scenarios/` built with val=2021–2022, test=2023–2026, Atlas through 1000 yr.
Every split×rung used in experiments has ≥3 parents. `max_spread=10` recorded in `docs/protocol.md`.

## Tests

`pytest -q` → **47 passed**.

## What remains (T17–T22)

1. Your OK on topology + year splits (or alternate years).
2. Full controllability on train+val (expensive; parallelise).
3. θ calibration → `runs/theta.json`.
4. Tier 1/2 training (3–5 seeds × variants) then diet D1–D4.
5. Tag `protocol-v1` **before** any official test-set evaluation.
6. Stats/tables/figures + reproducibility pack.

## Smoke artifacts

- `runs/v8_smoke_s0/{train_log,eval_log,final_eval}.csv`, `checkpoints/best_val.pt`
- `runs/onset_table.csv`, `data/useful/rain_scenarios/`, `atlas14_mm.csv`

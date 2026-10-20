# System architecture & end-to-end flow

Neurosymbolic SAC controls gates on the Detroit 7 Mile / Hubbell–Southfield CSO
network (`7MPF_CSO_08.inp`) under multi-event rainfall. This document is the
architectural map: layers, pipeline steps, units, lengths, and frozen parameters.

Related: `docs/protocol.md` (hypotheses / QC), `docs/DATA.md` (units),
`docs/EXPERIMENT_STATUS.md` (current results), `data/README.md` (file layout).

---

## 1. Layered architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│  research/          data acquisition → events → QC → screen     │
│  configs/data.json  gauges, IETD, PFDS, QC thresholds           │
├─────────────────────────────────────────────────────────────────┤
│  multistorm/        multi-storm train / eval / baselines / report│
│    storms.py        load · scale · split · sample               │
│    physical_inp.py  TIMESERIES rain injection (physical units)  │
│    baselines.py     per-storm static / native refs + cache      │
│    adapters.py      thin bridge → app.py (only SWMM import site)│
│    train_multi.py   episode loop · val selection · final eval   │
├─────────────────────────────────────────────────────────────────┤
│  app.py (frozen)    NeurosymbolicSWMMEnv · SymbolicKB · SAC     │
│  7MPF_CSO_08.inp    SWMM network (CFS, Design_RG)               │
└─────────────────────────────────────────────────────────────────┘
         ▲                         │
         │                         ▼
   data/{raw,useful,unused}/    runs/<run_name>/
```

| Layer | Responsibility | Must not change for paper runs |
|-------|----------------|--------------------------------|
| `app.py` | Env, KB predicates/rules, reward, SAC nets/hparams | SAC, KB, reward weights, action/obs layout, INP |
| `multistorm/` | Storm IO, sampling, baselines, selection, reporting | May change data plumbing only |
| `research/` | NCEI → events → screen → diagnose | Event rules frozen in protocol |

---

## 2. End-to-end flow (begin → end)

### Stage A — Acquire & standardize (Stage 10)

1. `research.acquire_ncei` downloads NCEI HPD **15-min** series for gauges in
   `configs/data.json`.
2. Writes `data/raw/<station>_15min_standardized.csv`
   (`time_utc`, `precip_mm`) and `data/raw/raw_manifest.json` (URL, SHA, conversion).
3. Coverage reports flag years with poor validity.

**Units here:** source hundredths of an inch → **mm depth per 15-min bin**.  
**Timezone:** fixed EST offset **UTC−5** (no DST) so diurnal DWF alignment stays stable.

### Stage B — Event catalog (Stage 11)

1. `research.build_real_storms` detects events and cuts **72 h** windows.
2. Outputs under `data/useful/rain_real/` (primary) and `rain_real_secondary/`:
   one CSV hyetograph per event + `events.csv` + `data_manifest.json`.
3. Severity via NOAA Atlas 14 ARI (`configs/pfds_detroit_mm.csv`), not depth bins.

| Parameter | Value | Meaning |
|-----------|-------|---------|
| Control / rain interval | **15 min** = **900 s** | Env step & hyetograph bin |
| Episode / window length | **288 steps** = **72 h** | Pad/truncate to this |
| IETD | **6 h** | Inter-event dry time |
| Catalog min depth | **6.35 mm** (0.25 in) | Event significance |
| Tail margin | **6 h** | Event must end ≥6 h before window end |
| Window start | Local midnight of event day | Aligns with DWF pattern |

### Stage C — QC subset

`rain_real` → `rain_real_full` keep rules:

| Rule | Value | Why |
|------|-------|-----|
| `year ≥ 2010` | drop pre-2010 | HPD 0.1-inch quantization |
| `total_mm ≥ 12` | drop tiny events | Intensity structure for screening |
| Count (freeze) | **416** events | Working catalog |

### Stage D — Units & physical injection (Stage 12)

SWMM model: `FLOW_UNITS = CFS` → US customary. Gage `Design_RG` is **INTENSITY**.

| Quantity | Unit | Notes |
|----------|------|-------|
| Stored hyetograph | **mm / 15-min** depth | One float per step, length 288 |
| Gage write (physical) | **in/hr** | `rain_to_gage = mm_per_15min / 6.35` |
| Conversion identity | `(mm/25.4) / 0.25` | depth→inches, then ÷0.25 h |
| Flow / flood / CSO | SWMM project (CFS volume aggregates) | CSO volume reported in **m³** in screens |
| Storage fill | depth sum on nodes `54`, `54_B` | Capacity from INP geometry |

**Injection (research path, `--physical-rain`):**

1. On each `reset`, write `runs/_physical_active.inp`.
2. Set `Design_RG INTENSITY 0:15` + TIMESERIES `STORM15` (288× in/hr + dry pad).
3. No per-step API `total_precip` writes (avoids sparse under-application).
4. Baseline cache tag: **`v3-phys-timeseries`**.

**Legacy Trial 7** (`physical_rain=False`): peak-scaled `raindata.csv`, mm-as-gage
value — kept only for golden regression; **not** for reported research numbers.

### Stage E — Diagnostic gate

`research.diagnose_rain` on an extreme event: `.rpt` precip must match expected
depth (ratio ≈ 1.0). Finding: unscaled real k=1 → **static CSO = 0**; CSO appears
at **k≈2**. Storage `fill_max` ≈ **30.86** invariant under static gates (rain-insensitive).

### Stage F — Labelled ×2 stress catalog (active path)

Because unscaled storms do not produce CSO under physical units:

1. `build_scaled_storms` → `rain_real_full_x2` (hyetograph × **2**, shape preserved).
2. Manifest: `provenance=observed_scaled`, `role=secondary_stress_test`,
   `scaling=uniform_x2`.
3. **Not** a “100% real rainfall” claim; report separately.

### Stage G — Stormy screen (static baseline only)

`research.screen_events` runs **static** policy (gates 0.5, pumps ON) per event.
Never uses the agent.

| Rule (frozen) | Result |
|---------------|--------|
| Keep if static CSO ≥ **1000 m³** | **49 / 416** kept |
| Rejected | 367 (max rejected nonzero CSO ≈ 829 m³) |
| Output | `data/useful/rain_real_stormy_x2/` + `screening.csv` |

### Stage H — Temporal split

`data/useful/splits/splits_stormy_x2.json` (year blocks):

| Split | Years | N |
|-------|-------|---|
| Train | ≤ 2020 | **30** |
| Val | 2021–2022 | **7** |
| Test | 2023–2026 | **12** |
| **Total** | | **49** |

Test is never used for selection or hparams.

### Stage I — Train (M0 neurosymbolic SAC)

```bash
PYTHONPATH=. .venv/bin/python -m multistorm.train_multi \
  --rain-dir data/useful/rain_real_stormy_x2 \
  --split-manifest data/useful/splits/splits_stormy_x2.json \
  --physical-rain --scaling none --seed <N> --run-name m0_x2_s<N>
```

Per episode:

1. Sampler (`shuffled_cycle`) picks next train storm.
2. Load/cache **static** & **native** baselines for that storm (`BaselineStore`).
3. `env.reset` with storm depths → physical INP write → SWMM sim.
4. For each of **288** steps: SAC action → KB **project** → apply gates/pumps →
   reward → replay.
5. Warm-up: random actions for first **2000** env steps; then SAC update every **4** steps.
6. Every **25** episodes: deterministic eval on val; select on macro CSO reduction %
   with safety caps.

### Stage J — Evaluate & report

- Final deterministic eval on train / val / test → `final_eval.csv`, `final_agg.json`.
- Checkpoints: `best_val.pt`, periodic, `final.pt`.
- Primary metric: **% CSO volume reduction vs static baseline** (macro over events).
- Safety: `r6_excess ≤ 0.01`, `flood_ratio ≤ 1.05`.

---

## 3. Control / RL architecture (inside `app.py`)

### Action (10-D, all in [0, 1])

| Idx | Actuator | Role |
|-----|----------|------|
| 0–6 | Gates `1360`, `1360_B`, `35263`, `35281_B`, `35291_B`, `3530`, `3530_B` | Learnable |
| 7–9 | `PUMP27/28/29` | **Frozen = 1.0** (always ON) |

R1/R2 projection applies only to idxs **[0,1,2,5,6]**. R6 (flood > 9500) forces
those gates open. `35281_B` / `35291_B` learn without R1/R2.

### Observation

Raw SWMM node depths / inflows / heads + current rain + **11 symbolic predicates**
(storage critical/warn, manhole critical/warn, CSO active, flooding severe, fill &
depth ratios, normalized CSO/flood). Actor/critic use **LayerNorm** on input.

### Reward (3 terms, scale **S = 1000**)

| Term | Weight | Form |
|------|--------|------|
| `r_close` | **W = 10** | Reward closed R1/R2 gates when fill &lt; 70% and safe |
| `r_cso` | **W = 3** | −CSO flow / S (primary learning signal; links W35391+W35444) |
| `r_flood` | **W = 5** | −max(flood − **per-storm** baseline, 0) / S |

KB thresholds: storage open **0.85**, warn **0.70**; manhole critical **0.90**,
warn **0.75**; R6 flood **9500** (legacy 132% × Trial-7 baseline 7183).

### Storage (hydraulic)

| Item | Detail |
|------|--------|
| Storage nodes | `54`, `54_B` |
| Wetwells (pump depth) | `JCT-2114`, `JCT-3090`, `65`, `65_B` |
| Fill under static | ≈ **30.86** independent of rain scale (driven largely by baked-in `[INFLOWS]`) |
| Capacity | From INP full depths / geometry via `load_geometry()` |

### SAC (frozen)

| Hyperparameter | Value |
|----------------|-------|
| Network | MLP **256**, LayerNorm, ReLU |
| `lr` | **1e-4** |
| `γ` | **0.99** |
| `τ` | **0.005** |
| Batch | **256** |
| Replay | **50 000** (~175 episodes) |
| Target entropy | **−7.0** (7 learnable gates) |
| Grad clip | **0.5** |
| Update every | **4** steps |
| Warm-up | **2000** random steps |
| Episodes | **1000** |
| Eval policy | Deterministic (mean action) |
| Seeds (paper) | **≥ 5** |

---

## 4. Data lengths & catalogs (at a glance)

| Dataset | Location | Length / count | Role |
|---------|----------|----------------|------|
| Raw series | `data/raw/*_15min_standardized.csv` | Full multi-year 15-min | Source |
| Event hyetograph | one CSV / event | **288 × mm/15min** | Train input |
| `rain_real_full` | `data/useful/` | **416** | QC catalog |
| `rain_real_full_x2` | `data/useful/` | **416** (×2 depths) | Stress catalog |
| `rain_real_stormy_x2` | `data/useful/` | **49** | Active train set |
| Split manifest | `data/useful/splits/` | 30 / 7 / 12 | Frozen split |
| Trial 7 rain | `data/unused/rain/` | 288 (peak→24) | Golden only |

**Episode wall-clock physics:** 288 × 15 min = **72 hours** simulated per episode.  
**One full train seed:** 1000 episodes × ~72 h sim (CPU-bound SWMM; GPU mostly idle).

---

## 5. Baselines, cache, outputs

| Reference | Policy | Use |
|-----------|--------|-----|
| **Static (B0)** | Gates 0.5, pumps ON | Primary compare; stormy screen |
| **Native** | SWMM `[CONTROLS]` | Secondary reference |
| Cache key | `tag ‖ inp_sha ‖ storm_sha` | Tag = `v3-phys-timeseries` |
| Cache file | `runs/baseline_cache*.json` | Shared across seeds |

Per run directory `runs/<run_name>/`:

```text
run_config.json · storm_manifest.json
train_log.csv · eval_log.csv
final_eval.csv · final_agg.json
checkpoints/{best_val.pt, …}
```

---

## 6. Model selection rule

On validation (deterministic):

\[
\text{score} = \text{macro CSO reduction \%}
\quad\text{if}\quad
r6\_excess \le 0.01 \;\wedge\; flood\_ratio \le 1.05
\]

Otherwise demote (do not save as `best_val`).  
`cso_floor = 1.0` m³: events below floor are unscored for relative CSO %.

---

## 7. What is frozen vs what moves

| Frozen | Configurable / data-path |
|--------|---------------------------|
| SAC hparams, nets, buffer | `--rain-dir`, `--split-manifest` |
| KB rules R1/R2/R6, predicates | `--physical-rain`, `--scaling none` |
| Reward weights & layout | Stormy threshold (frozen at 1000 m³) |
| INP network topology | Gauge IDs / year QC in `configs/data.json` |
| 15-min step, 288 episode | Seeds, run name, variant (`m0`/`m1`/ablations) |

---

## 8. Active experiment status (one line)

**M0 ×2 stormy (5 seeds):** val CSO red. **+8.4 ± 3.3%**; test **+0.5 ± 7.6%** —
labelled stress test only; primary unscaled real-rain claim still blocked (no CSO at k=1).
See `docs/EXPERIMENT_STATUS.md`.

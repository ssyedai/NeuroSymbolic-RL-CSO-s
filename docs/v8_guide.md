# Neurosymbolic Safe SAC for CSO Control — v8 Implementation Guide
**Basis:** your `app.py` (v7), the Stage 0–19 pipeline already built, the analyses of your event catalog and baseline cache, and the Detroit PFSMC literature (Yin et al. 2023, 2024).
**Goal of the study:** minimise CSO, **use available storage before overflowing**, and **add no flooding**, with a neurosymbolic SAC agent, evaluated on real Detroit rainfall.

> **Honesty notes.**
> 1. Items marked **[VERIFY]** are things I inferred from your code/data or from API knowledge, not things I confirmed by running your INP. Stage 0 turns each into a yes/no test.
> 2. Safe RL in urban drainage already exists (safe & trustworthy RL for flooding; Safe DRQN for flood and CSO control; MARL+MPC). Your novelty has to come from the *combination* in Section 4 and the *evaluation rigor*, and you must verify it with a literature check (Section 4.6) before claiming "first".
> 3. "No flood" cannot be a universal guarantee: for sufficiently extreme storms flooding is physically unavoidable. The defensible goal is **flood non-regression** (never worse than the reference, zero flood whenever the reference or hindsight optimum achieves zero). Section 4.5 explains.

---

## 1. Answers to your two direct questions

### 1.1 "Should I train on 1,000-year return-period rainfall?"
**No, not as the training diet. Use it as an out-of-distribution stress test, if at all.** Reasons, with numbers from your catalog and the Detroit IDF used in the PFSMC papers:

| Fact | Number | Consequence |
|------|--------|-------------|
| IDF-extrapolated 1000-yr depths | 1 h: 112 mm; 6 h: 170 mm; 24 h: 217 mm (5-yr 24 h: 72 mm, 25-yr: 101 mm) | Replace with NOAA Atlas 14 values and their confidence intervals before using any rung above 100 yr; the fitted curve is extrapolated |
| Your SWMM calibration window (Sep 2016 to Jun 2017) | max 24-h depth 58 mm, max 1-h depth 16.5 mm (about a 1.8-yr storm) | The hydraulics were validated far below 100 yr; 1000-yr results are pure model extrapolation |
| Published behavior on this network | CSO under native control from about 5-yr design storms; RL eliminated CSO only up to roughly 15–20 yr | The **controllable** regime is about 5 to 25 yr. At 1000 yr the system saturates, flooding dominates, and gates barely matter |
| Your Trial 7 storm | If the gauge is INTENSITY in in/h (as your own `rain_to_gage_value` docstring states), the legacy path wrote mm as in/h, so the effective storm was about **723 mm** with a **152 mm/h** peak | Trial 7 was already beyond a 1000-yr storm; it never measured realistic control value |

Training on 1000-yr events would teach the policy flood avoidance and rule overrides (R6) rather than CSO optimisation, would make `flood = 0` unattainable (so the Lagrange multiplier explodes), and would let a few huge returns dominate the critic.

**What to do instead:** a **severity ladder** (5, 10, 25, 50, 100 yr) for training and validation; 200/500/1000 yr only as **test-only stress rungs** to show the degradation curve.

### 1.2 "Is amplifying real rain by 2× OK?"
It is acceptable only as a **labelled scaled-historical** event, and a flat 2× is a poor design. From your 565 events since 2010 (return periods from durations ≥ 1 h):

| Class (T_eq) | Unscaled | After flat ×2 |
|--------------|---------:|--------------:|
| < 1 yr | 525 | 386 |
| 1–2 | 11 | 47 |
| 2–5 | 13 | 38 |
| 5–10 | 6 | 22 |
| 10–25 | 8 | 32 |
| 25–100 | 2 | 18 |
| 100–1000 | 0 | 21 |
| ≥ 1000 | 0 | 1 |

- **68% of events are still below a 1-year storm** after ×2 (likely no CSO, no signal).
- **22 events jump past 100 yr** (short-duration spikes doubled).
- The factor needed to bring a typical event (6-h depth ≥ 15 mm, n = 197) to a target return period is **median 2.5× (5 yr), 2.9× (10 yr), 3.5× (25 yr), 4.0× (50 yr), 4.6× (100 yr)**. Only 29% of events reach a 5-yr 6-h depth with ×2.

So flat ×2 gives a bimodal, uncontrolled severity mix. Use **return-period-anchored scaling** (Section 3): each real event is scaled by its own factor so a chosen duration (6 h) hits the target return period, with a cap on the factor and a check that the other durations stay plausible. This preserves real temporal structure, gives controlled severity, and is directly comparable with the published 5 to 25-yr design-storm results. Keep flat ×2 only as one diet in the ablation study.

---

## 2. Code audit of `app.py` (v7)

Severity: **C** critical (invalidates results), **H** high, **M** medium, **L** low. "Config change" means it alters the Trial 7 model; make it an opt-in flag that defaults to v7 behaviour so `tests/test_golden.py` still passes.

| ID | Sev | Where | Finding | Fix | Config change |
|----|-----|-------|---------|-----|---------------|
| A1 | **C** | `STORAGE_NODE_IDS=["54","54_B"]`, `build_obs_dict`, predicates 0/1/6, R1, `r_close`, `STORAGE_CAPACITY=35` | Your cache shows `fill_min/max`, `r1_frac`, `close_frac` **identical across all 66 storms** (including 848 mm and zero-rain-like events). So "storage fill" is **independent of rainfall**. Either nodes 54/54_B are outfalls (tailwater boundary; Yin 2023 describes outfalls 54 and 65 as river outfalls **[VERIFY]**) or storages fed only by fixed `[INFLOWS]`. Either way R1 fires at the **same time steps in every storm** (12.9% of steps = 37/287), i.e. a **clock signal**, and `r_close` is a rain-independent bias toward closed gates | Stage 0 node-type and dry-vs-wet test; then define storage state from **actual storage units** (`is_storage()`) | yes (KB v8) |
| A2 | **C** | `_init_sim → _apply_defaults()`; `reset(options native)` | **Native mode is not native**: `_apply_defaults()` runs in every `_init_sim`, including native runs, so gates start at 0.5 instead of the INP's own settings. Your "B1 native" reference is contaminated | Skip `_apply_defaults()` when `native_mode`; read initial settings from the INP | no (bug fix) |
| A3 | H | `evaluate_predicates`, `project_action`, `shape_reward`: `max_dr` over `known_drs` | `NODE_FULL_DEPTHS` includes outfalls/storage ("54": 17.5, "65": 5.0 ...). `max_dr` ("manhole" depth ratio) is therefore dominated by those nodes, not by manholes. Predicate 3 (warning ≥ 0.75) is probably always on; R2 may trigger on non-manholes **[VERIFY]** | Restrict to `is_junction()` nodes | yes (KB v8) |
| A4 | H | `shape_reward` r_flood | `max(flood_t − baseline_mean, 0)`: instantaneous flood vs the **episode mean**. Not "≈ 0 at baseline" as the docstring claims; for peaky floods roughly half the baseline steps are penalised; effective safety level differs per storm | Absolute flood cost (Section 4) | yes |
| A5 | H | `r_close` | Rain-independent (see A1); in zero-CSO periods it is the only active term, so the agent learns "close gates" | Drop; replace by storage-first term | yes |
| A6 | H | rewards are raw cfs sums | Big storms dominate returns/critic; returns not comparable across storms | **Reference-normalised reward**: `r = −w·cso_t / CSO_ref(storm)` so return ≈ −(CSO_agent/CSO_ref) | yes |
| A7 | H | `Actor/Critic` input `LayerNorm`; predicate constants (`cso/5000`, `flood/10000`, `flood>9500`) | LayerNorm over the feature axis with un-normalised heterogeneous inputs (heads, flows in the hundreds, predicates in [0,1]) lets large features dominate. The constants were tuned in the inflated regime (6.35× rain); at physical rain they are about 0 or never fire | Running mean/std normalisation; depth-ratio and capacity-relative predicates | yes (obs v8) |
| A8 | M | Actor outputs 10 dims, env overrides 3 | The 3 pump dims have no effect on reward but enter log-prob/entropy and the critic input | **7-D policy**, env appends pumps = 1 | yes |
| A9 | M | `step` returns `done` as terminated; `train` stores `done=1` at the horizon | Time limit treated as terminal; time is not in the observation, so values near the end are inconsistent | `truncated=True`, store `terminated` only | yes (small) |
| A10 | M | `train`: `update_every=4`, one gradient step | UTD = 0.25; low sample efficiency. `ReplayBuffer.sample` uses `random.sample(deque)` which is O(n) | Configurable UTD; numpy ring buffer | hyper-param |
| A11 | M | `physical_rain=False` default, two rain paths | Easy to run research with the legacy (inflated) path by accident; `step()` does nothing for rain in physical mode (relies on `write_physical_storm_inp`, not shown) | `real_only ⇒ physical_rain=True` enforced; review `physical_inp.py` | no |
| A12 | M | depth labels "m", `STORAGE_CAPACITY=35 # m` | A CFS INP implies **feet**; `NODE_FULL_DEPTHS` overrides (17.07, 4.0, ...) were set from the inflated regime ("storm equilibrium ~15m") | Read units from `[OPTIONS]`; derive capacities from the INP | yes |
| A13 | M | `gate topology ambiguous` for a[3], a[4] | Comment says topology unknown; it can be extracted from the INP graph | `research/topology.py` | yes |
| A14 | L | `train()` selects `best_model.pt` on training score | Superseded by multistorm validation selection | keep legacy only for regression | no |
| A15 | L | `run_baseline_episode` | Returns mean flooding only; re-creates `Nodes(sim)` each step | Already handled by `BaselineStore`; do not use directly in research | no |

**What the audit means for your results so far:** your ladder of earlier findings (zero CSO on every real storm, identical storage statistics) is consistent with A1/A11. Do not train anything further until Stage 0 passes.

---

## 3. Data design (answers 1.1/1.2 concretely)

### 3.1 Four scenario families (all labelled in the manifest)

| Family | provenance | Built how | Used for |
|--------|------------|-----------|----------|
| **R** real unscaled | `observed` | catalog events (2010+, QC, spike-checked, T_eq ≥ about 2 yr, or reference CSO > 0) | **Primary test** (held-out years) |
| **L** ladder | `scaled_real` | RP-anchored scaling of real events to 5, 10, 25, 50, 100 yr | Train, validation, ladder test |
| **X** extreme | `scaled_real` | same, 200/500/1000 yr (Atlas 14 depths with CI) | **Test only** (stress, degradation curve) |
| **A** anchor | `observed` | Sep 12 2018 and Aug 7 2019 (published PFSMC test events) if you can obtain the rainfall | Credibility check against published CSO magnitudes |

Rules: scaled variants of one parent event always stay in the same split; the primary claims use **R** and **A**; **L/X** carry the "controlled severity" analysis; synthetic design storms are **not** used (optional diet D5 only, clearly labelled).

### 3.2 Code: `research/scenarios.py`

```python
# research/scenarios.py
import numpy as np, pandas as pd
from research.idf import idf_depth_mm, t_eq

def roll_max(x, steps):
    return float(pd.Series(np.asarray(x, float)).rolling(steps).sum().max())

def target_depth(T, anchor_min, pfds=None):
    """Use NOAA Atlas 14 table (index=minutes, columns=ARI yr, mm) when provided; else the Detroit IDF fit (<= ~100 yr)."""
    if pfds is not None and T in pfds.columns:
        return float(pfds.loc[anchor_min, T])
    if T > 100:
        raise ValueError("Provide an Atlas 14 table (pfds) for T > 100 yr; the IDF fit is extrapolated")
    return float(idf_depth_mm(T, anchor_min))

def shape_ok(depth15, max_spread=10.0):
    """After scaling, T_eq at 1 h / 6 h / 24 h must stay within a factor `max_spread` of each other."""
    Ts = [float(t_eq(roll_max(depth15, D // 15), D)) for D in (60, 360, 1440)]
    return max(Ts) / max(min(Ts), 1e-9) <= max_spread, Ts

def build_scaled(events, ladder=(5, 10, 25, 50, 100), anchor_min=360,
                 k_lo=0.67, k_hi=4.0, min_anchor_mm=15.0, pfds=None):
    """events: list of dict(storm_id, depth[288] mm per 15 min). Returns list of scaled variants (dict)."""
    out = []
    for ev in events:
        d = np.asarray(ev["depth"], float)
        base = roll_max(d, anchor_min // 15)
        if base < min_anchor_mm:
            continue
        for T in ladder:
            k = target_depth(T, anchor_min, pfds) / base
            if not (k_lo <= k <= k_hi):
                continue
            ok, Ts = shape_ok(d * k)
            if ok:
                out.append(dict(parent=ev["storm_id"], T_target=T, k=float(k), anchor_min=anchor_min,
                                depth=d * k, T_by_dur=Ts))
    return out
```
Write each variant as `rain_scaled/<parent>__T<T>.csv` (intensity mm/h = depth × 4) with manifest fields `provenance: "scaled_real"`, `parent`, `T_target`, `k`, `anchor_min`, `T_by_dur`, `file_sha256`. Variants inherit the parent's split.

### 3.3 Guard update (`research/guard.py`)
`assert_provenance(storms, train_ok={"observed","scaled_real"}, primary_test_ok={"observed"})`: refuse any storm whose manifest provenance is outside the allowed set for its role; require `scaling == "none"` for all; forbid on-the-fly augmentation; verify SHA-256s.

---

## 4. The proposed method: **Topology-grounded Neurosymbolic Safe SAC with a Storage-First Specification** (working name: *NS-SAFE-SAC*)

### 4.1 Idea in one paragraph
Keep SAC as the learner, but (i) derive the symbolic knowledge base **automatically from the SWMM network graph** (what each gate feeds, which storage can absorb it, which weir spills) instead of hand-written node lists; (ii) state the operating goal as a **temporal-logic specification**, *"overflow only when storage is full"* and *"never flood"*; (iii) enforce the hard part with a **topology-aware shield** at execution time and the soft part with **reference-normalised reward + a Lagrangian cost** at training time; (iv) **calibrate the shield's rule parameters on data** (hindsight-optimal and optimised-rule baselines) instead of hand-set 0.85/0.9/9500; (v) evaluate on a controlled **severity ladder** with statistics and a **hindsight-regret** metric.

### 4.2 Components

| # | Component | What it is | Why it should help | Ablation |
|---|-----------|-----------|--------------------|----------|
| N1 | **Topology-derived KB** | Graph from INP; for each gate: downstream storage set, downstream weir set, upstream risk-node set; predicates and rules are generated from these sets | Removes the "a[3]/a[4] topology ambiguous" gap, fixes A1/A3, transfers to other networks | `−topo` (v7 rules) |
| N2 | **Storage-first specification** (STL-style) | φ_store: `G( cso_t > ε → fill_t ≥ 1−δ )`; φ_safe: `G( flood_t = 0 )`; objective: min Σ cso | Encodes exactly your goal "reduce CSO while maximising storage" as a measurable property; quantitative robustness gives a dense signal | `−store-first` |
| N3 | **Constrained SAC (Lagrangian)** | Cost critic + dual variable λ for the flood/depth-margin cost, limit near 0 | Standard safe-RL machinery (CMDP); gives safety in expectation during learning | `−Lagrangian` |
| N4 | **Topology-aware shield** | Hard rules at execution (parameterised thresholds θ); action replaced when a rule fires | State-wise safety on the known failure modes; logs intervention rate | `−shield` |
| N5 | **Data-calibrated rule parameters** | CMA-ES on train events over θ and default gate settings → "optimised rule controller" (also a baseline, B3) | Honest strong non-learned baseline; shows what RL adds beyond tuned rules | compare B3 vs full |
| N6 | **Reference-normalised reward + 7-D policy + truncation fix + obs v8** | Fixes A6, A7, A8, A9 | Makes storms comparable and learning stable | `−refnorm`, `−obs8` |
| N7 | **Predictive shield** *(stretch)* | k-step look-ahead with SWMM hot-start (or a learned surrogate) before executing the policy action | Closer to certified safety; expensive | optional |

### 4.3 KB v8 rule skeleton (generated from the graph, not hand-coded node lists)
For each controlled gate `g`: `U(g)` = upstream junctions, `S(g)` = storage units reachable downstream, `W(g)` = CSO weirs reachable downstream, `P(g)` = pump wet-wells downstream.

| Rule | Condition | Action | Intent |
|------|-----------|--------|--------|
| F1 flood guard | `max_dr(U(g)) ≥ θ_f` | `a_g ≥ θ_f_open` | relieve upstream surcharge (v7 R2, now per gate and junctions only) |
| F2 emergency | `flood_t > θ_E` (relative to junction capacity, not 9500 absolute) | `a_g = 1` for gates with `S(g)` headroom, otherwise `a_g ≥ θ_f_open` | drain without pushing a full system to overflow |
| S1 store first | `S(g)≠∅ and fill(S(g)) < 1−δ and cso_t = 0` | `a_g ≥ θ_s` (admit flow to storage) | use storage before spilling |
| S2 protect weir | `W(g)≠∅ and fill(S(g)) ≥ 1−δ and flood guard inactive` | no forced opening; learner chooses | avoid feeding the spill when storage is full |
| P1 pumps | always | pumps = 1 | unchanged from v7 |

Parameters θ = (θ_f, θ_f_open, θ_E, θ_s, δ) are **calibrated** (N5), not hand-set.

### 4.4 Reward and cost (per step)
```text
r_t = − w_cso · cso_t / max(CSO_ref(storm), floor)           # return ≈ −CSO_agent/CSO_ref
      − w_store · 1[cso_t > ε] · max(0, 1−δ − fill_t) / T     # overflow while storage has headroom
c_t =   flood_volume_t / V_scale  +  0.1 · Σ_i max(depth_i − (Dmax_i − margin), 0)/Dmax_i
```
`margin` = 2 ft (as in Yin 2023, in INP units). `w_cso` about 10, `w_store` about 2 as starting values (tune on validation only). The old `r_close` and baseline-hinge `r_flood` are removed in v8; v7 stays available for ablation.

### 4.5 What "no flood" can honestly mean
- **Primary claim:** per event, `flood_agent ≤ flood_ref·(1+tol) + abs_tol` (**non-regression**), where `ref` is true native control.
- **Zero-flood claim:** if `ref` *and* the hindsight optimum have zero flooding, the agent must also have zero.
- Report the fraction of events satisfying each, per severity rung. At extreme rungs the reference floods; say so.
- Be explicit that the shield+Lagrangian give **empirical** safety on the tested events, not a formal proof (unless you build N7 with a validated model and state its assumptions).

### 4.6 Novelty verification protocol (do before writing "novel")
1. Search (Google Scholar, Scopus, Web of Science, arXiv) for combinations: *combined sewer overflow* AND (*reinforcement learning* OR *RTC*) AND (*shield* OR *safe RL* OR *constrained* OR *Lagrangian* OR *temporal logic* OR *neurosymbolic* OR *knowledge*).
2. Record each close paper in a table: control objective, safety mechanism, rainfall data, split, baselines, metrics.
3. Phrase the contribution as the **gap** the table shows (for example: topology-derived knowledge + storage-first specification + event-ladder benchmark with non-regression metrics), not as "first neurosymbolic RL for CSO" unless the search supports it.
4. Re-run the search just before submission.

Related lines to cite and position against (verify each): Lagrangian/CMDP safe RL and PID-Lagrangian updates, constrained policy optimisation, control-barrier-function shielding, safe & trustworthy RL for urban flooding (J. Hydrology 2023), Safe DRQN for flood and CSO (2026), MARL+MPC for CSO and flooding.

---

## 5. Stage 0 — diagnostics (run first; all are quick)

### 5.1 `research/diag_semantics.py`
```python
# research/diag_semantics.py
import re, numpy as np, pandas as pd
from pyswmm import Simulation, Nodes, Links
from multistorm import adapters as A
from multistorm.storms import load_storms, Storm

INP = "7MPF_CSO_08.inp"
WATCH = ["54", "54_B", "65", "65_B", "JCT-2114", "JCT-3090"]
GATES = ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B"]

# 1) what ARE these nodes/links?  (pyswmm: Node.is_outfall/is_storage/is_junction, Link.connections [VERIFY API])
with Simulation(INP) as sim:
    nd = pd.DataFrame([dict(id=n.nodeid, outfall=n.is_outfall(), storage=n.is_storage(),
                            junction=n.is_junction(), full_depth=n.full_depth) for n in Nodes(sim)])
    rows = []
    for l in Links(sim):
        up, dn = l.connections
        kind = ("orifice" if l.is_orifice() else "weir" if l.is_weir() else
                "pump" if l.is_pump() else "outlet" if l.is_outlet() else "conduit")
        rows.append(dict(id=l.linkid, kind=kind, up=up, dn=dn))
    lk = pd.DataFrame(rows)
    sim.start()
    init_settings = {g: Links(sim)[g].target_setting for g in GATES}     # INP-native initial gate settings
nd.to_csv("runs/diag_nodes.csv", index=False); lk.to_csv("runs/diag_links.csv", index=False)
print(nd[nd.id.isin(WATCH)].to_string())
print("node types:", nd[["outfall", "storage", "junction"]].sum().to_dict())
print(lk[lk.kind.isin(["orifice", "weir", "pump", "outlet"])].to_string())
txt = open(INP).read()
print(re.findall(r"FLOW_UNITS\s+\w+", txt)); print(re.search(r"\[RAINGAGES\][\s\S]{0,500}", txt).group(0))
print("INP-native initial gate settings:", init_settings)

# 2) is 'storage fill' rain-dependent?  dry vs wet vs 3x wet, identical gates
env, agent, kb = A.build(0)
storms = load_storms("rain_real_full", scaling="none")
wet = max(storms, key=lambda s: s.depth.sum())
dry = Storm("dry", "diag", np.zeros(288), np.zeros(288), "test", {"scaling": "none"})
big = Storm("wet_x3", "diag", wet.intensity * 3, wet.depth * 3, "test", {"scaling": "none"})

def run(storm, native=False):
    env.reset(options={"storm": storm, "baseline_flooding": 0.0, "physical_rain": True, "native": native})
    d = {n: [] for n in WATCH}; first = None; done = False
    while not done:
        _, _, term, trunc, _ = env.step(np.full(10, 0.5))
        for n in WATCH:
            d[n].append(env._node_obj[n].depth)
        if first is None:
            first = {g: getattr(env, "O" + g).target_setting for g in ["1360", "1360_B"]}
        done = bool(term or trunc)
    return pd.DataFrame(d), first

d0, f_nonnative = run(dry); d1, _ = run(wet); d3, _ = run(big)
print("max |depth(wet) - depth(dry)| per watch node:\n", (d1 - d0).abs().max().round(4).to_string())
print("max |depth(x3)  - depth(dry)| per watch node:\n", (d3 - d0).abs().max().round(4).to_string())
_, f_native = run(wet, native=True)
print("initial gate settings  non-native:", f_nonnative, " native-mode:", f_native, " INP-native:", init_settings)
```
**Decision table**

| Result | Meaning | Action |
|--------|---------|--------|
| Nodes 54/54_B/65/65_B are `outfall=True` | "storage fill" is tailwater | Replace with true storage units (Stage 1); A1 confirmed |
| `max|depth(wet) − depth(dry)| ≈ 0` for 54/54_B | Rain-independent state | Same; R1/R7/`r_close` carry no storm information |
| native-mode initial settings = 0.5 ≠ INP-native | A2 confirmed | Fix native mode; rebuild all native references |
| `FLOW_UNITS CFS` | US units | Depths are **feet**; fix all "m" labels and margins |

### 5.2 Also rerun
- Dose–response (previous message) with `physical_rain=True`: scale one extreme real event by k in {1, 2, 4, 6.35, 10, 25.4} and print CSO and flooding. This tells you where CSO starts and re-establishes what the cache really contains.
- Rebuild `baseline_cache.json` with a key that includes `RAIN_CONV_VERSION`, `physical_rain`, `native_fixed` and the KB version.

---

## 6. Stage-by-stage implementation, with prompts

**Preamble for every session**
```text
You are modifying an existing research codebase (neurosymbolic SAC for SWMM CSO control).
Read methodology.md, app.py and the multistorm/ and research/ packages before editing.
HARD RULES:
- Every behavioural change is an opt-in flag whose default reproduces Trial 7 (tests/test_golden.py must pass).
- Research runs use physical rain only (physical_rain=True), scaling="none", provenance guard ON.
- Never read the test split in any training, tuning or selection code path.
- All reported numbers must be reproducible from runs/*/final_eval.csv by a script.
- No new dependencies without telling me; prefer numpy/pandas/scipy/torch/networkx/cma.
- Small diffs, run tests after each stage, print the effective config of every run.
```

### Stage 1 — Env/KB plumbing (A2, A3, A8, A9, A11, A12)
```text
In app.py add opt-in flags (defaults = v7): 
 1) native_mode must skip _apply_defaults() and all target_setting writes; add a test that native-mode initial settings equal the INP's own.
 2) use_projection (default True): False bypasses KB.project_action (pumps still 1.0).
 3) real_only: if True, raise unless physical_rain is True and a storm was supplied.
 4) Build from the INP: storage_ids = nodes with is_storage(), junction_ids = nodes with is_junction(), outfall_ids; units from [OPTIONS].
    Add obs fields: store_fill_ratio (sum depth / sum full_depth over storage_ids; use volume if available), max_dr_junction (junctions only).
    Keep the legacy fields so v7 numbers do not change.
 5) action 7-D support: if raw action has 7 entries append [1,1,1] for pumps; action_space accepts either via flag policy_dim.
 6) step() returns terminated=False and truncated=True at the horizon (flag time_limit_truncation).
 7) project_action(..., return_info=True) additionally returns which rules fired (R1/R2/R6 or v8 F1/F2/S1) and the intervention magnitude.
 8) get_episode_log(): add cso_flow_35391, cso_flow_35444, pump_flow (sum of the 3 pumps), actions_raw, store_fill_ratio,
    max_dr_junction, rule_flags (T x n_rules), and per-step cost.
Update adapters and BaselineStore cache key. Run test_golden and the diagnostics.
```
**Accept:** golden test passes with defaults; native-mode test passes; logs contain all fields.

### Stage 2 — Topology extraction (`research/topology.py`)
```python
# research/topology.py
import networkx as nx, pandas as pd

def build_graph(links_csv="runs/diag_links.csv"):
    L = pd.read_csv(links_csv)
    G = nx.MultiDiGraph()
    for r in L.itertuples():
        G.add_edge(r.up, r.dn, key=r.id, kind=r.kind)
    return G, L

def gate_context(G, L, nodes, gates, cso_weirs):
    kind = nodes.set_index("id")
    storage = set(kind.index[kind.storage]); junction = set(kind.index[kind.junction])
    link = L.set_index("id")
    rows = []
    for g in gates:
        up, dn = link.loc[g, "up"], link.loc[g, "dn"]
        down = nx.descendants(G, dn) | {dn}
        upstream = nx.ancestors(G, up) | {up}
        w_up = {w: link.loc[w, "up"] for w in cso_weirs}
        rows.append(dict(gate=g, up=up, dn=dn,
                         storage_down=sorted(down & storage),
                         weirs_down=[w for w, u in w_up.items() if u in down],
                         risk_up=sorted(upstream & junction)))
    return pd.DataFrame(rows)
```
**Prompt:** *"Using runs/diag_nodes.csv and runs/diag_links.csv write research/topology.py (above), print `gate_context` for the 7 gates and the two weirs 35391 and 35444, export `runs/gate_topology.csv`, and draw the network graph colouring gates, storage, weirs, outfalls (PNG). Flag every gate whose downstream set reaches a weir without passing a storage unit."* **Accept:** I review `gate_topology.csv` with you; it replaces the "topology ambiguous" comment.

### Stage 3 — Scenario factory
**Prompt:** *"Implement research/scenarios.py (above). Inputs: rain_real_full catalog filtered to years ≥ 2010 and QC-clean. Produce rain_scaled/ ladder files for T in 5,10,25,50,100 and rain_scaled_test/ files for 200,500,1000 (requires an Atlas 14 table CSV; refuse to build > 100 yr without it). Write data_manifest.json with provenance, parent, T_target, k, anchor, T_by_dur, sha256. Extend research/guard.py as described. Splits: by parent event, by calendar year blocks (train: earliest years, val: middle, test: latest), inherited by children. Print counts per split × rung and the histogram of k."* **Accept:** ≥ 3 parent events per split per rung; k within [0.67, 4]; counts reported.

### Stage 4 — Controllability screening (hindsight optimum)
Purpose: measure the **achievable** CSO reduction per event and severity before training; skip regimes where control cannot help, and use the result as the oracle for regret metrics.
```python
# research/controllability.py
import numpy as np, cma
from multistorm.evaluate import evaluate_policy_on_storm      # you have this logic in evaluate(); expose it per storm

class SchedulePolicy:
    """Open-loop piecewise-constant gate schedule: params (n_seg, 7) in [0,1]; pumps = 1."""
    def __init__(self, params, n_steps=287):
        self.p = np.clip(np.asarray(params, float).reshape(-1, 7), 0, 1)
        self.seg = int(np.ceil(n_steps / len(self.p))); self.t = 0
    def select_action(self, obs, deterministic=True):
        a = np.r_[self.p[min(self.t // self.seg, len(self.p) - 1)], np.ones(3)]
        self.t += 1
        return a.astype(np.float32)

def static_search(env, storm, ref, n=64, seed=0, use_projection=False):
    rng = np.random.default_rng(seed)
    cands = [np.full(7, 0.5), np.zeros(7), np.ones(7)] + [rng.uniform(0, 1, 7) for _ in range(n)]
    best = None
    for x in cands:
        s = evaluate_policy_on_storm(env, SchedulePolicy(x[None]), storm, use_projection=use_projection)
        cost = s["cso_total"] / max(ref["cso_total"], 1.0) + 10 * max(s["flood_total"] - ref["flood_total"], 0) / max(ref["flood_total"], 1e3)
        if best is None or cost < best[0]:
            best = (cost, x, s)
    return best

def cma_search(env, storm, ref, n_seg=4, iters=25, pop=12, seed=0, x0=None, use_projection=False):
    f = lambda x: (lambda s: s["cso_total"] / max(ref["cso_total"], 1.0)
                   + 10 * max(s["flood_total"] - ref["flood_total"], 0) / max(ref["flood_total"], 1e3))(
        evaluate_policy_on_storm(env, SchedulePolicy(np.reshape(x, (n_seg, 7))), storm, use_projection=use_projection))
    es = cma.CMAEvolutionStrategy(np.full(7 * n_seg, 0.5) if x0 is None else x0, 0.25,
                                  dict(bounds=[0, 1], popsize=pop, maxiter=iters, seed=seed, verbose=-9))
    while not es.stop():
        xs = es.ask(); es.tell(xs, [f(x) for x in xs])
    return es.result.fbest, es.result.xbest
```
**Prompt:** *"Write research/controllability.py (above) with `evaluate_policy_on_storm` exposed from evaluate.py. For every train/val storm: reference = TRUE native run; run static_search (use_projection False and True), then cma_search on storms where the static result is within 5% of reference. Output runs/controllability.csv: storm_id, ref_cso, best_static_cso, best_hindsight_cso, achievable_pct_static, achievable_pct_hindsight, ref_flood, best_flood, wall time. Run per-event in parallel processes (one SWMM per process). Budget: ≈ 8 min per event for static search, ≈ 40 min for CMA-ES."* **Accept:** table exists; **training eligibility rule** fixed in `protocol.md`, for example `achievable_pct_hindsight ≥ 10%` or `ref_cso > floor`.

### Stage 5 — KB v8 (reward, cost, rules)
```python
# in app.py or multistorm/kb_v8.py
class KnowledgeBaseV8(SymbolicKnowledgeBase):
    """Opt-in v8 semantics; the parent class is untouched."""
    def __init__(self, *a, topo=None, theta=None, w_cso=10.0, w_store=2.0, delta=0.05, eps_cso=0.01,
                 cso_floor=1.0, v_scale_m3=1000.0, margin=2.0, horizon=287, junctions=(), **kw):
        super().__init__(*a, **kw)
        self.topo, self.theta = topo, theta or {}
        self.w_cso, self.w_store, self.delta, self.eps = w_cso, w_store, delta, eps_cso
        self.cso_floor, self.v_scale, self.margin, self.T = cso_floor, v_scale_m3, margin, horizon
        self.junctions, self.ref_cso = set(junctions), cso_floor

    def set_reference(self, cso_total_cfs_steps):                 # per storm, from TRUE native reference
        self.ref_cso = max(float(cso_total_cfs_steps), self.cso_floor)

    def cost(self, obs):
        flood_m3 = obs["flooding"] * 900.0 * 0.0283168
        c_depth = sum(max(d - (self.node_full_depths[n] - self.margin), 0.0) / max(self.node_full_depths[n], 1e-6)
                      for n, d in obs["node_depths"].items() if n in self.junctions)
        return flood_m3 / self.v_scale + 0.1 * c_depth

    def shape_reward(self, obs, raw, proj):
        cso = max(obs["cso_flow"], 0.0)
        fill = obs["store_fill_ratio"]
        r_cso = -self.w_cso * cso / self.ref_cso
        v = float(cso > self.eps) * max(0.0, 1.0 - self.delta - fill)
        r_store = -self.w_store * v / self.T
        total = r_cso + r_store
        return total, dict(cso_penalty=r_cso, store_first=r_store, gate_close=0.0,
                           flood_penalty=0.0, cost=self.cost(obs), total=total)
```
Shield (`project_action_v8`) implements Section 4.3 using `topo` and `theta`. **Prompt:** *"Implement KnowledgeBaseV8 and project_action_v8 (rules F1, F2, S1, S2, P1 from guide Section 4.3) using runs/gate_topology.csv; parameters from a theta dict; return rule flags and intervention magnitude. Unit-test each rule on hand-made observations; with `kb_version='v7'` the old class is used unchanged."*

### Stage 6 — Constrained SAC agent (SAC-Lag) and ring replay
```python
# multistorm/agents_lag.py
import numpy as np, torch, torch.nn.functional as F, torch.nn.utils as nn_utils, torch.optim as optim
from app import SACAgent, Critic, device

class RingReplay:
    def __init__(self, cap, obs_dim, act_dim):
        self.cap, self.i, self.n = cap, 0, 0
        self.o = np.zeros((cap, obs_dim), np.float32); self.no = np.zeros_like(self.o)
        self.a = np.zeros((cap, act_dim), np.float32)
        self.r = np.zeros((cap, 1), np.float32); self.c = np.zeros_like(self.r); self.d = np.zeros_like(self.r)
    def push(self, o, a, r, c, no, d):
        j = self.i
        self.o[j], self.a[j], self.r[j], self.c[j], self.no[j], self.d[j] = o, a, r, c, no, d
        self.i, self.n = (j + 1) % self.cap, min(self.n + 1, self.cap)
    def __len__(self): return self.n
    def sample(self, B):
        k = np.random.randint(0, self.n, B)
        t = lambda x: torch.as_tensor(x[k], device=device)
        return t(self.o), t(self.a), t(self.r), t(self.c), t(self.no), t(self.d)

class SACLagAgent(SACAgent):
    """SAC + cost critic + dual variable. Policy is 7-D (pumps appended by the env)."""
    def __init__(self, obs_dim, action_dim=7, cost_limit=0.05, lam_init=0.5, lam_lr=0.02, lam_max=50.0, **kw):
        super().__init__(obs_dim, action_dim, **kw)
        hid, lr = kw.get("hidden", 256), kw.get("lr", 1e-4)
        self.cost_critic = Critic(obs_dim, action_dim, hid).to(device)
        self.cost_target = Critic(obs_dim, action_dim, hid).to(device)
        self.cost_target.load_state_dict(self.cost_critic.state_dict())
        self.cost_opt = optim.Adam(self.cost_critic.parameters(), lr=lr)
        self.replay = RingReplay(kw.get("buffer_cap", 50_000), obs_dim, action_dim)
        self.target_entropy = -float(action_dim)                     # standard -|A| for a 7-D policy
        self.cost_limit, self.lam, self.lam_lr, self.lam_max = cost_limit, lam_init, lam_lr, lam_max
        self.lam_log = []

    def store(self, s, a, r, c, ns, d):
        f = lambda x: x.detach().cpu().numpy() if isinstance(x, torch.Tensor) else np.asarray(x)
        self.replay.push(f(s), f(a), r, c, f(ns), d)

    def end_episode(self, ep_cost):                                   # dual ascent on the episode cost
        self.lam = float(np.clip(self.lam + self.lam_lr * (ep_cost - self.cost_limit), 0.0, self.lam_max))
        self.lam_log.append(self.lam)

    def _soft(self, net, tgt):
        for p, pt in zip(net.parameters(), tgt.parameters()):
            pt.data.copy_(self.tau * p.data + (1 - self.tau) * pt.data)

    def update(self):
        if len(self.replay) < self.batch_size: return
        s, a, r, c, ns, d = self.replay.sample(self.batch_size)
        alpha = self.log_alpha.exp().detach()
        with torch.no_grad():
            na, lp = self.actor.sample(ns)
            y = r + self.gamma * (1 - d) * (self.critic_target.min_q(ns, na) - alpha * lp)
            yc = c + self.gamma * (1 - d) * torch.max(*self.cost_target(ns, na))
        q1, q2 = self.critic(s, a)
        self.critic_opt.zero_grad(); (F.mse_loss(q1, y) + F.mse_loss(q2, y)).backward()
        nn_utils.clip_grad_norm_(self.critic.parameters(), self.MAX_GRAD_NORM); self.critic_opt.step()
        c1, c2 = self.cost_critic(s, a)
        self.cost_opt.zero_grad(); (F.mse_loss(c1, yc) + F.mse_loss(c2, yc)).backward()
        nn_utils.clip_grad_norm_(self.cost_critic.parameters(), self.MAX_GRAD_NORM); self.cost_opt.step()
        a_new, lp_new = self.actor.sample(s)
        alpha = self.log_alpha.exp()
        qr = self.critic.min_q(s, a_new); qc = torch.max(*self.cost_critic(s, a_new))
        loss_pi = (alpha.detach() * lp_new - (qr - self.lam * qc) / (1.0 + self.lam)).mean()
        self.actor_opt.zero_grad(); loss_pi.backward()
        nn_utils.clip_grad_norm_(self.actor.parameters(), self.MAX_GRAD_NORM); self.actor_opt.step()
        al = -(self.log_alpha * (lp_new + self.target_entropy).detach()).mean()
        self.alpha_opt.zero_grad(); al.backward(); self.alpha_opt.step()
        self._soft(self.critic, self.critic_target); self._soft(self.cost_critic, self.cost_target)
```
**Prompt:** *"Add multistorm/agents_lag.py (above). In train_one_episode support: policy_dim 7, per-step cost from the breakdown, `terminated` only stored as `d`, `updates_per_step` (UTD) configurable, and `agent.end_episode(sum(costs))` at episode end. Log lam, cost per episode, and intervention rate. SAC-Lag must be selectable via --variant; the plain SACAgent path is untouched."*
Notes: the cost limit should be **small but positive** (for example 0.05 of the reference cost scale) with a **hard cap** on λ; `cost_limit = 0` makes λ run away on any unavoidable flood. The shield, not λ, provides the hard guarantee.

### Stage 7 — Storage-first specification module (`multistorm/stl.py`)
```python
# multistorm/stl.py
import numpy as np

def rho_flood_free(flood, eps=1e-6):
    """G(flood_t <= eps): robustness = min_t (eps - flood_t); >= 0 means satisfied."""
    return float(np.min(eps - np.asarray(flood, float)))

def rho_storage_first(cso, fill, eps_cso=0.01, delta=0.05):
    """G( cso_t > eps -> fill_t >= 1-delta )  ==  G( cso_t <= eps  OR  fill_t >= 1-delta )."""
    a = eps_cso - np.asarray(cso, float); b = np.asarray(fill, float) - (1.0 - delta)
    return float(np.min(np.maximum(a, b)))

def storage_metrics(L, eps_cso=0.01, delta=0.05):
    cso = np.asarray(L["cso_flow"], float); fill = np.asarray(L["store_fill_ratio"], float)
    act = cso > eps_cso; viol = act & (fill < 1.0 - delta)
    return dict(
        peak_store_util=float(fill.max()),
        suo_onset=float(fill[np.argmax(act)]) if act.any() else float("nan"),      # storage utilisation when overflow starts
        fill_during_cso=float(fill[act].mean()) if act.any() else float("nan"),
        store_first_viol_steps=int(viol.sum()),
        store_first_viol_rate=float(viol.sum() / act.sum()) if act.any() else float("nan"),
        rho_storage_first=rho_storage_first(cso, fill, eps_cso, delta),
        rho_flood_free=rho_flood_free(L["flooding"]),
        sat_storage_first=bool(rho_storage_first(cso, fill, eps_cso, delta) >= 0),
        sat_flood_free=bool(rho_flood_free(L["flooding"]) >= 0),
    )
```
**Prompt:** *"Add multistorm/stl.py (above) and merge storage_metrics(L) into evaluate() rows. Unit-test with synthetic traces: overflow with headroom ⇒ violation; overflow at full storage ⇒ satisfied; flood anywhere ⇒ rho_flood_free < 0."*

### Stage 8 — Data-calibrated rules and the optimised-rule baseline (B3)
**Prompt:** *"Create research/optimize_rules.py: parameters θ = (θ_f, θ_f_open, θ_E, θ_s, δ, default gate setting per topology cluster). Objective on TRAIN storms only: mean(cso/CSO_ref) + 10·mean(max(flood − flood_ref,0))/scale. Use CMA-ES with fixed seeds, evaluate with the real env (rule-only policy, constant raw action), early-stop on VALIDATION score. Save theta.json (versioned, hash recorded). The resulting optimised rule controller is baseline B3; the shield in NS-SAFE-SAC uses the same theta."* **Accept:** B3 beats B2 on validation; if it does not, say so in the paper.

### Stage 9 — Training pipeline updates
**Prompt:** *"Extend multistorm/train_multi.py: (a) `--diet` in {D1_flat2, D2_ladder100, D3_ladder1000, D4_real, D5_design(optional, labelled)}; (b) a StratifiedSampler: choose a rung uniformly, then a storm within the rung by shuffled cycle; (c) eligibility from runs/controllability.csv; (d) per-rung logging of CSO reduction, flood, intervention rate, lam; (e) selection score = validation macro CSO reduction (vs TRUE native) with caps: flood non-regression rate ≥ 0.95 and r6/F2 excess ≤ 0.01; (f) checkpoints keep theta.json hash and KB version; (g) real-only/provenance guard on."*

```python
class StratifiedSampler:
    def __init__(self, storms, key=lambda s: s.meta.get("T_target", 0), seed=0):
        self.rng = np.random.default_rng(seed)
        self.groups = {}
        for s in storms: self.groups.setdefault(key(s), []).append(s)
        self.queues = {k: [] for k in self.groups}; self.counts = {s.storm_id: 0 for s in storms}
    def next(self):
        k = list(self.groups)[int(self.rng.integers(len(self.groups)))]
        if not self.queues[k]:
            self.queues[k] = [int(i) for i in self.rng.permutation(len(self.groups[k]))]
        s = self.groups[k][self.queues[k].pop()]; self.counts[s.storm_id] += 1
        return s
```

### Stage 10 — Evaluation additions
Add to `multistorm/metrics_ext.py`:
```python
def vs_hindsight(s, ref, hind, floor=1.0):
    den = ref["cso_total"] - hind["cso_total"]
    return dict(pct_achievable_captured=100 * (ref["cso_total"] - s["cso_total"]) / den if den > floor else float("nan"),
                regret_vs_hindsight=s["cso_total"] - hind["cso_total"])

def flood_nonregression(s, ref, rel_tol=0.02, abs_tol=10.0):
    ok = s["flood_total"] <= ref["flood_total"] * (1 + rel_tol) + abs_tol
    zero_ok = (not (ref["flood_total"] <= abs_tol)) or (s["flood_total"] <= abs_tol)
    return dict(flood_nonregress=bool(ok), flood_zero_when_feasible=bool(zero_ok))

def scorecard(row):             # per-event pass = no flood regression AND CSO not worse than reference
    return bool(row["flood_nonregress"] and row["cso_delta"] <= 0)
```
`ref` is the **true native** record; `hind` the hindsight record from Stage 4. Headline metrics per split and per rung: median/IQM CSO reduction vs native, `pct_achievable_captured`, scorecard pass-rate, `flood_nonregress` rate, `flood_zero_when_feasible` rate, `suo_onset`, `store_first_viol_rate`, intervention rate, capture ratio, actuation TV, CSO event count, plus the Stage 15–16 statistics (hierarchical bootstrap, paired Wilcoxon, Holm) already implemented.

### Stage 11 — Experiment matrix (priorities)

| Tier | Runs | Seeds |
|------|------|-------|
| **T1 must** | B0 static, **B1 true native**, B2 v7 rules, **B3 optimised rules**, **O1 hindsight** (Stage 4); V7 (current SAC+KB v7, retrained under physical rain), **V8-Full**, SAC-plain, SAC-Lag (no shield, no store-first) | 5 |
| **T2 should** | V8 ablations: −topo, −store-first, −Lagrangian, −shield, −refnorm, −obs v8, 10-D policy; DDPG comparator (best published on this network) | 5 (3 minimum) |
| **T3 diet study** (V8-Full only) | D1 flat×2, D2 ladder≤100, D3 ladder+1000, D4 real only, D5 design (optional) | 3–5 |
| T4 optional | Robustness (obs noise, sensor dropout, stuck gate); predictive shield (N7); grouped year-fold CV | 3 |

Compute: about 3 h CPU per run; T1+T2 ≈ 20–25 learned runs × 5 seeds ≈ 100+ runs ≈ 300 CPU-h; run one process per seed (SWMM is not thread-safe in a process). Do a 1-seed pilot of every variant first; only scale up variants that train stably.

### Stage 12 — Hypotheses to freeze in `docs/protocol.md` (before any test run)
- **H1** V8-Full reduces CSO vs **true native** on unscaled real test events (macro reduction > 0, CI excludes 0) with flood non-regression ≥ 95% of events.
- **H2** V8-Full ≥ B3 (optimised rules) on ladder test rungs; if not, rules explain most of the gain.
- **H3** V8-Full ≥ SAC-plain and SAC-Lag on CSO reduction, and has fewer storage-first violations and lower flood regression.
- **H4** Each of topo-KB, store-first, Lagrangian, shield contributes on at least one primary metric (ablations).
- **H5** Diet D2 > D1 and D4 on held-out real events; D3 (adding 1000-yr) does not help and may hurt (answers your question empirically).
- **H6** Degradation across rungs: gains peak in 5–25 yr; above 100 yr the agent matches the reference but cannot eliminate flooding (report hindsight-flood as the floor).

### Stage 13 — Reporting
Tables: dataset by family/rung/split; main results (real test, ladder test, stress rungs); ablations; paired tests (Holm); storage metrics; safety (flood non-regression, zero-flood-when-feasible, intervention rates); compute. Figures: network + topology graph; scenario overview (T_eq distribution unscaled vs scaled; k histogram); CSO reduction by rung with CIs; **achievable-captured %** by rung; storage utilisation at overflow vs reference; example hydrographs (native vs B3 vs V8-Full: gates, storage fill, CSO) for one 10-yr and one 100-yr event; λ and cost curves; learning curves with seed bands; diet-study comparison.

### Stage 14 — Predictive shield (stretch, N7)
Hot-start based k-step look-ahead: save a SWMM hotstart each control step (PySWMM supports saving/using hotstart files **[VERIFY]**), simulate the candidate action for k steps (k = 2–4) under persisted rainfall, and if projected junction depth ratio or flooding crosses limits, substitute the safe fallback (e.g. the B3 action). Cost is about (k+1)× simulation time per step; evaluate only on the test rungs where it matters and report the added latency. Do this only after T1–T3 are done.

---

## 7. What else I need from you (to turn this guide into exact patches)

1. **`multistorm/physical_inp.py`**, **`multistorm/adapters.py`**, **`multistorm/storms.py`**, **`multistorm/evaluate.py`**, **`multistorm/train_multi.py`** (so I can check the rain-injection path, how `static_fn`/`native_fn` call the env, and the cache key).
2. **INP sections** (paste text, not the whole file): `[OPTIONS]`, `[RAINGAGES]`, `[TIMESERIES]` (names/length only), `[INFLOWS]`, `[CONTROLS]`, `[STORAGE]`, `[OUTFALLS]`, `[ORIFICES]`, `[WEIRS]`, `[PUMPS]`.
3. **Output of Stage 0** (`diag_semantics.py` prints and `runs/diag_nodes.csv`, `runs/diag_links.csv`) and the dose–response table.
4. **`runs/unit_audit.json`**, one `train_log.csv`, one `final_eval.csv`.
5. **Atlas 14 depth table** for your gauge/catchment (including the 90% confidence intervals) if you plan any rung above 100 yr.
6. Whether you can obtain the **Sept 2018 / Aug 2019** rainfall (anchor events) or the utility's gauge record for the 2016–2017 calibration events.

---

## 8. Definition of done (go/no-go before writing the paper)

- [ ] Stage 0 diagnostics pass; storage state defined from true storage units; native mode verified.
- [ ] Golden test passes with v7 defaults; v8 flags documented; effective config printed per run.
- [ ] Scenario families R/L/X/A built with provenance, parent-based splits, guard enforced.
- [ ] Controllability table and hindsight references computed; training eligibility rule frozen.
- [ ] Optimised-rule baseline B3 and true-native B1 reported.
- [ ] V8-Full and all T1/T2 runs with ≥ 5 seeds (≥ 3 minimum); statistics with hierarchical bootstrap, paired tests, Holm correction.
- [ ] Diet study answers the 2× / ladder / 1000-yr question empirically.
- [ ] Flood non-regression and zero-flood-when-feasible reported per rung; extreme-rung unavoidable flooding stated.
- [ ] Novelty verification table completed and the contribution phrased as the verified gap.
- [ ] Limitations stated: digital twin only, calibration range 1.8-yr vs scaled storms, scaled-historical events are not observed events, single network, empirical (not formal) safety.

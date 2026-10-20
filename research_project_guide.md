# From Experiment to Research Project — Real-Rainfall Neurosymbolic RL for CSO Control
**Builds on:** `multi_rainfall_implementation_guide.md` (Stages 0–9, already implemented)
**This guide:** real observed rainfall only, standard hydraulic + RL + statistical evaluation, baselines/ablations, pre-registered protocol, reproducibility package, paper plan, and vibe-coding stages 10–19.

> **Caveat.** I have still not seen `app.py` or your results, so everything is anchored to `methodology.md` and the Stage 0–9 code. Items I could not verify online are marked **[VERIFY]**. Station IDs, file layouts and URLs for data you must fetch are deliberately **not** invented here; the coding assistant must read the official documentation first.

---

## 0. Read first: corrections to the earlier guide

| # | Correction | Why |
|---|------------|-----|
| 1 | The previous guide suggested synthetic/design hyetographs and `--augment-scales`. **Do not use either for any reported result.** | You require real rainfall. Intensity augmentation is synthetic by definition |
| 2 | `scaling="peak"` (peak → 24) rewrites real storms. **Use `scaling="none"` for all real events.** | Peak scaling destroys the severity information that makes real storms scientifically meaningful (and makes them semi-synthetic) |
| 3 | `randomrainfall.xlsx`, `raindata.csv` and `test_rainfall_0.01_1.csv` have **unknown provenance**. | Unless you can document them as observed (station, dates, source), keep them only for development/regression tests and exclude them from every reported number |
| 4 | **Unit audit is mandatory before real data goes in** (Section 3). | Trial 7 describes rainfall as "mm per 15 min" and feeds it to `rg1.total_precip`. SWMM models in CFS are US-customary, and the toolkit setter is, as far as I know, an *intensity* in project units (in/hr for US units) **[VERIFY]**. If so, Trial 7 storms may be physically far larger than their stated millimetres, which would also explain a baseline flooding of ~7,000 and R6 threshold of 9,500 |
| 5 | A hard **real-only guard** (Section 2.7) refuses to train/evaluate unless every storm is in the observed-data manifest. | Prevents accidental mixing |

---

## 1. Research framing

### 1.1 Working title options
- *Neurosymbolic Reinforcement Learning for Real-Time Control of Combined Sewer Overflows: Generalization to Observed Storm Events*
- *Does Symbolic Knowledge Help? Safe SAC Control of a Detroit Combined Sewer Network Under Historical Rainfall*

### 1.2 Research questions and hypotheses (freeze these before looking at test results)

| ID | Research question | Hypothesis (falsifiable) | Primary evidence |
|----|-------------------|--------------------------|------------------|
| RQ1 | Does the agent reduce CSO on **unseen real storms** vs. current operation? | H1: macro CSO-volume reduction vs static baseline on the held-out test events is > 0 with 95% CI excluding 0 | Table 2, Fig. 3 |
| RQ2 | Does multi-event training generalize better than single-event training? | H2: multi-event agent > single-event agent on test events (paired, Holm-corrected) | Table 4 |
| RQ3 | Does the symbolic layer help beyond plain SAC? | H3: full neurosymbolic ≥ SAC-plain on CSO reduction **and** has lower flood excess / constraint violations; and reaches a given performance in fewer episodes | Tables 2–4, Fig. 5 |
| RQ4 | Which symbolic component matters? | H4: removing projection, predicates, or the gate-close shaping each degrades at least one primary metric | Table 3 (ablations) |
| RQ5 | How does benefit depend on storm severity? | H5 (exploratory): gains peak for moderate events; for extreme events overrides (R1/R2/R6) dominate and RL adds little | Fig. 4 |
| RQ6 | Is the policy robust to sensing/actuation faults? | H6: degradation under moderate noise is bounded relative to the static baseline | Table 5 |

### 1.3 Contributions you can claim (if evidence supports them)
1. A reproducible benchmark of **observed** storm events for a real SWMM CSO network, with documented event extraction, QC and a temporal split.
2. A multi-event training/evaluation protocol for neurosymbolic SAC with per-event baselines.
3. A systematic ablation of the symbolic components with statistically sound comparisons.
4. Open code, event manifest and (if licensing allows) the network model.

---

## 2. Real rainfall data pipeline

### 2.1 Candidate sources

| Source | What it offers | Status |
|--------|----------------|--------|
| **NOAA NCEI COOP 15-minute precipitation, v1 (DSI-3260)** | Quality-controlled 15-min accumulations at ~2,000 stations. Only intervals **with precipitation** are recorded (no entry for zeros), plus flags for missing and accumulated periods | Verified in NCEI/Data.gov catalog |
| **NOAA NCEI COOP 15-minute precipitation, v2 (CPD-15min)** | Newer version; direct download at `https://www.ncei.noaa.gov/data/coop-precipitation-15-minute/`. The catalog notes that access to 15-min data past 2014 was halted and restarted in 2025 | Verified in catalog; **[VERIFY]** which years/stations exist for the Detroit area |
| **Local utility / county gauges** (e.g. the model owner's calibration rain gauges for the 7 Mile / Hubbell Southfield system) | Gauges closest to the catchment, often at 5-min resolution | **Request from the model owner (the 2018 model came with a specific rain record).** Often the best option; confirm sharing permission |
| **NOAA Atlas 14, Volume 8 (covers Michigan)** | Not a rainfall record; precipitation-frequency estimates (depth by duration and return period) via the Precipitation Frequency Data Server. Public domain | Verified. Used here **only to classify real events by severity**, not to generate storms |
| ASOS 1-min / 5-min at Detroit airports; radar–gauge products (MRMS, Stage IV) | Higher resolution or areal rainfall | **[VERIFY]** availability and licensing yourself; optional extension |
| City of Ann Arbor 15-min gauges (2013 onward) | Real, open, 15-min, but ~40 miles from your catchment | Only as a supplementary or sensitivity dataset, not primary |
| CoCoRaHS | Daily totals only | Not suitable (interval too coarse) |

**Recommended primary design:** one primary gauge (closest to the catchment with the longest 15-min record) for the main benchmark, with a second gauge or the utility record as an independent *test* source if you can obtain one (strongest generalization claim).

### 2.2 Acquisition step (build with the coding assistant)

Output of acquisition is a **standardized series** per gauge:

`data/raw/<gauge>_15min_standardized.csv` with columns `time_utc` (ISO 8601) and `precip_mm` (float). Rules:
- Explicit `0.0` only where the gauge was demonstrably operating and dry; **blank (NaN) wherever missing, flagged, or part of an accumulated multi-interval period**.
- Convert from the source unit (check the documentation; NCEI 15-min values are typically hundredths of an inch **[VERIFY]**) to millimetres.
- Because v1 omits zero intervals, infer zeros from the begin/end *missing* flags in the documentation, never by naive zero-fill.
- Write `data/raw/raw_manifest.json` with source URL, retrieval date, station metadata, file SHA-256, unit conversion applied.

**Prompt (Stage 10):**
```text
Read the official NCEI documentation for the COOP 15-minute precipitation dataset (v2; v1 if v2 lacks the
years I need). Write research/acquire_ncei.py that downloads data for the stations I specify in
configs/data.json, parses values and quality/missing/accumulation flags exactly as documented,
converts to mm, and writes data/raw/<gauge>_15min_standardized.csv (time_utc, precip_mm) following these rules:
explicit 0.0 only where the gauge was operating and dry; NaN for missing, flagged or accumulated intervals.
Also write data/raw/raw_manifest.json (URL, retrieval date, station metadata, SHA-256, conversion).
Do not guess file layouts: if the documentation is ambiguous, stop and print what is ambiguous.
Add a coverage report: valid fraction per year and per month.
```
**Accept:** coverage report reviewed; years with < 90% valid data are excluded or flagged; manifest written.

### 2.3 Event definition (standard practice, with sensitivity)

- **Event separation:** inter-event dry period (IETD) of **6 h** (default); report sensitivity at 3 h and 12 h.
- **Event significance:** event total ≥ `min_event_depth_mm` (default 6.35 mm = 0.25 in; tune after the audit so that a meaningful share of events produces baseline CSO).
- **Simulation window:** 72 h (288 × 15 min), starting at **local-standard-time midnight of the event's start day**, so the real time-of-day alignment with the diurnal DWF pattern is preserved. Use a fixed UTC offset (standard time) to avoid DST gaps.
- **Rain inside the window that belongs to other events is kept** (it is real); count it in `n_other_events`.
- **QC rules (strict):** no missing 15-min value in the whole window; event end at least 6 h before window end (so the recession is simulated); windows must not overlap (greedy: keep the larger event).
- **Every rejected event is logged with a reason** (`events_rejected.csv`) for transparency.

### 2.4 Code: `research/events.py`

```python
# research/events.py
from __future__ import annotations
import numpy as np
import pandas as pd

N = 288                      # 72 h at 15 min
STD_OFFSET_H = -5            # fixed UTC offset for Detroit standard time (no DST)


def load_standardized(path) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["time_utc"])
    t = (df["time_utc"].dt.tz_localize(None) + pd.Timedelta(hours=STD_OFFSET_H)).dt.floor("15min")
    s = pd.Series(df["precip_mm"].to_numpy(float), index=t).groupby(level=0).sum(min_count=1)
    idx = pd.date_range(s.index.min(), s.index.max(), freq="15min")
    return s.reindex(idx)                         # NaN = missing/unknown


def detect_events(p: pd.Series, ietd_h=6.0, min_depth_mm=6.35) -> list[dict]:
    wet = np.flatnonzero(np.nan_to_num(p.to_numpy(), nan=0.0) > 0)
    if wet.size == 0:
        return []
    gap, spans, start, last = int(ietd_h * 4), [], wet[0], wet[0]
    for j in wet[1:]:
        if j - last - 1 >= gap:
            spans.append((start, last)); start = j
        last = j
    spans.append((start, last))
    out = []
    for s, e in spans:
        d = float(np.nansum(p.iloc[s:e + 1]))
        if d >= min_depth_mm:
            out.append(dict(start=p.index[s], end=p.index[e], i0=s, i1=e, depth_mm=d))
    return out


def extract_window(p: pd.Series, ev: dict, tail_margin_h=6.0):
    """Return (window Series, reject_reason|None)."""
    t0 = ev["start"].normalize()
    if t0 not in p.index:
        return None, "window_start_outside_record"
    i0 = p.index.get_loc(t0)
    if i0 + N > len(p):
        return None, "window_exceeds_record"
    w = p.iloc[i0:i0 + N]
    if w.isna().any():
        return None, "missing_values_in_window"
    if ev["end"] > w.index[-1] - pd.Timedelta(hours=tail_margin_h):
        return None, "event_too_long_for_window"
    return w, None


def descriptors(w: pd.Series) -> dict:
    a = w.to_numpy(float)
    r = lambda k: float(pd.Series(a).rolling(k).sum().max())
    return dict(total_mm=float(a.sum()), max15_mm=float(a.max()), max1h_mm=r(4), max3h_mm=r(12),
                max6h_mm=r(24), max24h_mm=r(96), wet_steps=int((a > 0).sum()),
                peak_pos_frac=float(a.argmax() / N))


def select_non_overlapping(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Greedy by event depth (largest first). Windows are [t0, t0+72h)."""
    keep, drop = [], []
    for r in sorted(rows, key=lambda r: -r["total_mm"]):
        if any(abs((r["t0"] - k["t0"]).total_seconds()) < N * 900 for k in keep):
            drop.append({**r, "reject": "overlaps_larger_event"})
        else:
            keep.append(r)
    return sorted(keep, key=lambda r: r["t0"]), drop


def ari_class(desc: dict, pfds: pd.DataFrame) -> dict:
    """pfds: index = duration in minutes (15, 60, 360, 1440); columns = ARI years (float, ascending);
    values = depth in mm (converted from the PFDS table; state whether AMS or PDS and keep it consistent)."""
    cols = {15: "max15_mm", 60: "max1h_mm", 360: "max6h_mm", 1440: "max24h_mm"}
    out, aris = {}, np.array(pfds.columns, float)
    for dur, key in cols.items():
        depths = pfds.loc[dur].to_numpy(float)
        x = desc[key]
        if x < depths[0]:
            ari = float(aris[0]) / 2          # "below the smallest tabulated ARI"
        elif x > depths[-1]:
            ari = float("inf")
        else:
            ari = float(np.exp(np.interp(x, depths, np.log(aris))))
        out[f"ari_{dur}min"] = ari
    out["ari_max"] = max(out.values())
    out["severity_class"] = ("<1yr" if out["ari_max"] < 1 else "1-2yr" if out["ari_max"] < 2 else
                             "2-5yr" if out["ari_max"] < 5 else "5-10yr" if out["ari_max"] < 10 else ">=10yr")
    return out
```

### 2.5 Event builder CLI: `research/build_real_storms.py`

**Prompt (Stage 11):**
```text
Create research/build_real_storms.py using research/events.py. Inputs: standardized series path(s),
configs/data.json (ietd_h, min_event_depth_mm, tail_margin_h, station metadata), PFDS table CSV
(durations 15/60/360/1440 min x ARIs, mm).
For each gauge: load_standardized -> detect_events -> extract_window -> descriptors -> ari_class,
select_non_overlapping. Write:
 - rain_real/<gauge>_<YYYYMMDD>.csv : headerless, 288 rows, INTENSITY in mm/h (= depth_mm_per_15min * 4)
 - rain_real/events.csv : one row per kept event (id, gauge, t0, descriptors, ARI classes, n_other_events)
 - rain_real/events_rejected.csv : every rejected event with its reason
 - rain_real/data_manifest.json : {"storms": {id: {"provenance": "observed", "gauge": ..., "source_sha256": ...,
   "file_sha256": ..., "t0": ...}}, "params": {...}}
Plot: rain_real/events_overview.png (total depth vs peak 15-min intensity, colored by severity_class, and a
histogram of events per year). Add tests with a hand-made series (known events, a gap, an overlap, a 90-h event).
```
**Accept:** tests pass; `events_overview.png` shows spread across severities; manifest SHA-256s match files.

### 2.6 Dataset targets and temporal split

- **Size:** at least ~40–60 kept events over many years is a healthy target; **fewer than ~20 total makes test-set claims weak.**
- **Split by time, in blocks of whole years** (never random across adjacent windows):
  - *Train*: earliest years.
  - *Validation*: a middle block (used for model selection and hyperparameter decisions).
  - *Test*: the **most recent** years (never touched until the protocol is frozen).
- Keep **at least one severe event in train** (the extrapolation guard from Stage 2 does this for random splits; do it by hand here) and report any test event whose depth exceeds the maximum training depth as "out-of-range".
- Optional robustness: **grouped K-fold by year** (e.g. 5 folds) for the main method, to show results are not an artefact of one split.

```python
# research/splits.py
import json
import pandas as pd

def split_by_year(events: pd.DataFrame, val_years: list[int], test_years: list[int]) -> dict:
    yr = pd.to_datetime(events["t0"]).dt.year
    sp = pd.Series("train", index=events.index)
    sp[yr.isin(val_years)] = "val"
    sp[yr.isin(test_years)] = "test"
    out = dict(zip(events["storm_id"], sp))
    cnt = sp.value_counts().to_dict()
    assert all(cnt.get(k, 0) >= 3 for k in ("train", "val", "test")), f"too few events per split: {cnt}"
    return out

if __name__ == "__main__":
    ev = pd.read_csv("rain_real/events.csv")
    json.dump(split_by_year(ev, val_years=[...], test_years=[...]), open("splits.json", "w"), indent=1)
```
(`splits.json` is exactly the manifest format Stage 2's `assign_splits(manifest_path=...)` already reads.)

### 2.7 Real-only guard (`research/guard.py`)

```python
# research/guard.py
import hashlib, json
from pathlib import Path

def assert_real_only(storms, rain_dir="rain_real", manifest="rain_real/data_manifest.json"):
    man = json.loads(Path(manifest).read_text())["storms"]
    bad = []
    for s in storms:
        m = man.get(s.storm_id)
        if not m or m.get("provenance") != "observed":
            bad.append((s.storm_id, "not in observed manifest"))
        elif s.meta.get("scaling") != "none":
            bad.append((s.storm_id, "rescaled"))
        elif "aug_scale" in s.meta:
            bad.append((s.storm_id, "augmented"))
        else:
            f = Path(rain_dir) / f"{s.storm_id}.csv"
            if hashlib.sha256(f.read_bytes()).hexdigest() != m["file_sha256"]:
                bad.append((s.storm_id, "file changed since manifest"))
    if bad:
        raise RuntimeError(f"Real-only guard failed: {bad}")
```
Call it in `train_multi.main()` and `audit.py` immediately after loading/splitting. Add config flags `--real-only` (default **on** for research runs) and force `augment_scales=[]` when on.

---

## 3. Model-validity checks before any learning (Work Package 0)

These protect the whole paper. Do them first.

### 3.1 Rainfall unit and format audit
1. Read `[RAINGAGES]` in the INP: the gauge **format** (INTENSITY / VOLUME / CUMULATIVE), **interval**, scale factor and source. Read `[OPTIONS]` flow units (CFS ⇒ US customary).
2. Confirm what `rg1.total_precip = x` means in your PySWMM/SWMM toolkit version (units and intensity-vs-depth). **[VERIFY]** in the PySWMM and SWMM toolkit documentation.
3. Run a controlled test: a constant known intensity for a known duration on an otherwise empty rainfall record, then compare the **total precipitation reported by SWMM** (report/continuity table, or subcatchment statistics) with the expected depth.
4. Decide a single conversion function `real_mm_per_15min → value passed to total_precip` and unit-test it.

**Prompt (Stage 12):**
```text
Write research/unit_audit.py. Using the same Simulation setup as the env (no control), apply a constant
rainfall for 2 hours (then zero) through rg1.total_precip with candidate unit conventions:
(a) value = mm/h, (b) value = mm per 15 min, (c) value = in/h. Read total precipitation and total runoff
from the SWMM report/continuity (or subcatchment statistics), print expected depth in mm for each convention
and the observed depth, and report which convention reproduces physical depth within 2%.
Also print the INP [RAINGAGES] line and [OPTIONS] flow units. Write results to runs/unit_audit.json.
Then implement `rain_to_gage_value(depth_mm_per_15min)` in multistorm/storms.py using the verified convention,
with a unit test. Do not change anything else.
```

**Decision tree after the audit:**
- **Trial 7 convention is physically correct** → proceed; thresholds (R6 = 9,500, baseline calibrations) are meaningful.
- **Trial 7 convention inflated rainfall** → you have a validity issue to disclose. Re-run the baseline audit with *physically correct* real storms. If R6 (flooding > 9,500) never triggers or the baseline CSO is almost always zero, the KB thresholds were tuned to a non-physical storm. In that case, make a **single, pre-registered recalibration** (e.g. R6 = 132% of the baseline flooding of a reference real storm, per the original rule) and say so in the paper. Do not silently tune on test events.

### 3.2 Baseline plausibility and model credibility
- **Continuity error:** record SWMM runoff and flow-routing continuity errors for every run; flag any run above the threshold you justify (report the distribution).
- **Baseline CSO frequency:** for real events, how many produce CSO at `35391`/`35444` under native operation? If utility CSO records or annual CSO counts exist for the outfalls, compare qualitatively (and say that the model was not re-calibrated here).
- **Audit table** (Stage 7) must show, per real event: baseline CSO volume, baseline flooding, R6 pressure, and flags `NO_CSO`, `R6_NEVER`, `R6_DOMINATES`.
- **Scored events:** events with baseline CSO above `cso_floor` are *scored* for reduction %; the rest are *safety events* (the agent must not create CSO or flooding). Report both counts.

### 3.3 Known limitation to state
The INP simulation window and DWF patterns are fixed to the 2018 model setup; real events from other years are replayed on this network. Weekday/weekend DWF alignment is not matched to the real calendar date (time-of-day alignment is).

---

## 4. Comparators and ablations

All learned variants use **identical** SAC hyperparameters, training budget (episodes and warm-up), observation raw state, seeds and event sets. Pumps stay frozen ON in every variant (treated as a physical configuration choice, not symbolic reasoning).

| ID | Method | What it is | Learned? |
|----|--------|-----------|----------|
| B0 | **Static** | gates 0.5, pumps ON, no projection | no |
| B1 | **SWMM native rules** | INP `[CONTROLS]` active, no RL writes (`options["native"]=True`, Stage 3) | no |
| B2 | **KB-rules only** | constant 0.5 gates passed through projection (R1/R2/R6) | no |
| M0 | **Full neurosymbolic SAC** (Trial 7) | your method | yes |
| M1 | **SAC-plain** | no projection, predicates masked to zeros (obs shape unchanged), reward = `r_cso + r_flood` only | yes |
| A1 | − projection | M0 without R1/R2/R6 gate rules | yes |
| A2 | − predicates | M0 with the 11 predicate dims zeroed | yes |
| A3 | − gate-close shaping | M0 reward without `r_close` | yes |
| E0 | **Single-event M0** | Trial 7 trained on one real event (the median-severity training event) | yes |
| O1 *(optional)* | **Hindsight open-loop optimum** | per-event schedule tuned directly on that event with CMA-ES/random search (e.g. piecewise-constant gate settings per 3 h). Not deployable; an approximate upper bound | search |
| P1 *(optional)* | Other RL (PPO/TD3) | shows the finding is not SAC-specific | yes |

**Implementation of ablations (Stage 14):** constructor flags on the env/KB that default to Trial 7 behaviour, so `test_golden.py` still passes:
`use_projection=True`, `use_predicates=True`, `reward_terms=("close","cso","flood")`.
Unified policy interface for non-learned methods:

```python
# multistorm/policies.py
import numpy as np

class ConstantPolicy:
    """B0 / B2: same select_action signature as SACAgent so evaluate() works unchanged."""
    def __init__(self, gates=0.5, pumps=1.0):
        self.a = np.array([gates] * 7 + [pumps] * 3, dtype=np.float32)
    def select_action(self, obs, deterministic=True):
        return self.a.copy()
# B0: env built with use_projection=False;  B2: env with use_projection=True.
# B1: env.reset(options={"native": True}) and the policy is ignored.
```

---

## 5. Evaluation metrics

### 5.1 Hydraulic performance (primary)

| Metric | Definition | Notes |
|--------|-----------|-------|
| **CSO volume** | `V = Σ_t (Q_35391 + Q_35444)·900 s`, reported in m³ (CFS × 0.0283168) | Primary KPI. Report per outfall and total |
| **CSO volume reduction (%)** | `100·(V_B0 − V_agent)/V_B0` per event; also vs B1 (native) | Undefined if `V_B0 ≈ 0` → event is a *safety event* |
| **CSO event count** | contiguous CSO activity separated by ≥ 6 h (same IETD as rainfall) | Regulatory-style metric |
| **CSO duration** | hours with `Q_cso > 0.01 cfs` (threshold documented) | |
| **CSO peak flow** | `max_t Q_cso` | |
| **Capture ratio (control structure)** | `V_pump / (V_pump + V_cso)` | Simple, well-defined proxy for system capture; document that it is not a full-system capture percentage |
| **Flooding volume / peak** | total and peak node flooding; **excess over event baseline** | Safety |
| **Flood ratio** | `V_flood,agent / V_flood,B0` | Must not exceed 1.05 on average (selection cap) |
| **Storage utilization** | peak fill ratio, time-weighted mean fill, fraction of steps ≥ 85% | Used by R1 |
| **Continuity errors** | SWMM runoff and routing continuity (%) | Validity check; report distribution |

### 5.2 Control behaviour

| Metric | Definition |
|--------|-----------|
| **Actuation effort** | mean `|Δa|` per step per gate (total variation); gate-direction reversals per episode |
| **Intervention rate** (neurosymbolic-specific) | fraction of steps where `‖a_proj − a_raw‖∞ > 1e-6` over gates 0–6; mean intervention magnitude; fraction of steps in R1 / R2 / R6 |
| **Constraint violations** | steps with flooding above threshold *after* projection; steps with storage ≥ 85% |
| **Inference latency** | ms per action (shows real-time feasibility vs the 15-min interval) |

### 5.3 Learning and statistical metrics (RL standard practice)

| Metric | Definition |
|--------|-----------|
| **Seed-aggregated score** | per-event CSO reduction %, averaged over seeds, then summarized across events |
| **IQM** (interquartile mean), mean, median, **optimality gap** | with **stratified/hierarchical bootstrap 95% CIs** (Agarwal et al., NeurIPS 2021, "Deep RL at the Edge of the Statistical Precipice") |
| **Performance profile** | fraction of events with reduction ≥ τ, for τ on a grid |
| **Probability of improvement** | P(method A beats method B on a random event) |
| **Sample efficiency** | episodes to reach 80% of final validation reduction; area under the validation-reduction learning curve |
| **Compute** | wall-clock and CPU-hours per run |
| **Generalization gap** | val − test macro reduction; reduction by severity class |

### 5.4 Code: extended metrics (add to `multistorm/metrics.py`)

The env log contract (Section 5 of the previous guide) must additionally provide `cso_flow_35391`, `cso_flow_35444`, `pump_flow` (sum of the three pump flows), `actions_raw` (T×10), `max_depth_ratio`, and, at episode end, `routing_error_pct` and `runoff_error_pct` (PySWMM exposes simulation continuity errors on the `Simulation` object in recent versions, otherwise parse the `.rpt`) **[VERIFY]**.

```python
# multistorm/metrics_ext.py
import numpy as np

CFS_TO_M3_PER_STEP = 0.028316846592 * 900.0
CSO_ON_CFS = 0.01


def count_events(active: np.ndarray, min_gap_steps: int = 24) -> int:
    idx = np.flatnonzero(active)
    if idx.size == 0:
        return 0
    return int(1 + np.sum(np.diff(idx) - 1 >= min_gap_steps))


def extended_summary(L: dict) -> dict:
    q1 = np.asarray(L["cso_flow_35391"], float)
    q2 = np.asarray(L["cso_flow_35444"], float)
    cso = q1 + q2
    pump = np.asarray(L["pump_flow"], float)
    acts = np.asarray(L["actions_projected"], float)[:, :7]
    raw = np.asarray(L["actions_raw"], float)[:, :7]
    v_cso = cso.sum() * CFS_TO_M3_PER_STEP
    v_pump = pump.sum() * CFS_TO_M3_PER_STEP
    d = np.abs(acts - raw)
    dA = np.diff(acts, axis=0)
    sgn = np.sign(np.where(np.abs(dA) > 0.02, dA, 0.0))
    reversals = int(np.sum((sgn[1:] * sgn[:-1]) < 0))
    return dict(
        cso_vol_m3=float(v_cso),
        cso_vol_35391_m3=float(q1.sum() * CFS_TO_M3_PER_STEP),
        cso_vol_35444_m3=float(q2.sum() * CFS_TO_M3_PER_STEP),
        cso_events=count_events(cso > CSO_ON_CFS),
        cso_hours=float((cso > CSO_ON_CFS).sum() * 0.25),
        cso_peak_cfs=float(cso.max()),
        capture_ratio=float(v_pump / (v_pump + v_cso)) if (v_pump + v_cso) > 0 else float("nan"),
        actuation_tv=float(np.abs(dA).mean()),
        gate_reversals=reversals,
        intervention_rate=float((d.max(axis=1) > 1e-6).mean()),
        intervention_mag=float(d.mean()),
        max_depth_ratio_peak=float(np.max(L["max_depth_ratio"])),
        routing_error_pct=float(L.get("routing_error_pct", float("nan"))),
        runoff_error_pct=float(L.get("runoff_error_pct", float("nan"))),
    )
```
Merge `extended_summary(L)` into each row in `evaluate()` (`**episode_summary(...), **extended_summary(L)`) and add `cso_vol_reduction_pct` computed from `cso_vol_m3` against the B0 reference record (extend `BaselineStore` records to store the extended summary too).

---

## 6. Statistical protocol

**Unit of analysis = storm event** (paired across methods), nested within **training seed**.

1. Per method and per event, average the metric over seeds → one value per event.
2. **Point estimate + 95% CI:** hierarchical bootstrap (resample events, then seeds) of IQM and mean.
3. **Paired comparisons** (method A vs method B, same events): median and mean paired difference with bootstrap CI; **Wilcoxon signed-rank** (two-sided); **rank-biserial correlation** as effect size; probability of improvement.
4. **Multiple comparisons:** Holm–Bonferroni across all pre-registered comparisons.
5. **No test-set peeking:** hyperparameters, thresholds, and model selection only on validation events.
6. **Seeds:** ≥ 5 for every learned method in the final tables (≥ 3 minimum). With few events, report the CIs honestly; say "n = k test events".
7. Report negative/neutral results as such.

```python
# multistorm/stats.py
from __future__ import annotations
import numpy as np
from scipy import stats


def iqm(x):
    return float(stats.trim_mean(np.asarray(x, float), 0.25))


def hier_bootstrap(M: np.ndarray, stat=np.mean, n_boot=10_000, alpha=0.05, seed=0):
    """M: (n_seeds, n_events). Resample events AND seeds; average seeds; apply stat over events."""
    rng = np.random.default_rng(seed)
    S, E = M.shape
    point = stat(M.mean(axis=0))
    boots = np.empty(n_boot)
    for b in range(n_boot):
        si, ei = rng.integers(0, S, S), rng.integers(0, E, E)
        boots[b] = stat(M[np.ix_(si, ei)].mean(axis=0))
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(point), (float(lo), float(hi))


def paired_compare(A: np.ndarray, B: np.ndarray, higher_is_better=True, n_boot=10_000, seed=0) -> dict:
    """A, B: (n_seeds, n_events), same events in the same order."""
    d = A.mean(0) - B.mean(0)
    if not higher_is_better:
        d = -d
    try:
        p = float(stats.wilcoxon(d, alternative="two-sided", zero_method="wilcox").pvalue)
    except ValueError:                       # all differences zero
        p = float("nan")
    nz = d[d != 0]
    ranks = stats.rankdata(np.abs(nz)) if nz.size else np.array([])
    rbc = float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum()) if nz.size else 0.0
    sgn = 1 if higher_is_better else -1
    D = sgn * (A - B)
    point, ci = hier_bootstrap(D, np.mean, n_boot, seed=seed)
    return dict(n_events=int(d.size), mean_diff=point, mean_diff_ci=ci,
                median_diff=float(np.median(d)), p_wilcoxon=p, rank_biserial=rbc,
                prob_improvement=float((d > 0).mean() + 0.5 * (d == 0).mean()))


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(((k, v) for k, v in pvals.items() if v == v), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, v) in enumerate(items):
        running = max(running, min(1.0, (m - i) * v))
        out[k] = running
    return {**{k: float("nan") for k in pvals if k not in out}, **out}


def performance_profile(x: np.ndarray, taus: np.ndarray) -> np.ndarray:
    """Fraction of events with score >= tau."""
    x = np.asarray(x, float)
    return np.array([(x >= t).mean() for t in taus])
```

---

## 7. Experimental protocol

### 7.1 Protocol freeze (commit before touching the test split)
Create `docs/protocol.md` containing: hypotheses (Section 1.2), event-extraction parameters, split years, metric definitions, selection rule (validation macro CSO reduction with caps r6_excess ≤ 0.01 and flood ratio ≤ 1.05), seeds, budgets, comparison list and test procedure. Commit it and tag the commit (`git tag protocol-v1`). Any later change is reported as a deviation.

### 7.2 Run matrix

| Block | Runs | Seeds | Notes |
|-------|------|-------|-------|
| Learned methods | M0, M1, A1, A2, A3 (multi-event) | 5 each | same budgets |
| Generalization | E0 (single event) | 5 | evaluated on all val/test events |
| Reference policies | B0, B1, B2 | deterministic (1) | cached via `BaselineStore` |
| Sensitivity | IETD 3/12 h; min event depth; `selection` rule | 3 (M0 only) | |
| Grouped CV *(optional)* | M0 across 5 year-folds | 3 | |
| O1 / P1 *(optional)* | hindsight search / other RL | 1–3 | |

**Compute estimate:** 5 methods × 5 seeds + E0 × 5 = **30 training runs**, each ~2–4 h CPU (unchanged). Run **one process per seed/method** (SWMM is not thread-safe within a process): on 8 cores ≈ 4 rounds ≈ 8–16 h wall time. Evaluation per run is small compared with training.

### 7.3 Budget parity and tuning policy
- Same episodes, warm-up, update ratio, buffer, hyperparameters for every learned variant.
- Trial 7 hyperparameters were tuned on a single storm; keep them frozen. State it as a limitation, and optionally run a small validation-only sensitivity study on learning rate/entropy for M0 **and** M1 (equal effort).

### 7.4 Training/evaluation commands (illustrative)
```bash
python -m research.build_real_storms --config configs/data.json
python -m research.unit_audit
python -m multistorm.audit --rain-dir rain_real --split-manifest splits.json --real-only
for s in 0 1 2 3 4; do
  python -m multistorm.train_multi --rain-dir rain_real --split-manifest splits.json --real-only \
         --scaling none --variant m0 --seed $s --run-name m0_s$s &
done; wait
python -m research.compare_methods --runs runs/m0_s* runs/m1_s* runs/a1_s* runs/a2_s* runs/a3_s* runs/e0_s*
```

---

## 8. Stress and robustness tests (optional, standard in RTC studies)

These perturb **observations/actuators**, never the rainfall, so rainfall stays real.

| Test | Perturbation | Report |
|------|--------------|--------|
| Sensor noise | multiplicative Gaussian noise on depth/flow observations (σ = 2%, 5%, 10%) | CSO reduction vs noise level, M0 vs M1 vs B0 |
| Sensor dropout | randomly hold last value for k steps | same |
| Actuator fault | one diverting gate stuck at its initial setting | same |
| Rainfall timing shift | none (not applied; would alter DWF alignment) | — |

Implement as wrappers in `evaluate()`: `obs_noise_sigma`, `dropout_prob`, `stuck_gate`. The policy sees the perturbed observation; the KB projection uses true state (state this in the paper) or perturbed state (run both).

---

## 9. Reproducibility package

```text
neuro/
├── README.md                    # one-command reproduction, expected runtime
├── LICENSE                      # code license; data licence notes in docs/DATA.md
├── environment.yml / requirements.lock
├── Makefile                     # make data | audit | train | eval | report | paper
├── configs/{data.json, protocol.json}
├── docs/{protocol.md, DATA.md, model_card.md}
├── data/raw/ …                  # standardized series + raw_manifest.json
├── rain_real/ …                 # events + data_manifest.json + events_rejected.csv
├── research/                    # acquisition, events, splits, guard, unit_audit, compare_methods
├── multistorm/                  # pipeline from the previous guide
├── tests/                       # golden, storms, events, stats, guard, unit tests
├── runs/ …                      # per-run configs, logs, checkpoints, final_eval.csv
└── paper/{figures/, tables/, main.tex}
```

Checklist:
- [ ] Every run stores `run_config.json`, git commit hash, library versions, seed, storm manifest hash.
- [ ] Data: NOAA data are US-government products; cite the dataset as the catalog requires. **Check permission to publish the SWMM INP** (utility/consultant models are often restricted); if not shareable, publish the event data, code, and a synthetic-free description of the model.
- [ ] Archive a release with a DOI (e.g. Zenodo), including checkpoints of the headline models.
- [ ] CI runs `pytest` (golden test, events tests, stats tests) on every commit.
- [ ] `make paper` regenerates all tables/figures from `runs/*/final_eval.csv` only.

---

## 10. Reporting plan

### 10.1 Tables
| # | Content |
|---|---------|
| T1 | Dataset: gauges, years, number of events, per-split counts, severity class distribution, depth/intensity summary, rejected-event reasons |
| T2 | **Main results** (test events): per method: CSO volume reduction (mean, IQM, 95% CI, worst case), CSO event count, capture ratio, flood ratio, R6 excess, intervention rate |
| T3 | Ablations (same columns) |
| T4 | Paired tests: effect sizes, Holm-adjusted p-values (M0 vs B0, B1, B2, M1, E0; ablations vs M0) |
| T5 | Robustness (noise/dropout/fault) |
| T6 | Compute and latency |

### 10.2 Figures
| # | Content |
|---|---------|
| F1 | System diagram: SWMM network, controlled gates, CSO outlets, neurosymbolic layers |
| F2 | Event dataset overview (depth vs peak intensity, ARI classes, splits) |
| F3 | Per-event CSO reduction on test events (paired dots/bars with CIs) |
| F4 | Reduction vs storm severity (ARI/total depth), with out-of-range events marked |
| F5 | Learning curves with seed bands; validation reduction and flood ratio vs episode |
| F6 | Performance profiles |
| F7 | Example hydrographs: gates, storage fill, CSO for one test event (B0 vs B1 vs M0) |
| F8 | Intervention rate and rule activations (R1/R2/R6) by severity |
| F9 | Robustness curves |

### 10.3 Paper outline
1. **Introduction** — CSO problem; RTC; RL promise and safety concerns; gap: generalization to observed storms and value of symbolic knowledge.
2. **Related work** — RL for urban drainage/RTC; safe RL / shielding / neurosymbolic RL; benchmarking practice (statistical rigor in RL).
3. **Study system and data** — network, SWMM model, real rainfall, event extraction, split.
4. **Method** — SAC, predicates, projection, shaping (as in Trial 7); training protocol.
5. **Evaluation protocol** — baselines, ablations, metrics, statistics.
6. **Results** — main, generalization, ablations, severity, robustness.
7. **Discussion** — when symbolic knowledge helps; failure cases; deployment considerations.
8. **Limitations** — see 10.4.
9. **Conclusion; data/code availability.**

Common venues (check scope, current formatting and policies yourself): Journal of Hydroinformatics, Water Research, Environmental Modelling & Software, ASCE Journal of Water Resources Planning and Management, Water Resources Research; for the ML side, climate/sustainability workshops at major ML conferences.

### 10.4 Threats to validity (write these honestly)
- **Digital twin, not the field:** results are in a SWMM model that was not recalibrated here; no field deployment.
- **Single network, single control interval**, one gauge per event (no areal rainfall).
- **Fixed 72-h window and 2018 DWF/initial conditions** for all events.
- **Hyperparameters tuned on one synthetic-or-unknown storm** (Trial 7); frozen thereafter.
- **R6/predicate thresholds** may be mis-scaled for real events (Section 3.1).
- **Small number of test events** → wide CIs; temporal split reflects one climate period.
- **KB uses true state** in simulation; real sensors are noisy (Section 8 partly addresses this).
- **Pumps frozen ON**; only seven gates are learned.
- **Selection effects:** events kept only if QC-clean and ≥ minimum depth; report rejected-event reasons.

---

## 11. Vibe-coding stages 10–19

Use the same system preamble as the previous guide, **plus**:

```text
ADDITIONAL RULES FOR THE RESEARCH PHASE:
- No synthetic, augmented, or rescaled rainfall in any reported run. scaling must be "none". Real-only guard on.
- No change to SAC hyperparameters, reward weights, predicates, or projection rules unless a stage explicitly
  adds an ablation flag whose default reproduces Trial 7 (tests/test_golden.py must still pass).
- Every number in a paper table must be reproducible from runs/*/final_eval.csv by a script.
- Never read the test split inside training, tuning, or selection code paths.
- Ask before guessing: if an official data/documentation detail is ambiguous, stop and report.
```

| Stage | Deliverable | Acceptance |
|-------|-------------|------------|
| 10 | `research/acquire_ncei.py`, standardized series, raw manifest, coverage report | coverage reviewed; explicit-zero vs NaN rule verified on a sample day |
| 11 | `events.py`, `build_real_storms.py`, tests, `rain_real/` + manifest | tests pass; rejected-events ledger present |
| 12 | `unit_audit.py` + `rain_to_gage_value()` | physical depth within 2% for the chosen convention; decision recorded in `docs/DATA.md` |
| 13 | `splits.py` (+ `splits.json`), `guard.py`, `--real-only` in train/audit | guard raises on a deliberately modified file; split counts ≥ 3 each |
| 14 | Ablation flags (`use_projection`, `use_predicates`, `reward_terms`), `policies.py`, `--variant {m0,m1,a1,a2,a3,e0}` | golden test passes with defaults; each variant prints its effective config |
| 15 | `metrics_ext.py` merged into `evaluate()`; `BaselineStore` stores extended summaries | volume equals sum(flow)·900·0.0283168; event counts verified on a synthetic log |
| 16 | `stats.py` + tests | bootstrap CI covers a known mean in simulation; Holm matches a hand example |
| 17 | `research/compare_methods.py`: build (seed × event) tensors, T2–T4 as CSV and LaTeX, F3/F4/F6 figures | regenerates identical tables from CSVs |
| 18 | Stress-test wrappers + T5/F9 | σ = 0 reproduces baseline numbers exactly |
| 19 | Packaging: README, Makefile, environment lock, `docs/protocol.md`, CI, release tag | clean-clone `make report` works |

**Prompt for Stage 17 (example of the level of detail to give):**
```text
Create research/compare_methods.py. Inputs: run directories named <method>_s<seed> containing final_eval.csv
(phase "final", deterministic). For each metric in configs/protocol.json and each split (val, test),
build an array (n_seeds, n_events) per method with events aligned by storm_id (error if events differ).
Outputs in paper/tables and paper/figures:
 - T2: per method mean, IQM, 95% hierarchical-bootstrap CI (multistorm/stats.py), worst case, n_events.
 - T4: paired_compare of every comparison listed in configs/protocol.json with Holm-adjusted p-values.
 - F3 per-event reduction (test), F4 reduction vs total depth and ARI class (mark out-of-range events),
   F6 performance profiles.
Events with undefined reduction (baseline CSO below the floor) are excluded from reduction statistics but
included in flood/safety statistics, and counted in the table footnote.
Write LaTeX tables with booktabs and a CSV twin for each table.
```

---

## 12. Suggested timeline (single researcher, indicative)

| Weeks | Work package |
|-------|--------------|
| 1 | WP0: unit audit, baseline plausibility, gauge/data decisions, protocol draft |
| 2–3 | Data acquisition, event extraction, splits, guard (Stages 10–13) |
| 3–4 | Ablation flags, extended metrics, stats code (Stages 14–16); smoke tests |
| 4–6 | Freeze protocol; run main matrix (30 runs), sensitivity, optional CV |
| 6–7 | Stress tests, comparison tables/figures (Stages 17–18) |
| 7–9 | Writing, internal review, packaging/release (Stage 19) |

---

## 13. Final go/no-go checklist before writing the paper

- [ ] All storms observed, unscaled, hash-verified; manifest and rejected-events ledger published.
- [ ] Unit audit documented; any Trial 7 unit issue disclosed and handled by a pre-registered change.
- [ ] Protocol committed and tagged before any test-set run.
- [ ] Test events never used for selection or tuning (code-path audit done).
- [ ] ≥ 5 seeds per learned method; hierarchical bootstrap CIs and Holm-adjusted paired tests reported.
- [ ] Safety metrics (flooding ratio, R6 excess, intervention rate) reported alongside CSO reduction.
- [ ] Negative results and failure cases (storms where the agent is worse than the baseline) shown.
- [ ] Limitations section covers digital-twin scope, single network, event count, threshold scaling.
- [ ] A reviewer can reproduce the headline table from a clean clone.

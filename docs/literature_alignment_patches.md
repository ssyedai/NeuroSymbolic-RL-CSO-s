# Literature-alignment patches (companion to the analysis)

Everything here is either (a) validation tooling, (b) a bug fix in the event pipeline, or (c) a clearly flagged *optional* change. Nothing changes SAC hyperparameters, the KB predicates, the projection rules or the INP.

---

## 1. Severity classification from the Detroit IDF (replaces the empty ARI columns)

The Detroit local IDF used in Yin et al. (2023, 2024) is
`i [in/h] = 38.4164 · T^0.2082 / (12.3258 + D)^0.8405`, with T in years and D in minutes.
The authors state it corresponds to NOAA Atlas 14 through the Detroit stormwater manual. It is a single fitted curve, so treat the class as approximate and say so.

```python
# research/idf.py
import numpy as np, pandas as pd

def idf_i(T, D):                    # in/h
    return 38.4164 * T**0.2082 / (12.3258 + D)**0.8405

def idf_depth_mm(T, D):
    return idf_i(T, D) * D / 60.0 * 25.4

def t_eq(depth_mm, D):              # equivalent return period of a depth over duration D (min)
    i = np.asarray(depth_mm, float) / 25.4 * 60.0 / D
    return (i * (12.3258 + D) ** 0.8405 / 38.4164) ** (1 / 0.2082)

DUR = {60: "max1h_mm", 180: "max3h_mm", 360: "max6h_mm", 1440: "max24h_mm"}   # >= 1 h only (robust to 15-min spikes)

def classify(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.copy()
    for D, c in DUR.items():
        ev[f"T{D}"] = t_eq(ev[c].clip(lower=1e-6), D)
    ev["T_eq"] = ev[[f"T{D}" for D in DUR]].max(axis=1)
    ev["T_eq_15min"] = t_eq(ev["max15_mm"].clip(lower=1e-6), 15)
    # spike flag: one 15-min bucket carries most of the event depth (possible accumulation/QC artefact)
    ev["spike_flag"] = (ev["max15_mm"] / ev["total_mm"] > 0.75) & (ev["total_mm"] > 20)
    ev["severity"] = pd.cut(ev["T_eq"], [0, 1, 2, 5, 10, 25, np.inf],
                            labels=["<1", "1-2", "2-5", "5-10", "10-25", ">=25"])
    return ev
```
Use it in `build_real_storms.py` instead of the depth-bin `severity_class`, and drop `ari_*` columns that need a PFDS file.

Resulting IDF reference depths (mm) for checking: 24 h = 51.5 (1 yr), 72.0 (5 yr), 83.2 (10 yr), 100.7 (25 yr), 116.3 (50 yr); 1 h = 26.7 (1 yr), 37.3 (5 yr), 52.2 (25 yr).

---

## 2. Event detector bug: missing data is silently treated as dry

In `events.py`, `detect_events` does `np.nan_to_num(p, nan=0)`, so an event that falls inside a data gap is never detected, never logged, and never appears in `events_rejected.csv`. Replace with:

```python
def detect_events(p: pd.Series, ietd_h=6.0, min_depth_mm=6.35):
    a = p.to_numpy(float)
    unk = np.isnan(a)
    wet = np.flatnonzero(~unk & (a > 0))
    if wet.size == 0:
        return []
    gap = int(ietd_h * 4)
    spans, start, last, uncertain = [], wet[0], wet[0], False
    for j in wet[1:]:
        between = slice(last + 1, j)
        if unk[between].any():                      # cannot certify dryness -> keep in same event, flag it
            uncertain = True
        elif j - last - 1 >= gap:
            spans.append((start, last, uncertain)); start, uncertain = j, False
        last = j
    spans.append((start, last, uncertain))
    out = []
    for s, e, u in spans:
        d = float(np.nansum(a[s:e + 1]))
        if d >= min_depth_mm:
            out.append(dict(start=p.index[s], end=p.index[e], i0=s, i1=e, depth_mm=d, uncertain=u))
    return out


def missing_runs(p: pd.Series, min_hours=6.0) -> pd.DataFrame:
    """Gaps long enough to hide an event; write to rain_real/missing_runs.csv."""
    m = p.isna().to_numpy()
    runs, i = [], 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            if (j - i) * 0.25 >= min_hours:
                runs.append(dict(start=p.index[i], end=p.index[j - 1], hours=(j - i) * 0.25))
            i = j
        else:
            i += 1
    return pd.DataFrame(runs)


def check_dates(p: pd.Series, dates, pad_days=2):
    """Coverage and rain totals around known events (e.g. the 2018-09-12 and 2019-08-07 events in Yin et al. 2024)."""
    for d in dates:
        t = pd.Timestamp(d)
        w = p[t - pd.Timedelta(days=pad_days): t + pd.Timedelta(days=pad_days + 1)]
        print(d, "valid frac %.2f" % w.notna().mean(), "total mm %.1f" % w.sum(), "max15 %.1f" % w.max())
```

---

## 3. Anchor events and design storms (validation only, never mixed into "real" results)

### 3a. Anchor events from the published Detroit study
Yin et al. (2024) tested on real PFSMC events starting **2018-09-12** and **2019-08-07**, and report total CSO volumes between 0 and about 90,000 m³ across 50 random gate settings. Run `check_dates` for both dates on your standardized series:
- If the gauge shows heavy rain, the events were lost by the bug above (fix and rerun).
- If the gauge shows valid data and little rain, `USC00200230` does not see the rain that stressed the published model. You need a gauge nearer the catchment (utility record).

With the rainfall for those two events, run your pipeline (INP unchanged, **random uniform gate settings 0 to 1**, as in the paper). CSO volumes on the order of 10⁴ m³ for the September 2018 event would support your rain injection and units; zero would not.

### 3b. Design-storm validation (labelled synthetic; used only to check the model)
Yin et al. (2023) simulate 5, 10, 15, 20 and 25-year 24-h storms and report CSO under the native rule-based control in every case. A rough check on your pipeline: alternating-block hyetographs from the same IDF should give CSO under native control from about 5 years up (not identical to NRCS MSE3, so only the onset and the trend are comparable).

```python
# research/design_storm.py  (VALIDATION ONLY)
import numpy as np
from research.idf import idf_depth_mm

def alternating_block(T, dur_h=24, dt_min=15, peak_frac=0.5, n_steps=288, start_h=12):
    D = np.arange(dt_min, dur_h * 60 + 1, dt_min)
    cum = idf_depth_mm(T, D)
    inc = np.diff(np.r_[0.0, cum])                       # descending increments
    n = len(inc)
    order = np.empty(n)
    pos = int(peak_frac * n)
    left, right = pos - 1, pos + 1
    seq = [pos]
    for k in range(1, n):                                # alternate right, left around the peak
        if k % 2 == 1 and right < n: seq.append(right); right += 1
        elif left >= 0: seq.append(left); left -= 1
        else: seq.append(right); right += 1
    hyet = np.zeros(n)
    for k, idx in enumerate(seq[:n]):
        hyet[idx] = inc[k]
    full = np.zeros(n_steps)
    s = int(start_h * 4)
    full[s:s + n] = hyet[: n_steps - s]
    return full                                          # mm per 15 min
```
Anything built this way goes in `rain_design_validation/`, not `rain_real_*`, and the real-only guard must keep refusing it.

### 3c. Dose-response (from the earlier diagnostic)
Scale one extreme real event by k in {1, 2, 4, 6.35, 10, 25.4}. If CSO first appears near k = 6.35, your earlier Trial 7 regime was the inflated one (6.35 = 25.4 / 4).

---

## 4. Baseline: make the native rule-based control primary

The literature compares against the model's existing rule-based (passive) control. In `metrics.relative()` and the report, treat the **native-controls run as the primary reference** and the static 0.5 policy as secondary:

```python
def relative(s, rec, cso_floor=1.0, ref="native"):
    b = rec["native"] if (ref == "native" and rec.get("native")) else rec["static"]
    ...
```
Keep the static 0.5 baseline for the `baseline_flooding` calibration and for the shaped-score reference, but report % reductions against native.

---

## 5. Optional reward additions (a change to the model config: pre-register as an ablation, not the default)

Yin et al. (2023) use a dense safety signal: node depth margin against a limit 2 ft below the maximum allowable depth, summed over key nodes, plus weir flow. Your flooding term is sparse and baseline-relative (zero whenever nothing floods). A dense variant for an ablation:

```python
# r_depth = - w_depth * sum_i max(depth_i - (Dmax_i - 2.0 ft), 0) / Dmax_i       (ft units, SWMM US customary)
```
Add as `reward_terms=("close","cso","flood","depth")`. Default stays Trial 7.

---

## 6. Algorithm comparator

On this same network the 2023 study ranked DDPG > SAC > A2C > PPO (single design storm). Add DDPG as a comparator with the same actor/critic sizes and the same `select_action(obs, deterministic)` interface, run with ≥5 seeds, and let the multi-event results decide whether that ranking holds.

---

## 7. Hybrid training sets (decision for you, flagged)

Both Detroit studies and several others mix design storms into training because real events rarely cause CSO. If you keep **evaluation strictly on real events** but add design storms (Detroit IDF, several return periods, durations and shapes) **to training only**, label the training data as synthetic in `data_manifest.json` (`provenance: "design"`), disable the real-only guard only for the training split, and report three training variants side by side: real-only, design-only, hybrid. The primary claim stays on real held-out events.

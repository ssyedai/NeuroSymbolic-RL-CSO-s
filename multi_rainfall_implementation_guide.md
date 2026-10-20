# Multi-Rainfall Training & Evaluation — Implementation Guide
**Project:** Neurosymbolic SAC for SWMM CSO control (Trial 7 / v7, `7MPF_CSO_08`)
**Goal:** Train and evaluate on *many* rainfall series (same 15-min interval) with the **same physical model, same SAC, same KB, same reward**. Only the data/experiment pipeline changes.

> **Important caveat.** This guide is written from `methodology.md` only. I have **not** seen `app.py`. Class and function names used below (`NeurosymbolicSWMMEnv`, `SymbolicKnowledgeBase`, `SACAgent`, `run_baseline_episode`, `NODE_FULL_DEPTHS`, ...) come from the methodology. Your coding assistant must read `app.py` first and adapt the thin `adapters.py` layer (Section 5) to the real signatures. If you upload `app.py`, I can turn Stage 3 into exact patches.

---

## 0. What to download / gather

| # | File | Why you need it | Where it goes |
|---|------|-----------------|---------------|
| 1 | `app.py` | Trial 7 production code (env, KB, SAC, baseline run). **Single most important file.** | project root |
| 2 | `7MPF_CSO_08.inp` | SWMM network (unchanged) | project root |
| 3 | `raindata (1).csv` → rename `raindata.csv` | Trial 7 storm (becomes storm #1) | `rain/` |
| 4 | `randomrainfall (1).xlsx` | Already a second storm from earlier trials (storm #2) | `rain/` |
| 5 | `test_rainfall_0.01_1.csv` (legacy, if you still have it) | Possible third storm | `rain/` |
| 6 | `methodology.md` | Give to the coding assistant as context | project root |
| 7 | *(optional)* `PySWAIMM_project.ipynb`, `Pyswmm_environment.txt` | Only if `app.py` is missing something | reference |
| 8 | **New storms** (you must source these) | Needed for real generalization; **aim for 8–20 storms** | `rain/` |

**Where to get more storms (pick a mix):**
- Design storms (SCS/NRCS Type II, Chicago method) at several return periods from NOAA Atlas 14 depths for your location.
- Observed 15-min gauge records (e.g. NOAA NCEI 15-minute precipitation data) cut into 72 h windows around real events.
- Synthetic hyetographs: vary peak position, duration, number of bursts, and total depth. (`randomrainfall.xlsx` looks like this style.)
- Make sure you include **mild, medium, severe** storms, and at least one that produces little or no CSO.

**File format accepted by the loader (Stage 2):**
- `.csv` / `.xlsx`, **no header** (a header row is auto-skipped), one rainfall value per row, 15-min interval.
- Optional timestamp column is ignored automatically.
- Multiple columns in one file = multiple storms.
- Target length is **288 rows** (72 h). Shorter → zero-padded; longer → truncated (both logged loudly).

**Python packages**
```bash
pip install pyswmm swmm-toolkit gymnasium torch numpy pandas matplotlib openpyxl pytest
```

---

## 1. Analysis of the current methodology (what breaks with multiple storms)

Trial 7 is a clean single-storm design. Below is every place where "one storm" is silently baked in. Each one is a bug (or a misleading result) the moment you add a second storm.

| # | Issue in Trial 7 | Why it matters for multi-storm | Fix in this guide |
|---|------------------|--------------------------------|-------------------|
| 1 | `rainfall_series` is a module-level global; env step reads `rainfall_series[t]` | Cannot change storm per episode | Env takes the storm at `reset(options=...)` |
| 2 | `BASELINE_FLOODING = 7183.0` hardcoded, derived from *one* storm | `r_flood = -W·max(flood − baseline, 0)` becomes meaningless: on a big storm it is permanently penalized, on a small one it is never active | **Per-storm baseline**, calibrated once and cached |
| 3 | Every storm is rescaled to peak = 24 | Erases severity differences between storms; "mild" and "severe" become the same peak | Scaling mode is configurable; default `peak` (Trial 7 compatible) plus optional intensity augmentation |
| 4 | `FLOODING_THRESHOLD = 9500` (≈132% of the one baseline) feeds R6 and predicate `flooding_severe` | If a storm's baseline already exceeds ~9500, R6 fires all episode and overrides the policy (all gates = 1.0). If baseline is far below, R6 never fires | Keep 9500 (KB frozen) but **audit R6 pressure per storm** and warn. Optional relative-threshold ablation |
| 5 | Episode score is compared across episodes | Returns across different storms are not comparable (different rain volume) | Report **relative metrics vs a per-storm reference policy** (% CSO reduction, score advantage) |
| 6 | "Best model" = best *training* score | With a storm mix, a lucky easy storm wins; also no generalization signal | Model selection on **held-out validation storms**, deterministic policy |
| 7 | No train/val/test concept | Cannot claim generalization | Storm-level splits, fixed manifest, extrapolation guard |
| 8 | Training episodes use stochastic SAC actions; evaluation never separated | Noisy, non-reproducible comparisons | Separate **deterministic evaluation harness** (no updates, no replay writes) |
| 9 | Metrics are aggregated as one number per episode | Averages hide failures on specific storms | Per-storm tables, macro/micro averages, worst-case, % storms improved, flood-regression rate |
| 10 | Replay buffer 50k ≈ 175 episodes, random storm order not controlled | Buffer can be dominated by whatever storms were sampled recently | **Balanced shuffled-cycle sampler** (each storm once per cycle); log buffer composition |
| 11 | Rainfall length assumed exactly 288 | Other files will have other lengths | Explicit length policy (pad/truncate/error) + validation |
| 12 | The INP `[CONTROLS]` rules are bypassed; no "status quo" reference | Cannot say how much better the agent is than the real system | Add **native-controls reference run** per storm |
| 13 | No seeds / run manifest | Results not reproducible | Seeds, `run_config.json`, `storm_manifest.json`, data hashes |
| 14 | Obs contains only *current* subcatchment rain; no forecast | Policy cannot anticipate a storm it hasn't "memorized" — single-storm training lets it memorize the time index | Not changed (would change the model config). Multi-storm training is the mitigation; mention as limitation |
| 15 | Notes say baseline must be re-run when gate defaults change | Cached baselines can go stale | Cache key includes INP hash + storm hash + version tag |

### What stays frozen (do not touch)
SAC hyperparameters, network (256, LayerNorm), lr `1e-4`, γ `0.99`, τ `0.005`, batch `256`, buffer `50,000`, target entropy `-7.0`, grad clip `0.5`, update every 4 steps, warm-up 2000 random steps, 1000 episodes (default), the 10-D action / observation layout, 11 predicates, projection rules R1/R2/R6/pumps, reward terms and weights (10 / 3 / 5, S=1000), 15-min control step, 288-step episode, the INP file.

### What is allowed to change
Where the rainfall comes from, how baselines are computed, how episodes are sampled, how models are selected, how results are evaluated/logged/plotted.

---

## 2. Design decisions (defaults, with reasons)

| Decision | Default | Alternative | Note |
|----------|---------|-------------|------|
| Scaling | `peak` (peak→24, Trial 7) | `none` (raw mm/h) | If your new files are real intensities, `none` keeps severity diversity. Run both as an experiment |
| Length policy | `pad_or_truncate` | `error` | Padding = dry tail |
| Split | seeded random, stratified guard, or explicit manifest | leave-one-out | With < 10 storms **write the manifest by hand** |
| Sampler | `shuffled_cycle` | `uniform` | Balanced exposure |
| Baseline flooding | per storm | fixed 7183 (ablation) | Per-storm is required for correctness |
| R6 threshold | fixed 9500 (KB unchanged) | 1.32 × per-storm baseline | Ablation only; changes KB semantics |
| Reference policies | static 0.5 gates + pumps ON, and SWMM native controls | + KB-only rules | Needed for relative metrics |
| Eval policy | deterministic (mean action) | stochastic | Deterministic for selection and reports |
| Model selection | val macro CSO-reduction %, subject to safety caps | train score | Held-out |
| Seeds | 1 for dev, **≥3 for final** | — | ~2–4 h CPU per run |
| Episodes | 1000 (unchanged) | 1500–2000 for N ≥ 8 storms | Optional: each storm gets 1000/N visits |

---

## 3. Target folder layout

```text
neuro/
├── app.py                      # logic unchanged; add `if __name__ == "__main__":` guard
├── 7MPF_CSO_08.inp
├── methodology.md
├── rain/                       # ALL rainfall files
│   ├── raindata.csv
│   ├── randomrainfall.xlsx
│   └── ...
├── splits.json                 # optional manual split manifest
├── multistorm/
│   ├── __init__.py
│   ├── config.py               # dataclass + argparse
│   ├── storms.py               # load / validate / scale / split / sampler / augment
│   ├── adapters.py             # THIN bridge to app.py (only file that imports app)
│   ├── metrics.py              # episode_summary, relative(), aggregate(), selection_score()
│   ├── baselines.py            # per-storm cached reference runs
│   ├── evaluate.py             # deterministic eval harness
│   ├── audit.py                # pre-flight storm audit CLI
│   ├── train_multi.py          # multi-storm training entry point
│   ├── report.py               # tables + plots for one run
│   └── compare.py              # aggregate several seeds / experiments
├── tests/
│   ├── test_golden.py          # Trial 7 regression
│   ├── test_storms.py
│   └── golden_trial7.npz       # created in Stage 0, BEFORE any edits
└── runs/<run_name>/            # outputs (created automatically)
    ├── run_config.json
    ├── storm_manifest.json
    ├── train_log.csv
    ├── eval_log.csv
    ├── final_eval.csv
    ├── final_agg.json
    ├── checkpoints/{best_val.pt, ep100.pt, final.pt}
    └── figures/*.png, REPORT.md
```

---

## 4. Vibe-coding workflow (how to use this guide)

1. Create the folder layout, copy files from Section 0.
2. Open the folder in your AI coding tool (Cursor / Claude Code / Copilot / etc.).
3. Start every session with this **system preamble**:

```text
You are modifying an existing research codebase (Trial 7 neurosymbolic SAC for SWMM).
Read methodology.md and app.py fully before editing anything.
HARD RULES:
- Do NOT change: SAC hyperparameters, network architecture, observation/action layout,
  the 11 predicates, projection rules (pumps, R1/R2/R6), reward terms/weights, the INP file,
  control step (900 s), episode length (288), warm-up steps, update frequency, buffer size.
- With a single storm (raindata.csv) and baseline_flooding=7183, new code must reproduce
  Trial 7 numerically (tests/test_golden.py must pass).
- Remove reliance on module-level mutable globals for rainfall and BASELINE_FLOODING.
- Keep all app.py imports confined to multistorm/adapters.py.
- Small, reviewable diffs. Run tests after every stage. Do not refactor unrelated code.
```

4. Paste the stage prompts below **one at a time**. Do not move on until the acceptance checks pass.

---

## 5. The adapter contract (`multistorm/adapters.py`)

Everything else in `multistorm/` is pure Python (numpy/pandas) and does not import `app.py`. `adapters.py` is the only bridge. The coding assistant must implement these against the real `app.py`:

| Function / method | Behavior |
|-------------------|----------|
| `build(seed) -> (env, agent, kb)` | Construct exactly what Trial 7 constructs. Seed numpy/torch/random |
| `env.reset(seed=None, options=None)` | `options["storm"]` (a `Storm`) sets the rainfall for this episode; `options["baseline_flooding"]` sets KB baseline; `options["native"]=True` enables native-controls mode (no target-setting writes, no projection). Missing options → legacy behavior |
| `env.get_episode_log() -> dict` | Per-step arrays: `cso_flow`, `flooding`, `storage_fill`, `actions_projected` (T×10), `reward`, `r_close`, `r_cso`, `r_flood` |
| `train_one_episode(env, agent, storm, baseline_flooding, global_step, warmup_steps, update_every) -> (log, global_step)` | **Verbatim extraction of Trial 7's per-episode training loop**, plus the `reset(options=...)` call. No logic changes |
| `agent.select_action(obs, deterministic=False)` | `deterministic=True` returns `tanh(mean)` mapped to [0,1], no sampling, under `torch.no_grad()` |
| `agent.alpha_value() -> float` | For logging |
| `agent.save(path, extra: dict)` / `agent.load(path)` | Model + optimizers + log-alpha (+ `extra`) |
| `run_baseline_episode_for(storm) -> float` | Wraps existing `run_baseline_episode(storm.depth)`; returns the same quantity as `BASELINE_FLOODING` (mean flood volume rate per step) |

---

## Stage 0 — Freeze Trial 7 behavior (golden test) — do this BEFORE editing

**Prompt:**
```text
Without modifying app.py, write a script that:
1) seeds numpy/torch/random with 0,
2) builds the Trial 7 env exactly as app.py does with raindata.csv scaled as in Block 1,
3) runs 30 control steps with a fixed action sequence (rng seed 123, uniform[0,1], shape (30,10)),
4) saves per-step reward, cso_flow, flooding, projected actions, observation[:50] to tests/golden_trial7.npz.
Also write tests/test_golden.py that loads this file and (for now) re-runs the same procedure
and asserts np.allclose(atol=1e-6).
```
**Accept:** `pytest tests/test_golden.py` passes; `golden_trial7.npz` exists and is committed.

---

## Stage 1 — Make `app.py` importable (no logic change)

**Prompt:**
```text
In app.py, wrap all top-level training/execution code (training loop, plotting, evaluation prints)
in `def main():` and add `if __name__ == "__main__": main()`. Keep class/function bodies and constants
identical. Heavy side effects at import time (opening simulations, loading files, training) must not run on import.
Confirm `python -c "import app"` is instant and test_golden still passes.
```
**Accept:** import is side-effect free; golden test passes.

---

## Stage 2 — `storms.py` (loader, validation, scaling, splits, sampler)

**Prompt:**
```text
Create multistorm/storms.py exactly as specified in the code block below (adapt only if a test fails).
Then create tests/test_storms.py covering: header-row skipping, datetime-column skipping,
multi-column files, padding/truncation, NaN/negative rejection, dry-storm rejection,
Trial 7 scaling equivalence on raindata.csv (peak=24, depth=intensity*900/3600, total≈114 mm),
split determinism for a fixed seed, extrapolation guard, and sampler coverage (each storm exactly once per cycle).
```

```python
# multistorm/storms.py
"""Load, validate, preprocess, split and sample rainfall storms. No SWMM imports."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("storms")

CONTROL_DT_S = 900
N_STEPS = 288
PEAK_TARGET = 24.0


@dataclass(frozen=True, eq=False)
class Storm:
    storm_id: str
    source: str
    intensity: np.ndarray           # mm/h after scaling, len N_STEPS
    depth: np.ndarray               # mm per control interval, len N_STEPS
    split: str = "train"
    meta: dict = field(default_factory=dict)

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.depth.astype(np.float64).tobytes()).hexdigest()[:12]

    def with_split(self, split: str) -> "Storm":
        return Storm(self.storm_id, self.source, self.intensity, self.depth, split, self.meta)


# ---------------------------------------------------------------- loading
def _read_table(path: Path) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf == ".csv":
        df = pd.read_csv(path, header=None, skip_blank_lines=True)
    elif suf in (".xlsx", ".xls"):
        df = pd.read_excel(path, header=None)
    else:
        raise ValueError(f"Unsupported rainfall file type: {path}")
    keep = [c for c in df.columns if not pd.api.types.is_datetime64_any_dtype(df[c])]
    df = df[keep].apply(pd.to_numeric, errors="coerce")
    return df.dropna(axis=1, how="all").dropna(axis=0, how="all").reset_index(drop=True)


def _fit_length(x: np.ndarray, sid: str, policy: str) -> np.ndarray:
    n = len(x)
    if n == N_STEPS:
        return x
    if n < N_STEPS and policy in ("pad", "pad_or_truncate"):
        log.warning("%s: %d rows < %d, zero-padding dry tail", sid, n, N_STEPS)
        return np.pad(x, (0, N_STEPS - n))
    if n > N_STEPS and policy in ("truncate", "pad_or_truncate"):
        log.warning("%s: %d rows > %d, truncating (dropping %.2f units of rain)",
                    sid, n, N_STEPS, float(x[N_STEPS:].sum()))
        return x[:N_STEPS]
    raise ValueError(f"{sid}: has {n} rows, expected {N_STEPS} (policy={policy})")


def make_storm(raw, storm_id, source, scaling="peak", peak_target=PEAK_TARGET,
               length_policy="pad_or_truncate") -> Storm:
    x = _fit_length(np.asarray(raw, dtype=float), storm_id, length_policy)
    if np.isnan(x).any():
        raise ValueError(f"{storm_id}: contains NaN")
    if (x < 0).any():
        raise ValueError(f"{storm_id}: contains negative rainfall")
    peak = float(x.max())
    if peak <= 0:
        raise ValueError(f"{storm_id}: dry storm (peak == 0)")
    if scaling == "peak":
        intensity = x * (peak_target / peak)           # Trial 7 preprocessing
    elif scaling == "none":
        intensity = x.copy()                           # raw values assumed mm/h
    else:
        raise ValueError(f"unknown scaling {scaling}")
    depth = intensity * (CONTROL_DT_S / 3600.0)        # mm per 15 min
    return Storm(storm_id, source, intensity, depth,
                 meta={"raw_peak": peak, "scaling": scaling})


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_")


def load_storms(rain_dir, scaling="peak", peak_target=PEAK_TARGET,
                length_policy="pad_or_truncate") -> list[Storm]:
    rain_dir = Path(rain_dir)
    files = sorted(p for p in rain_dir.iterdir()
                   if p.suffix.lower() in (".csv", ".xlsx", ".xls"))
    if not files:
        raise FileNotFoundError(f"No rainfall files in {rain_dir}")
    storms: list[Storm] = []
    for p in files:
        df = _read_table(p)
        for k, col in enumerate(df.columns):
            s = df[col]
            s = s.iloc[: s.last_valid_index() + 1]            # strip trailing NaN
            sid = _slug(p.stem) if df.shape[1] == 1 else f"{_slug(p.stem)}_c{k}"
            storms.append(make_storm(s.to_numpy(), sid, str(p), scaling, peak_target, length_policy))
    ids = [s.storm_id for s in storms]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate storm ids; rename files")
    shas = {}
    for s in storms:
        if s.sha in shas:
            log.warning("Storms %s and %s are identical after preprocessing", s.storm_id, shas[s.sha])
        shas[s.sha] = s.storm_id
    return storms


# ---------------------------------------------------------------- splits
def assign_splits(storms, seed=0, manifest_path=None, val_frac=0.15, test_frac=0.15,
                  extrapolation_guard=True):
    """Return (storms_with_splits, info). Splits are by STORM, never by timestep."""
    ids = [s.storm_id for s in storms]
    info = {"selection_on_train": False}
    if manifest_path and Path(manifest_path).exists():
        m = json.loads(Path(manifest_path).read_text())
        missing = [i for i in ids if i not in m]
        if missing:
            raise ValueError(f"Storms missing from split manifest: {missing}")
        info["source"] = "manifest"
        out = [s.with_split(m[s.storm_id]) for s in storms]
    else:
        n = len(storms)
        rng = np.random.default_rng(seed)
        info["source"] = f"random(seed={seed})"
        if n == 1:
            out = [storms[0].with_split("train")]
            info["selection_on_train"] = True
            log.warning("Single storm: train == eval (legacy Trial 7 mode)")
        elif n == 2:
            order = rng.permutation(2)
            out = [storms[i].with_split("train" if i == order[0] else "test") for i in range(2)]
            info["selection_on_train"] = True
        else:
            totals = np.array([s.depth.sum() for s in storms])
            pool = list(range(n))
            if extrapolation_guard and n >= 5:
                pool.remove(int(totals.argmax()))
                pool.remove(int(totals.argmin()))
            n_test = max(1, round(test_frac * n))
            n_val = max(1, round(val_frac * n))
            pick = rng.permutation(pool)[: n_test + n_val]
            test_idx, val_idx = set(pick[:n_test]), set(pick[n_test:])
            out = [s.with_split("test" if i in test_idx else "val" if i in val_idx else "train")
                   for i, s in enumerate(storms)]
    if not any(s.split == "val" for s in out):
        info["selection_on_train"] = True
        log.warning("No validation storms: model selection falls back to TRAIN storms")
    info["counts"] = {sp: sum(s.split == sp for s in out) for sp in ("train", "val", "test")}
    return out, info


def augment_train(storms, scales):
    """Optional intensity augmentation, TRAIN storms only. Scales multiply depth/intensity."""
    out = list(storms)
    for s in storms:
        if s.split != "train":
            continue
        for k in scales:
            if abs(k - 1.0) < 1e-9:
                continue
            out.append(Storm(f"{s.storm_id}@x{k:g}", s.source, s.intensity * k, s.depth * k,
                             "train", {**s.meta, "aug_scale": k, "parent": s.storm_id}))
    return out


# ---------------------------------------------------------------- sampler
class StormSampler:
    def __init__(self, storms, mode="shuffled_cycle", seed=0):
        self.storms, self.mode = list(storms), mode
        self.rng = np.random.default_rng(seed)
        self._queue: list[int] = []
        self.counts = {s.storm_id: 0 for s in self.storms}

    def next(self) -> Storm:
        if self.mode == "uniform":
            s = self.storms[int(self.rng.integers(len(self.storms)))]
        else:
            if not self._queue:
                self._queue = [int(i) for i in self.rng.permutation(len(self.storms))]
            s = self.storms[self._queue.pop()]
        self.counts[s.storm_id] += 1
        return s

    def state_dict(self):
        return {"rng": self.rng.bit_generator.state, "queue": self._queue, "counts": self.counts}

    def load_state_dict(self, d):
        self.rng.bit_generator.state = d["rng"]
        self._queue, self.counts = list(d["queue"]), dict(d["counts"])


# ---------------------------------------------------------------- audit
def storm_table(storms) -> pd.DataFrame:
    rows = []
    for s in storms:
        wet = np.flatnonzero(s.depth > 0)
        rows.append(dict(
            storm_id=s.storm_id, split=s.split, total_mm=s.depth.sum(),
            peak_mm_per_step=s.depth.max(), peak_intensity=s.intensity.max(),
            wet_steps=len(wet), wet_frac=len(wet) / N_STEPS,
            first_wet_h=wet[0] * 0.25 if len(wet) else np.nan,
            last_wet_h=wet[-1] * 0.25 if len(wet) else np.nan,
            raw_peak=s.meta.get("raw_peak"), scaling=s.meta.get("scaling"), sha=s.sha))
    return pd.DataFrame(rows)
```

**Accept:** `pytest tests/test_storms.py` passes; loading `raindata.csv` reproduces ≈114 mm total, ~76 wet intervals, 0–6 mm/interval.

---

## Stage 3 — Storm-per-episode in the env + KB (the only edits to model-side code)

These are minimal plumbing edits, not model changes.

**Prompt:**
```text
Edit ONLY plumbing in app.py:

SymbolicKnowledgeBase:
- Add attribute `baseline_flooding` (default = existing BASELINE_FLOODING constant) and
  `set_baseline_flooding(v)`. In shape_reward replace the global BASELINE_FLOODING with self.baseline_flooding.
- Leave FLOODING_THRESHOLD (9500), predicates, projection and weights untouched.

NeurosymbolicSWMMEnv:
- Store rainfall per instance: self._rain (np.ndarray of mm per interval). Default = the legacy loaded series.
- reset(self, *, seed=None, options=None): if options has "storm", set self.current_storm and self._rain=storm.depth;
  if "baseline_flooding", call kb.set_baseline_flooding; if options.get("native"), set self.native_mode=True
  else False. Then run the existing reset logic (close/reopen simulation).
- step(): rg1.total_precip = self._rain[self.t] (instead of the global). In native_mode skip KB projection and skip
  all target_setting writes (SWMM [CONTROLS] rules act), but still advance, record logs, and apply rainfall.
- Add get_episode_log() returning the contract dict from Section 5 (arrays, not lists of dicts).
- Add storm_id to info.
- Assert len(self._rain) >= number of steps in the episode.

Do not change any other behavior. Update adapters.py accordingly and add train_one_episode by extracting the
existing Trial 7 loop verbatim. Re-run tests/test_golden.py.
```
**Accept:** `test_golden.py` passes unchanged (single storm + baseline 7183 ⇒ identical numbers); switching storm via `reset(options={"storm": other})` changes rainfall observed in the log.

---

## Stage 4 — Metrics (`metrics.py`)

**Prompt:** *"Create multistorm/metrics.py exactly as below. `cso_total` must use the same definition as the existing CSO logging (sum over steps of `flow_35391 + flow_35444`) so numbers match Trial 7."*

```python
# multistorm/metrics.py
from __future__ import annotations
import numpy as np
import pandas as pd

FLOOD_THRESHOLD = 9500.0   # R6 (frozen KB value)
STORAGE_R1 = 0.85
STORAGE_CLOSE = 0.70


def episode_summary(L: dict, baseline_flooding: float | None = None,
                    flood_threshold: float = FLOOD_THRESHOLD) -> dict:
    cso = np.asarray(L["cso_flow"], float)
    fl = np.asarray(L["flooding"], float)
    fill = np.asarray(L["storage_fill"], float)
    acts = np.asarray(L["actions_projected"], float)
    out = dict(
        steps=len(cso),
        score=float(np.sum(L["reward"])),
        cso_total=float(cso.sum()), cso_peak=float(cso.max()),
        cso_active_frac=float((cso > 0).mean()),
        flood_total=float(fl.sum()), flood_mean=float(fl.mean()), flood_peak=float(fl.max()),
        r6_frac=float((fl > flood_threshold).mean()),
        fill_min=float(fill.min()), fill_max=float(fill.max()),
        r1_frac=float((fill >= STORAGE_R1).mean()),
        close_frac=float((fill < STORAGE_CLOSE).mean()),
    )
    if baseline_flooding is not None:
        out["flood_excess_mean"] = float(np.maximum(fl - baseline_flooding, 0).mean())
    for k in range(7):
        out[f"gate{k}_mean"] = float(acts[:, k].mean())
    for k in ("r_close", "r_cso", "r_flood"):
        if k in L:
            out[f"sum_{k}"] = float(np.sum(L[k]))
    return out


def relative(s: dict, rec: dict, cso_floor: float = 1.0) -> dict:
    """Compare an episode summary to the per-storm reference records."""
    b = rec["static"]
    o = dict(static_cso=b["cso_total"], static_flood_total=b["flood_total"],
             static_r6_frac=b["r6_frac"], baseline_flooding=rec["baseline_flooding"])
    o["cso_delta"] = s["cso_total"] - b["cso_total"]
    o["cso_reduction_pct"] = (100 * (b["cso_total"] - s["cso_total"]) / b["cso_total"]
                              if b["cso_total"] > cso_floor else float("nan"))
    o["flood_ratio"] = s["flood_total"] / b["flood_total"] if b["flood_total"] > 0 else float("nan")
    o["r6_excess"] = max(s["r6_frac"] - b["r6_frac"], 0.0)
    o["score_adv"] = s["score"] - b["score"]
    n = rec.get("native")
    if n and n["cso_total"] > cso_floor:
        o["native_cso"] = n["cso_total"]
        o["cso_reduction_vs_native_pct"] = 100 * (n["cso_total"] - s["cso_total"]) / n["cso_total"]
    return o


def aggregate(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["cso_reduction_pct"])
    micro = (100 * (d.static_cso.sum() - d.cso_total.sum()) / d.static_cso.sum()
             if len(d) and d.static_cso.sum() > 0 else float("nan"))
    g = lambda col, f: float(f(df[col])) if col in df and len(df) else float("nan")
    return dict(
        n_storms=len(df), n_scored=len(d),
        cso_red_macro=float(d.cso_reduction_pct.mean()) if len(d) else float("nan"),
        cso_red_median=float(d.cso_reduction_pct.median()) if len(d) else float("nan"),
        cso_red_std=float(d.cso_reduction_pct.std(ddof=0)) if len(d) else float("nan"),
        cso_red_worst=float(d.cso_reduction_pct.min()) if len(d) else float("nan"),
        cso_red_micro=float(micro),
        frac_improved=float((d.cso_reduction_pct > 0).mean()) if len(d) else float("nan"),
        flood_ratio_mean=g("flood_ratio", np.nanmean), flood_ratio_max=g("flood_ratio", np.nanmax),
        flood_regress_frac=float((df.flood_ratio > 1.05).mean()) if "flood_ratio" in df else float("nan"),
        r6_excess_mean=g("r6_excess", np.mean), r6_frac_max=g("r6_frac", np.max),
        score_adv_mean=g("score_adv", np.mean),
    )


def selection_score(agg: dict, r6_cap: float = 0.01, flood_ratio_cap: float = 1.05) -> float:
    """Primary = macro CSO reduction on validation storms. Safety caps demote infeasible models."""
    s = agg["cso_red_macro"]
    if s != s:
        return -1e9
    ok = agg["r6_excess_mean"] <= r6_cap and agg["flood_ratio_mean"] <= flood_ratio_cap
    return s if ok else s - 100.0
```

**Accept:** unit test with a synthetic log verifies each metric; a storm with zero baseline CSO yields `NaN` reduction (excluded from macro mean, still reported).

---

## Stage 5 — Baselines and reference policies (`baselines.py`)

Per storm, run once and cache:
1. **Flooding calibration** → `baseline_flooding` (same definition as the old 7183, via existing `run_baseline_episode`).
2. **Static reference** (gates 0.5, pumps ON, through the normal env path with the calibrated baseline) → CSO, flooding, R6 fraction, shaped score.
3. **Native-controls reference** (`options["native"]=True`) → CSO, flooding. This answers "how much better than the existing SWMM rules?".

**Prompt:** *"Create multistorm/baselines.py as below. Wire `calibrate_fn`, `static_fn`, `native_fn` in adapters.py. `static_fn(storm, baseline_flooding)` runs the env with constant action (0.5×7 gates, 1.0×3 pumps) and returns `{**episode_summary(log), 'score': ...}`. Cache is keyed by storm hash, INP hash and a version tag."*

```python
# multistorm/baselines.py
from __future__ import annotations
import hashlib, json
from pathlib import Path


def file_sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


class BaselineStore:
    def __init__(self, cache_path, inp_path, calibrate_fn, static_fn, native_fn=None, tag="v1"):
        self.path = Path(cache_path)
        self.inp_sha, self.tag = file_sha(inp_path), tag
        self.calibrate_fn, self.static_fn, self.native_fn = calibrate_fn, static_fn, native_fn
        self._d = json.loads(self.path.read_text()) if self.path.exists() else {}

    def _key(self, storm) -> str:
        return f"{self.tag}|{self.inp_sha}|{storm.sha}"

    def get(self, storm) -> dict:
        k = self._key(storm)
        if k not in self._d:
            fb = float(self.calibrate_fn(storm))
            rec = {"storm_id": storm.storm_id, "baseline_flooding": fb,
                   "static": self.static_fn(storm, fb),
                   "native": self.native_fn(storm) if self.native_fn else None}
            self._d[k] = rec
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._d, indent=1, default=float))
        return self._d[k]
```

**Accept:** second call hits the cache (no sim). For `raindata.csv` the calibrated flooding is ≈ 7183 (or close; remember the note that gates at 0.5 may lower it, so compare and record the actual number).

---

## Stage 6 — Evaluation harness (`evaluate.py`)

**Prompt:** *"Create multistorm/evaluate.py as below. It must never call agent update, never push to the replay buffer, and must run the policy deterministically."*

```python
# multistorm/evaluate.py
from __future__ import annotations
import time
import pandas as pd
import torch
from .metrics import episode_summary, relative


def evaluate(agent, env, storms, bstore, phase, episode=None,
             deterministic=True, cso_floor=1.0) -> pd.DataFrame:
    rows = []
    for st in storms:
        rec = bstore.get(st)
        t0 = time.time()
        obs, _ = env.reset(options={"storm": st, "baseline_flooding": rec["baseline_flooding"]})
        done = False
        with torch.no_grad():
            while not done:
                a = agent.select_action(obs, deterministic=deterministic)
                obs, _, term, trunc, _ = env.step(a)
                done = bool(term or trunc)
        s = episode_summary(env.get_episode_log(), rec["baseline_flooding"])
        rows.append(dict(
            phase=phase, episode=episode, storm_id=st.storm_id, split=st.split,
            rain_total_mm=float(st.depth.sum()), rain_peak_mm=float(st.depth.max()),
            deterministic=deterministic, wall_s=time.time() - t0,
            **s, **relative(s, rec, cso_floor)))
    return pd.DataFrame(rows)
```

**Accept:** evaluating the same checkpoint twice gives identical numbers; replay-buffer size is unchanged before/after.

---

## Stage 7 — Config and audit CLI

**Prompt:**
```text
Create multistorm/config.py with a dataclass MultiStormConfig and argparse:
rain_dir="rain", inp="7MPF_CSO_08.inp", scaling="peak", length_policy="pad_or_truncate",
seed=0, split_seed=0, split_manifest=None, val_frac=0.15, test_frac=0.15,
sampler="shuffled_cycle", augment_scales=[], train_ids=[], holdout_ids=[],
episodes=1000, warmup_steps=2000, update_every=4,        # = Trial 7 values, do not change defaults
eval_every=25, eval_train_k=3, ckpt_every=100,
run_name="run", out_dir="runs", fixed_baseline=None,    # fixed_baseline=7183 => ablation
cso_floor=1.0, r6_cap=0.01, flood_ratio_cap=1.05, resume=None.

Create multistorm/audit.py: load storms, assign splits, compute BaselineStore records for ALL storms,
write runs/audit/storm_audit.csv with columns from storm_table plus baseline_flooding,
static_cso, native_cso, static_r6_frac, baseline_flooding/9500, and a `warnings` column:
 - "NO_CSO" if static_cso <= cso_floor
 - "R6_DOMINATES" if baseline_flooding > 0.9*9500 or static_r6_frac > 0.25
 - "R6_NEVER" if flooding peak < 0.5*9500
 - "DUPLICATE" / "PADDED" / "TRUNCATED" if applicable
Print the table and the split counts.
```

```bash
python -m multistorm.audit --rain-dir rain --out-dir runs --run-name audit
```

**Decision rule after reading the audit:**
- `NO_CSO` storms: keep a few as *safety* storms (agent should not create CSO), but do not let them dominate macro averages (they are excluded automatically).
- `R6_DOMINATES` storms: the policy is mostly overridden there. Keep them for realism but expect low learning signal; report R6 fraction per storm.
- If every storm lands in one severity band, add more storms or use `--augment-scales 0.7,1.3`.

---

## Stage 8 — Multi-storm training (`train_multi.py`)

**Prompt:** *"Create multistorm/train_multi.py as below. The inner per-episode logic must come from `adapters.train_one_episode` (a verbatim extraction of Trial 7). Do not rewrite SAC logic."*

```python
# multistorm/train_multi.py
from __future__ import annotations
import json, logging, random, time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from . import adapters as A
from .baselines import BaselineStore
from .config import parse_args
from .evaluate import evaluate
from .metrics import aggregate, episode_summary, relative, selection_score
from .storms import (StormSampler, assign_splits, augment_train, load_storms, storm_table)

log = logging.getLogger("train")


def seed_everything(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)


def append_row(path: Path, row: dict):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not path.exists(), index=False)


def main(cfg=None):
    cfg = cfg or parse_args()
    run = Path(cfg.out_dir) / cfg.run_name
    (run / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run / "figures").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed_everything(cfg.seed)

    # ---- storms & splits
    storms = load_storms(cfg.rain_dir, cfg.scaling, length_policy=cfg.length_policy)
    storms, split_info = assign_splits(storms, cfg.split_seed, cfg.split_manifest,
                                       cfg.val_frac, cfg.test_frac)
    if cfg.train_ids:                       # e.g. E0: train on raindata only, test on the rest
        storms = [s.with_split("train" if s.storm_id in cfg.train_ids else "test") for s in storms]
        split_info["selection_on_train"] = True
    if cfg.holdout_ids:                     # leave-storm-out
        storms = [s.with_split("test") if s.storm_id in cfg.holdout_ids else s for s in storms]
    train = [s for s in storms if s.split == "train"]
    val = [s for s in storms if s.split == "val"] or train       # fallback flagged in split_info
    test = [s for s in storms if s.split == "test"]
    train_pool = augment_train(train, cfg.augment_scales) if cfg.augment_scales else train
    (run / "run_config.json").write_text(json.dumps(asdict(cfg), indent=1, default=str))
    (run / "storm_manifest.json").write_text(json.dumps(
        {"split_info": split_info,
         "storms": storm_table(storms).to_dict("records")}, indent=1, default=float))

    # ---- build model stack (unchanged Trial 7)
    env, agent, kb = A.build(cfg.seed)
    bstore = BaselineStore(Path(cfg.out_dir) / "baseline_cache.json", cfg.inp,
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env))

    def record(storm):
        rec = bstore.get(storm)
        if cfg.fixed_baseline is not None:             # ablation only
            rec = {**rec, "baseline_flooding": float(cfg.fixed_baseline)}
        return rec

    # pre-compute all references up front so training time is not interleaved with calibration
    for s in storms:
        bstore.get(s)

    sampler = StormSampler(train_pool, cfg.sampler, cfg.seed)
    best_sel, global_step, start_ep = -1e18, 0, 1
    if cfg.resume:
        ck = A.load_checkpoint(agent, cfg.resume)       # returns dict with extra
        sampler.load_state_dict(ck["sampler"]); global_step = ck["global_step"]
        start_ep = ck["episode"] + 1; best_sel = ck.get("best_sel", best_sel)

    t_start = time.time()
    for ep in range(start_ep, cfg.episodes + 1):
        st = sampler.next()
        rec = record(st)
        L, global_step = A.train_one_episode(
            env, agent, st, rec["baseline_flooding"], global_step,
            cfg.warmup_steps, cfg.update_every)
        s = episode_summary(L, rec["baseline_flooding"])
        append_row(run / "train_log.csv", dict(
            phase="train", episode=ep, storm_id=st.storm_id, global_step=global_step,
            alpha=agent.alpha_value(), warmup=global_step <= cfg.warmup_steps,
            rain_total_mm=float(st.depth.sum()), **s, **relative(s, rec, cfg.cso_floor)))

        if ep % cfg.eval_every == 0 and global_step > cfg.warmup_steps:
            vdf = evaluate(agent, env, val, bstore, "val", ep, cso_floor=cfg.cso_floor)
            parts = [vdf]
            if cfg.eval_train_k:                         # generalization-gap monitor
                parts.append(evaluate(agent, env, train[: cfg.eval_train_k], bstore,
                                      "train_eval", ep, cso_floor=cfg.cso_floor))
            pd.concat(parts).to_csv(run / "eval_log.csv", mode="a",
                                    header=not (run / "eval_log.csv").exists(), index=False)
            agg = aggregate(vdf)
            sel = selection_score(agg, cfg.r6_cap, cfg.flood_ratio_cap)
            log.info("ep %d | val CSO red macro %.1f%% worst %.1f%% | flood x%.2f | sel %.2f | %.0f min",
                     ep, agg["cso_red_macro"], agg["cso_red_worst"],
                     agg["flood_ratio_mean"], sel, (time.time() - t_start) / 60)
            if sel > best_sel:
                best_sel = sel
                A.save_checkpoint(agent, run / "checkpoints" / "best_val.pt",
                                  dict(episode=ep, sel=sel, agg=agg, global_step=global_step,
                                       sampler=sampler.state_dict()))
        if ep % cfg.ckpt_every == 0:
            A.save_checkpoint(agent, run / "checkpoints" / f"ep{ep}.pt",
                              dict(episode=ep, global_step=global_step, best_sel=best_sel,
                                   sampler=sampler.state_dict()))

    A.save_checkpoint(agent, run / "checkpoints" / "final.pt",
                      dict(episode=cfg.episodes, global_step=global_step, best_sel=best_sel,
                           sampler=sampler.state_dict()))

    # ---- final held-out evaluation: best_val checkpoint on ALL splits, deterministic
    best_path = run / "checkpoints" / "best_val.pt"
    if best_path.exists():
        A.load_checkpoint(agent, best_path)
    frames = [evaluate(agent, env, storms, bstore, "final", None, cso_floor=cfg.cso_floor)]
    fdf = pd.concat(frames)
    fdf.to_csv(run / "final_eval.csv", index=False)
    final_agg = {sp: aggregate(fdf[fdf.split == sp]) for sp in ("train", "val", "test")
                 if (fdf.split == sp).any()}
    final_agg["selection_on_train"] = split_info["selection_on_train"]
    (run / "final_agg.json").write_text(json.dumps(final_agg, indent=1, default=float))
    log.info("Done. Final aggregates: %s", json.dumps(final_agg, default=float)[:600])


if __name__ == "__main__":
    main()
```

**Accept (quick smoke test, ~10 min):**
```bash
python -m multistorm.train_multi --episodes 12 --warmup-steps 300 --eval-every 4 --run-name smoke
```
→ `train_log.csv` has rows cycling through storms, `eval_log.csv` has val rows, `best_val.pt` exists, `final_eval.csv` has every storm. Then a **regression run**: only `raindata.csv` in `rain/`, `--sampler shuffled_cycle`, confirm the learning curve looks like Trial 7 (score ≈ −900 early).

---

## Stage 9 — Reporting (`report.py`) and seed aggregation (`compare.py`)

**Prompt:**
```text
Create multistorm/report.py: given runs/<run>, read train_log.csv, eval_log.csv, final_eval.csv,
final_agg.json, storm_manifest.json and write figures/*.png and REPORT.md.

Figures (matplotlib, one PNG each):
1. training_curves.png: rolling-50 mean of cso_reduction_pct over training episodes (all storms), plus alpha,
   plus rolling mean of score_adv.
2. val_progress.png: validation macro CSO reduction, worst-case reduction, and flood_ratio_mean vs episode;
   mark best_val episode. Include train_eval line to show generalization gap.
3. per_storm_final.png: bar chart of final cso_reduction_pct per storm, bars colored by split; horizontal
   lines at 0 and at the macro mean.
4. severity_scatter.png: x = rain_total_mm, y = cso_reduction_pct, colored by split; shows whether gains
   depend on storm severity.
5. cso_vs_baselines.png: grouped bars per storm: static, native (if available), agent cso_total.
6. gates_by_storm.png: heatmap of gate0..gate6 mean action per storm (final eval).
7. safety.png: per-storm flood_ratio and r6_frac (final eval) with the caps drawn.
8. per_storm_learning.png: small multiples, rolling cso_reduction_pct per storm_id from train_log.csv.

REPORT.md: split counts, selection_on_train flag, table of final metrics per split (macro, median, worst,
micro, % improved, flood ratio, R6 excess), per-storm table, warnings from the audit, and the figure list.

Create multistorm/compare.py: takes several run dirs (seeds), reads final_agg.json, reports mean ± std across
seeds for each split and metric, and writes compare.csv + compare.png.
```

---

## 6. Experiment matrix (run in this order)

| ID | Purpose | Command (abridged) | Seeds |
|----|---------|--------------------|-------|
| **E0** | Reproduce Trial 7 and measure **transfer failure** of single-storm training | `--train-ids raindata --run-name e0_single` | 1–3 |
| **E1** | **Main result**: multi-storm training | `--run-name e1_multi` | 3 |
| E2 | Ablation: fixed baseline 7183 (shows why per-storm baseline matters) | `--fixed-baseline 7183 --run-name e2_fixedbase` | 1–3 |
| E3 | Scaling: `peak` vs `none` | `--scaling none --run-name e3_rawscale` | 1–3 |
| E4 | Augmentation | `--augment-scales 0.7,1.3 --run-name e4_aug` | 1–3 |
| E5 | Sampler | `--sampler uniform --run-name e5_uniform` | 1 |
| E6 | Leave-one-storm-out (only if ≤ 8 storms) | `--holdout-ids <id>` per storm | 1 each |

```bash
python -m multistorm.audit      --rain-dir rain --run-name audit
python -m multistorm.train_multi --rain-dir rain --run-name e0_single_s0 --seed 0 --train-ids raindata
python -m multistorm.train_multi --rain-dir rain --run-name e1_multi_s0  --seed 0
python -m multistorm.train_multi --rain-dir rain --run-name e1_multi_s1  --seed 1
python -m multistorm.train_multi --rain-dir rain --run-name e1_multi_s2  --seed 2
python -m multistorm.report  --run runs/e1_multi_s0
python -m multistorm.compare --runs runs/e1_multi_s0 runs/e1_multi_s1 runs/e1_multi_s2
```

**Compute estimate:** training is ~2–4 h CPU per run (unchanged); evaluation adds roughly `(eval_every=25 → 40 rounds) × (#val storms + 3) × one rollout`, usually well under an hour. Budget ~1 day for E0 + 3×E1 on one machine.

**The headline claim you should be able to make:** *E1 test-split macro CSO reduction vs E0 test-split* (same held-out storms), with seed variance, plus worst-case storm and flood-regression rate.

---

## 7. Acceptance checklist (whole project)

- [ ] `tests/test_golden.py` passes (single storm reproduces Trial 7).
- [ ] No module-level rainfall or `BASELINE_FLOODING` is read inside `step`/`shape_reward`.
- [ ] SAC, network, reward weights, predicates, projection untouched (`git diff` shows only plumbing in `app.py`).
- [ ] Audit CSV generated; warnings reviewed; split manifest saved.
- [ ] Training cycles through all train storms evenly (`sampler.counts` differ by ≤ 1).
- [ ] Evaluation is deterministic, has no updates and no replay writes.
- [ ] Best model chosen on validation storms (unless `selection_on_train` is true, which the report must state).
- [ ] Final test numbers come only from storms never used for selection or training.
- [ ] ≥ 3 seeds for headline numbers; mean ± std reported.
- [ ] `REPORT.md` and all figures regenerate from CSVs with one command.

---

## 8. Common pitfalls (tell your coding assistant)

1. **One SWMM simulation per process at a time.** Never run train and eval in parallel threads; run them sequentially between episodes. Parallelize across *processes* (one seed per process) only.
2. **Never evaluate mid-episode.** Call `evaluate` only between training episodes; `reset` fully closes/reopens the simulation.
3. **Reduction % is undefined when baseline CSO ≈ 0.** The code returns NaN and excludes it; still report absolute CSO for those storms.
4. **Do not mix scaling modes between runs when comparing.** The baseline cache key uses the storm hash, so it stays correct, but report the scaling mode in every table.
5. **Padding makes a dry tail**, which can lower CSO totals relative to full-length storms. Prefer full-length files.
6. **Percent changes across storms are not additive.** Use macro (storm average) *and* micro (volume-weighted) numbers together.
7. **Do not pick the best checkpoint by training score** in multi-storm mode; easy storms dominate it.
8. **Resume** restores model, optimizers, sampler state and counters, but not the replay buffer unless you also save it (optional, large).

---

## 9. Limitations to state in the paper (after this work)

- Policy still has no rainfall forecast or time-index input (observation layout frozen); generalization comes only from storm diversity in training.
- R6 uses a fixed absolute threshold, so its pressure varies by storm (reported, not corrected).
- With few storms (< 10), split results have high variance; leave-one-out or more storms strengthens claims.
- All storms use the same INP initial conditions, DWF pattern and 72 h window; storm-timing relative to the diurnal DWF pattern is not randomized.
- Pumps remain frozen ON; only seven gates are learned.

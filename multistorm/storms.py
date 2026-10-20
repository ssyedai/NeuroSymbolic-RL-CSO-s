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
MM_PER_INCH = 25.4


def rain_to_gage_value(depth_mm_per_15min: float | np.ndarray):
    """
    mm per 15-min interval → SWMM Design_RG INTENSITY value (in/hr).

    CFS + INTENSITY gage: pyswmm `total_precip` is a precipitation rate in
    project units (inches/hour). Verified by research/unit_audit.py.
      in/h = (depth_mm / 25.4) / 0.25 = depth_mm / 6.35
    """
    return np.asarray(depth_mm_per_15min, dtype=float) / (MM_PER_INCH * 0.25)


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
                 meta={"raw_peak": peak, "scaling": scaling,
                       "padded": len(np.asarray(raw)) < N_STEPS,
                       "truncated": len(np.asarray(raw)) > N_STEPS})


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("_")


def load_storms(rain_dir, scaling="peak", peak_target=PEAK_TARGET,
                length_policy="pad_or_truncate", storm_ids=None) -> list[Storm]:
    rain_dir = Path(rain_dir)
    skip = {"events.csv", "events_rejected.csv", "events_primary.csv",
            "data_manifest.json", "storm_audit.csv", "screening.csv",
            "scenarios.csv", "rejected.csv", "splits.json"}
    man_path = rain_dir / "data_manifest.json"
    man_storms = {}
    if man_path.exists():
        man_storms = json.loads(man_path.read_text()).get("storms") or {}
    if man_storms:
        # Prefer manifest keys so catalog CSVs (scenarios.csv etc.) are never loaded as rain
        files = [rain_dir / f"{sid}.csv" for sid in sorted(man_storms)
                 if (rain_dir / f"{sid}.csv").exists()]
    else:
        files = sorted(
            p for p in rain_dir.iterdir()
            if p.suffix.lower() in (".csv", ".xlsx", ".xls")
            and p.name not in skip
            and not p.name.endswith("_coverage.csv")
            and not p.name.endswith("_overview.csv")
            and not p.name.startswith("screening")
        )
    if storm_ids is not None:
        if not man_storms:
            raise ValueError("Selective loading requires a manifest")
        wanted = set(storm_ids)
        if wanted - set(man_storms):
            raise ValueError("Requested storms are absent from manifest")
        files = [p for p in files if p.stem in wanted]
        if {p.stem for p in files} != wanted:
            raise FileNotFoundError("Selected rainfall files are missing")
    if not files:
        raise FileNotFoundError(f"No rainfall files in {rain_dir}")
    storms: list[Storm] = []
    for p in files:
        df = _read_table(p)
        for k, col in enumerate(df.columns):
            s = df[col]
            last = s.last_valid_index()
            if last is None:
                continue
            s = s.iloc[: last + 1]            # strip trailing NaN
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
    # P10: attach scenario metadata from the v8 builder manifest when present
    if man_storms:
        out = []
        for s in storms:
            m = man_storms.get(s.storm_id)
            if not m:
                out.append(s)
                continue
            meta = dict(s.meta)
            t_by = m.get("T_by_dur") or {}
            # JSON keys may be str
            t360 = t_by.get("360", t_by.get(360, m.get("T_anchor")))
            meta.update(
                provenance=m.get("provenance"),
                family=m.get("family"),
                rung=m.get("rung"),
                k=m.get("k"),
                parent=m.get("parent"),
                test_only=m.get("test_only", False),
                T_anchor=t360,
                T_target=m.get("T_target"),
                T_by_dur=t_by,
            )
            out.append(Storm(s.storm_id, s.source, s.intensity, s.depth, s.split, meta))
        storms = out
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
            raw_peak=s.meta.get("raw_peak"), scaling=s.meta.get("scaling"), sha=s.sha,
            padded=bool(s.meta.get("padded")), truncated=bool(s.meta.get("truncated"))))
    return pd.DataFrame(rows)

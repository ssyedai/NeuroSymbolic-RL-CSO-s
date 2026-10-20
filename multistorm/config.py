"""Multi-storm training configuration."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MultiStormConfig:
    rain_dir: str = "rain"
    inp: str = "7MPF_CSO_08.inp"
    scaling: str = "peak"
    length_policy: str = "pad_or_truncate"
    seed: int = 0
    split_seed: int = 0
    split_manifest: Optional[str] = None
    val_frac: float = 0.15
    test_frac: float = 0.15
    sampler: str = "shuffled_cycle"
    augment_scales: List[float] = field(default_factory=list)
    train_ids: List[str] = field(default_factory=list)
    holdout_ids: List[str] = field(default_factory=list)
    episodes: int = 1000
    warmup_steps: int = 2000
    update_every: int = 4
    eval_every: int = 25
    eval_train_k: int = 3
    ckpt_every: int = 100
    run_name: str = "run"
    out_dir: str = "runs"
    fixed_baseline: Optional[float] = None
    cso_floor: float = 1.0
    r6_cap: float = 0.01
    flood_ratio_cap: float = 1.05
    resume: Optional[str] = None
    real_only: bool = False
    physical_rain: bool = False
    variant: str = "m0"
    data_manifest: Optional[str] = None
    diet: str = "D2_ladder100"
    train_max_T: float = 100.0
    allow_test_only_rungs: bool = False
    primary_observed_only: bool = False
    updates_per_step: float = 0.25
    theta_path: Optional[str] = None
    controllability_summary: Optional[str] = None
    eager_baselines: bool = False
    max_val_eval: int = 0
    max_final_val_eval: int = 0
    strict_safety_selection: bool = False
    evaluate_test: bool = False
    exploratory: bool = False


def _parse_float_list(s: str) -> List[float]:
    if not s:
        return []
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def _parse_str_list(s: str) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def parse_args(argv=None) -> MultiStormConfig:
    p = argparse.ArgumentParser(description="Multi-storm neurosymbolic SAC training")
    p.add_argument("--rain-dir", default="data/useful/rain_real_stormy_x2")
    p.add_argument("--inp", default="7MPF_CSO_08.inp")
    p.add_argument("--scaling", default="peak", choices=["peak", "none"])
    p.add_argument("--length-policy", default="pad_or_truncate")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--split-seed", type=int, default=0)
    p.add_argument("--split-manifest", default="data/useful/splits/splits_stormy_x2.json")
    p.add_argument("--val-frac", type=float, default=0.15)
    p.add_argument("--test-frac", type=float, default=0.15)
    p.add_argument("--sampler", default="shuffled_cycle", choices=["shuffled_cycle", "uniform"])
    p.add_argument("--augment-scales", type=_parse_float_list, default="")
    p.add_argument("--train-ids", type=_parse_str_list, default="")
    p.add_argument("--holdout-ids", type=_parse_str_list, default="")
    p.add_argument("--episodes", type=int, default=1000)
    p.add_argument("--warmup-steps", type=int, default=2000)
    p.add_argument("--update-every", type=int, default=4)
    p.add_argument("--eval-every", type=int, default=25)
    p.add_argument("--eval-train-k", type=int, default=3)
    p.add_argument("--ckpt-every", type=int, default=100)
    p.add_argument("--run-name", default="run")
    p.add_argument("--out-dir", default="runs")
    p.add_argument("--fixed-baseline", type=float, default=None)
    p.add_argument("--cso-floor", type=float, default=1.0)
    p.add_argument("--r6-cap", type=float, default=0.01)
    p.add_argument("--flood-ratio-cap", type=float, default=1.05)
    p.add_argument("--resume", default=None)
    p.add_argument("--real-only", action="store_true", default=False)
    p.add_argument("--no-real-only", action="store_true", default=False)
    p.add_argument("--physical-rain", action="store_true", default=False)
    p.add_argument("--variant", default="m0",
                   choices=["m0", "m1", "a1", "a2", "a3", "e0",
                            "v7", "v8", "v8_complete", "plain", "lag_only",
                            "b0", "b2", "b3",
                            "v8_notopo", "v8_nostore", "v8_nolag", "v8_noshield",
                            "v8_norain", "v8_10d"])
    p.add_argument("--data-manifest", default=None)
    p.add_argument("--diet", default="D2_ladder100",
                   choices=["D1_flat2", "D2_ladder100", "D3_ladder1000", "D4_real", "D5_all"])
    p.add_argument("--train-max-T", type=float, default=100.0)
    p.add_argument("--allow-test-only-rungs", action="store_true", default=False)
    p.add_argument("--primary-observed-only", action="store_true", default=False)
    p.add_argument("--updates-per-step", type=float, default=0.25)
    p.add_argument("--theta-path", default=None)
    p.add_argument(
        "--controllability-summary", default=None,
        help="Optional G2 summary JSON; exploratory runs must not reuse official results",
    )
    p.add_argument("--eager-baselines", action="store_true", default=False)
    p.add_argument("--max-val-eval", type=int, default=0,
                   help="Cap validation storms used for mid-training selection (0=all)")
    p.add_argument("--max-final-val-eval", type=int, default=0,
                   help="Exploratory-only cap for final validation (0=all)")
    p.add_argument("--strict-safety-selection", action="store_true",
                   help="Reject checkpoints that fail safety, including zero-when-feasible")
    p.add_argument("--evaluate-test", action="store_true",
                   help="Explicitly enable test evaluation after protocol freeze")
    p.add_argument("--exploratory", action="store_true",
                   help="Run with an explicit unverified-native-reference watermark")
    a = p.parse_args(argv)
    if a.diet == "D3_ladder1000":
        a.train_max_T = max(a.train_max_T, 1000.0)
        a.allow_test_only_rungs = True
    return MultiStormConfig(
        rain_dir=a.rain_dir, inp=a.inp, scaling=a.scaling,
        length_policy=a.length_policy, seed=a.seed, split_seed=a.split_seed,
        split_manifest=a.split_manifest, val_frac=a.val_frac, test_frac=a.test_frac,
        sampler=a.sampler, augment_scales=a.augment_scales or [],
        train_ids=a.train_ids or [], holdout_ids=a.holdout_ids or [],
        episodes=a.episodes, warmup_steps=a.warmup_steps, update_every=a.update_every,
        eval_every=a.eval_every, eval_train_k=a.eval_train_k, ckpt_every=a.ckpt_every,
        run_name=a.run_name, out_dir=a.out_dir, fixed_baseline=a.fixed_baseline,
        cso_floor=a.cso_floor, r6_cap=a.r6_cap, flood_ratio_cap=a.flood_ratio_cap,
        resume=a.resume,
        real_only=(False if a.no_real_only else a.real_only),
        physical_rain=a.physical_rain or a.real_only,
        variant=a.variant,
        data_manifest=a.data_manifest,
        diet=a.diet, train_max_T=a.train_max_T,
        allow_test_only_rungs=a.allow_test_only_rungs,
        primary_observed_only=a.primary_observed_only,
        updates_per_step=a.updates_per_step,
        theta_path=a.theta_path,
        controllability_summary=a.controllability_summary,
        eager_baselines=a.eager_baselines,
        max_val_eval=a.max_val_eval,
        max_final_val_eval=a.max_final_val_eval,
        strict_safety_selection=a.strict_safety_selection,
        evaluate_test=a.evaluate_test,
        exploratory=a.exploratory,
    )

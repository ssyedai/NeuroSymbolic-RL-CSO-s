# multistorm/train_multi.py
from __future__ import annotations
import hashlib
import importlib.metadata
import json, logging, random, time
import platform
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from . import adapters as A
from .baselines import BaselineStore, DEFAULT_BASELINE_TAG
from .config import parse_args
from .diet import filter_train_pool
from .evaluate import evaluate
from .metrics import aggregate, episode_summary, relative, selection_score
from .samplers import StratifiedSampler
from .safety_selection import validation_selection
from .storms import (StormSampler, assign_splits, augment_train, load_storms, storm_table)

log = logging.getLogger("train")

V8_VARIANTS = {
    "v8", "v8_complete", "plain", "lag_only", "b2", "b3",
    "v8_notopo", "v8_nostore", "v8_nolag", "v8_noshield", "v8_norain", "v8_10d",
    "v8_actionmask",
    "v8_nativeprior",
    "v8_nativeprior_5m",
    "v8_hybrid_gate2",
}


def seed_everything(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


_CSV_COLS: dict[str, list[str]] = {}


def append_row(path: Path, row: dict):
    """Append a CSV row with a stable header (first row defines column order)."""
    path = Path(path)
    key = str(path)
    if key not in _CSV_COLS:
        if path.exists() and path.stat().st_size > 0:
            _CSV_COLS[key] = list(pd.read_csv(path, nrows=0).columns)
        else:
            _CSV_COLS[key] = list(row.keys())
            pd.DataFrame([row], columns=_CSV_COLS[key]).to_csv(path, index=False)
            return
    cols = _CSV_COLS[key]
    # drop unknown keys; fill missing with blank
    ordered = {c: row.get(c, "") for c in cols}
    pd.DataFrame([ordered], columns=cols).to_csv(path, mode="a", header=False, index=False)


def _load_theta(path, exploratory=False, require_metadata=False):
    if not path:
        return None
    blob = json.loads(Path(path).read_text())
    if require_metadata and "theta" not in blob:
        raise ValueError("Research theta file lacks calibration metadata")
    if "theta" in blob:
        if blob.get("b3_beats_b2_on_val") is not True:
            raise ValueError("Theta file was not better than B2 on validation")
        if exploratory:
            if blob.get("research_status") != "exploratory_unverified_native_reference":
                raise ValueError("Exploratory training requires exploratory theta evidence")
        else:
            if blob.get("full_protocol_budget") is not True:
                raise ValueError("Official training requires full-budget theta calibration")
            if blob.get("research_status") != "official_hydraulic_gate_passed":
                raise ValueError("Official training cannot use exploratory theta evidence")
    return blob.get("theta", blob)


def _load_controllable(path="runs/controllability.csv"):
    p = Path(path)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if "uncontrollable" not in df.columns:
        return None
    ok = df[~df["uncontrollable"].astype(bool)]
    ids = set(ok["storm_id"].astype(str))
    if "parent" in ok.columns:
        ids |= set(ok["parent"].astype(str))
    return ids


def _build_stack(cfg):
    v = cfg.variant
    theta = _load_theta(
        cfg.theta_path, getattr(cfg, "exploratory", False),
        require_metadata=v in V8_VARIANTS)
    def v8_stack(**kwargs):
        # Every official v8 comparison uses identical complete four-outfall
        # volume accounting, exclusive external gate ownership, and the INP's
        # native pump interlocks. Variant flags change only their named factor.
        kwargs.setdefault("native_pumps", True)
        return A.build_v8(
            cfg.seed, complete_overflow=True,
            input_file=cfg.inp, **kwargs)
    if v == "v8_complete":
        if theta:
            raise ValueError("Use --variant b3 for a calibrated theta controller")
        return v8_stack()
    if v in ("v8", "b2", "b3"):
        return v8_stack(theta=theta if v == "b3" else (theta if v != "b2" else None),
                        use_projection=True, lagrangian=True, rain_features=True)
    if v == "plain":
        return v8_stack(use_projection=False, lagrangian=False,
                        rain_features=False, cost_limit=1e9, lam_init=0.0, lam_lr=0.0,
                        w_store=0.0)
    if v == "lag_only":
        return v8_stack(use_projection=False, lagrangian=True,
                        rain_features=False, w_store=0.0)
    if v == "v8_noshield":
        return v8_stack(theta=theta, use_projection=False, lagrangian=True)
    if v == "v8_nolag":
        return v8_stack(theta=theta, use_projection=True, lagrangian=False,
                        lam_init=0.0, lam_lr=0.0)
    if v == "v8_norain":
        return v8_stack(theta=theta, rain_features=False)
    if v == "v8_nostore":
        env, agent, kb = v8_stack(theta=theta)
        kb.w_store = 0.0
        return env, agent, kb
    if v == "v8_notopo":
        return v8_stack(theta=theta, topology_aware=False)
    if v == "v8_10d":
        return v8_stack(theta=theta, policy_dim=10, native_pumps=False,
                        policy_controls_pumps=True)
    if v == "v8_actionmask":
        return v8_stack(theta=theta, hard_bypass_mask=True)
    if v == "v8_nativeprior":
        return v8_stack(theta=theta, native_rule_prior=True, policy_dim=3)
    if v == "v8_nativeprior_5m":
        return v8_stack(theta=theta, native_rule_prior=True, policy_dim=3,
                        control_time_step=300)
    if v == "v8_hybrid_gate2":
        return v8_stack(
            theta=theta, gate2_rule_prior=True, policy_dim=1,
            native_managed_gates=("1360", "1360_B", "35281_B", "35291_B", "3530", "3530_B"),
            external_gate_indices=(2,),
        )
    # v7 / m0 / legacy
    env, agent, kb = A.build(cfg.seed)
    if cfg.physical_rain or cfg.real_only:
        env.physical_rain = True
    return env, agent, kb


def _v8_selection(vdf: pd.DataFrame) -> float:
    return validation_selection(vdf)


def _balanced_rung_cap(storms, limit):
    if not limit or len(storms) <= limit:
        return list(storms)
    groups = {}
    for storm in sorted(storms, key=lambda s: s.storm_id):
        groups.setdefault(str((storm.meta or {}).get("rung", "unknown")), []).append(storm)
    selected = []
    while groups and len(selected) < limit:
        for rung in sorted(list(groups)):
            if len(selected) >= limit:
                break
            selected.append(groups[rung].pop(0))
            if not groups[rung]:
                del groups[rung]
    return selected


def main(cfg=None):
    cfg = cfg or parse_args()
    experiment = dict(research_status="legacy", exploratory=False,
                      hydraulic_gate_passed=None)
    if cfg.variant in V8_VARIANTS:
        from research.readiness import experiment_status
        experiment = experiment_status(cfg.exploratory)
        if cfg.variant in {"v8_nativeprior", "v8_nativeprior_5m", "v8_hybrid_gate2"}:
            raise RuntimeError(
                f"{cfg.variant} is diagnostic-only: its TRAIN safety grid found no "
                "setting with complete flood and total-overflow non-regression. "
                "Do not train around an unsafe prior; see "
                "runs/exploratory/nativeprior_grid*/summary.csv and "
                "runs/exploratory/hybrid_gate2_screen/.")
        if cfg.exploratory and not cfg.run_name.startswith("exploratory_"):
            raise ValueError("Exploratory v8 run names must start with 'exploratory_'")
        if cfg.max_final_val_eval and not cfg.exploratory:
            raise ValueError("--max-final-val-eval is exploratory-only")
    run = Path(cfg.out_dir) / cfg.run_name
    if (run / "train_log.csv").exists() and not cfg.resume:
        raise ValueError("Run already contains training results; choose a new run name or resume explicitly")
    (run / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run / "figures").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed_everything(cfg.seed)

    if cfg.real_only or cfg.variant in V8_VARIANTS:
        cfg.scaling = "none"
        cfg.augment_scales = []
        if cfg.data_manifest is None:
            cfg.data_manifest = str(Path(cfg.rain_dir) / "data_manifest.json")
        log.info("Research mode: scaling=none, augment disabled, manifest=%s", cfg.data_manifest)

    if cfg.variant in V8_VARIANTS and cfg.evaluate_test:
        raise ValueError(
            "Research training never loads the test split. Train first, freeze the protocol, "
            "then use multistorm.evaluate_checkpoint in a separate process.")
    selected_ids = None
    if cfg.variant in V8_VARIANTS:
        if not cfg.split_manifest or not Path(cfg.split_manifest).is_file():
            raise ValueError("Research training requires a fixed split manifest; test rainfall is not loaded")
        split_map = json.loads(Path(cfg.split_manifest).read_text())
        selected_ids = [sid for sid, split in split_map.items() if split in ("train", "val")]
    storms = load_storms(cfg.rain_dir, cfg.scaling, length_policy=cfg.length_policy,
                         storm_ids=selected_ids)
    storms, split_info = assign_splits(storms, cfg.split_seed, cfg.split_manifest,
                                       cfg.val_frac, cfg.test_frac)
    from research.guard import assert_provenance, assert_real_only, assert_v8_scenario_manifest
    if Path(cfg.data_manifest or "").exists() or (Path(cfg.rain_dir) / "data_manifest.json").exists():
        allowed = None
        if cfg.primary_observed_only:
            allowed = {"train": {"observed"}, "val": {"observed"}, "test": {"observed"}}
        try:
            assert_provenance(storms, cfg.rain_dir, cfg.data_manifest, allowed=allowed)
        except RuntimeError:
            if cfg.real_only and cfg.variant not in V8_VARIANTS:
                assert_real_only(storms, rain_dir=cfg.rain_dir, manifest=cfg.data_manifest)
            else:
                raise
    if cfg.variant in V8_VARIANTS:
        assert_v8_scenario_manifest(
            cfg.rain_dir, cfg.data_manifest,
            allow_exploratory=cfg.exploratory)
    if cfg.train_ids:
        storms = [s.with_split("train" if s.storm_id in cfg.train_ids else "test") for s in storms]
        split_info["selection_on_train"] = True
    if cfg.holdout_ids:
        storms = [s.with_split("test") if s.storm_id in cfg.holdout_ids else s for s in storms]

    # G2 eligibility is rung-level (summary.json). Do NOT use the stratified
    # per-storm controllability sample as a whitelist — that shrinks the pool incorrectly.
    from .diet import load_uncontrollable_rungs
    controllability_summary = cfg.controllability_summary
    if controllability_summary is None and cfg.exploratory:
        controllability_summary = "runs/exploratory/controllability.csv.summary.json"
    bad_rungs = load_uncontrollable_rungs(
        controllability_summary or "runs/controllability.csv.summary.json")
    if bad_rungs:
        log.info("G2 uncontrollable rungs excluded from train: %s", bad_rungs)
    train_all = [s for s in storms if s.split == "train"]
    if any((s.meta or {}).get("family") for s in storms):
        train = filter_train_pool(
            storms, cfg.diet, cfg.train_max_T, cfg.allow_test_only_rungs,
            controllable=None, bad_rungs=bad_rungs)
    else:
        train = train_all
    from .diet import within_training_ceiling
    val = [s for s in storms if s.split == "val"]
    if not val and any((s.meta or {}).get("family") for s in storms):
        raise ValueError("Research scenarios require a separate validation split")
    val = val or train  # retain legacy behavior only for catalogs without scenario metadata
    val = [s for s in val if within_training_ceiling(s.meta or {}, cfg.train_max_T)]
    if not val:
        raise ValueError("No validation storms remain within the training ceiling")
    val_full = list(val)
    train_pool = augment_train(train, cfg.augment_scales) if cfg.augment_scales else train

    # run_config with hashes
    man_path = Path(cfg.data_manifest or (Path(cfg.rain_dir) / "data_manifest.json"))
    man_hash = hashlib.sha256(man_path.read_bytes()).hexdigest() if man_path.exists() else None
    theta_hash = None
    if cfg.theta_path and Path(cfg.theta_path).exists():
        theta_hash = hashlib.sha256(Path(cfg.theta_path).read_bytes()).hexdigest()
    git_dirty_files = []
    git_diff_sha256 = None
    try:
        import subprocess
        git_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        git_dirty_files = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True).splitlines()
        if git_dirty_files:
            git_diff = subprocess.check_output(["git", "diff", "--binary", "HEAD"])
            git_diff_sha256 = hashlib.sha256(git_diff).hexdigest()
    except Exception:
        git_hash = None
    strict_selection = bool(cfg.strict_safety_selection or cfg.variant in V8_VARIANTS)
    packages = ("numpy", "pandas", "torch", "gymnasium", "pyswmm", "swmm-toolkit",
                "scipy", "networkx", "cma")
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    config_baseline_tag = DEFAULT_BASELINE_TAG
    if cfg.variant in V8_VARIANTS:
        from .complete_overflow import COMPLETE_BASELINE_TAG, EXPLORATORY_BASELINE_TAG
        config_baseline_tag = (EXPLORATORY_BASELINE_TAG if cfg.exploratory
                               else COMPLETE_BASELINE_TAG)
        if cfg.variant == "v8_hybrid_gate2":
            config_baseline_tag += "|hybridgate2"
    run_cfg = dict(asdict(cfg), git_hash=git_hash, git_dirty=bool(git_dirty_files),
                   git_dirty_files=git_dirty_files, git_diff_sha256=git_diff_sha256,
                   manifest_hash=man_hash, theta_hash=theta_hash,
                   baseline_tag=config_baseline_tag,
                   effective_strict_safety_selection=strict_selection,
                   effective_native_pumps=cfg.variant != "v8_10d",
                   effective_policy_controls_pumps=cfg.variant == "v8_10d",
                   effective_hard_bypass_mask=cfg.variant == "v8_actionmask",
                   effective_native_rule_prior=cfg.variant in {"v8_nativeprior", "v8_nativeprior_5m"},
                   effective_gate2_rule_prior=cfg.variant == "v8_hybrid_gate2",
                   effective_control_time_step_s=(300 if cfg.variant == "v8_nativeprior_5m" else 900),
                   **experiment,
                   python_version=platform.python_version(), lib_versions=versions)
    (run / "run_config.json").write_text(json.dumps(run_cfg, indent=1, default=str))
    (run / "storm_manifest.json").write_text(json.dumps(
        {"split_info": split_info,
         "storms": storm_table(storms).to_dict("records"),
         "n_train_pool": len(train_pool)}, indent=1, default=float))

    env, agent, kb = _build_stack(cfg)
    log.info("Compute device: %s | variant=%s diet=%s train_pool=%d",
             torch.device("cuda" if torch.cuda.is_available() else "cpu"),
             cfg.variant, cfg.diet, len(train_pool))

    baseline_tag = DEFAULT_BASELINE_TAG
    if cfg.variant in V8_VARIANTS:
        from .complete_overflow import COMPLETE_BASELINE_TAG, EXPLORATORY_BASELINE_TAG
        baseline_tag = (EXPLORATORY_BASELINE_TAG if cfg.exploratory
                        else COMPLETE_BASELINE_TAG)
        if cfg.variant == "v8_hybrid_gate2":
            baseline_tag += "|hybridgate2"
    # This process never deserializes test references. Official test evaluation
    # has its own cache and entry point after protocol freeze.
    bstore = BaselineStore(run / "baseline_cache_trainval.json", cfg.inp,
                           A.calibrate_fn(env), A.static_fn(env), A.native_fn(env),
                           tag=baseline_tag)
    checkpoint_common = dict(
        variant=cfg.variant, kb_version="v8-complete" if cfg.variant in V8_VARIANTS else "v7",
        theta_hash=theta_hash, manifest_hash=man_hash, baseline_tag=baseline_tag,
        action_dim=int(env.action_space.shape[0]),
        pump_control="external policy" if cfg.variant == "v8_10d" else "INP native",
        hard_bypass_mask=cfg.variant == "v8_actionmask",
        native_rule_prior=cfg.variant in {"v8_nativeprior", "v8_nativeprior_5m"},
        gate2_rule_prior=cfg.variant == "v8_hybrid_gate2",
        control_time_step_s=(300 if cfg.variant == "v8_nativeprior_5m" else 900),
        research_status=experiment["research_status"],
        exploratory=bool(cfg.exploratory),
        hydraulic_gate_passed=experiment["hydraulic_gate_passed"],
    )

    def record(storm):
        rec = bstore.get(storm)
        if cfg.fixed_baseline is not None:
            rec = {**rec, "baseline_flooding": float(cfg.fixed_baseline)}
        return rec

    # Lazy baselines: compute on first use. Eager precompute of full train/val
    # is O(hours) on rain_scenarios; skip unless --eager-baselines.
    if getattr(cfg, "eager_baselines", False):
        warmup_refs = list({id(s): s for s in list(train_pool) + list(val)}.values())
        log.info("Precomputing baselines for %d train/val storms...", len(warmup_refs))
        for i, s in enumerate(warmup_refs, 1):
            bstore.get(s)
            if i % 25 == 0 or i == len(warmup_refs):
                log.info("  baselines %d/%d", i, len(warmup_refs))
    else:
        log.info("Lazy baselines (cache fills during train/eval)")

    # Cap validation size for selection evals (full test still at final_eval).
    max_val = int(getattr(cfg, "max_val_eval", 0) or 0)
    if max_val and len(val) > max_val:
        # Selection events must be identical across learning seeds.
        rng = np.random.default_rng(cfg.split_seed + 17)
        # stratified by rung when available
        by = {}
        for s in val:
            by.setdefault((s.meta or {}).get("rung", "R"), []).append(s)
        picked = []
        per = max(1, max_val // max(len(by), 1))
        for _, xs in sorted(by.items(), key=lambda item: str(item[0])):
            xs = sorted(xs, key=lambda s: s.storm_id)
            k = min(per, len(xs))
            idx = rng.choice(len(xs), size=k, replace=False)
            picked.extend(xs[i] for i in idx)
        val = picked[:max_val]
        log.info("Val capped to %d storms for selection evals", len(val))

    use_v8_train = cfg.variant in V8_VARIANTS and hasattr(agent, "end_episode")
    if use_v8_train and any((s.meta or {}).get("rung") for s in train_pool):
        sampler = StratifiedSampler(train_pool, seed=cfg.seed)
    else:
        sampler = StormSampler(train_pool, cfg.sampler, cfg.seed)

    best_sel, global_step, start_ep = -1e18, 0, 1
    if cfg.resume:
        ck = A.load_checkpoint(agent, cfg.resume)
        if getattr(agent, "legacy_safety_state_missing", False):
            env.close()
            raise RuntimeError("Cannot resume SAC-Lag: legacy checkpoint omitted safety state")
        for name, expected in (("variant", cfg.variant), ("manifest_hash", man_hash),
                               ("theta_hash", theta_hash)):
            if name in ck and ck[name] != expected:
                env.close()
                raise RuntimeError(
                    f"Cannot resume: checkpoint {name}={ck[name]!r}, runtime={expected!r}")
        if hasattr(sampler, "load_state_dict") and "sampler" in ck:
            sampler.load_state_dict(ck["sampler"])
        global_step = ck["global_step"]
        start_ep = ck["episode"] + 1
        best_sel = ck.get("best_sel", ck.get("sel", best_sel))

    t_start = time.time()
    for ep in range(start_ep, cfg.episodes + 1):
        st = sampler.next()
        rec = record(st)
        if use_v8_train:
            ref_n = rec.get("native") or rec["static"]
            L, global_step, ep_cost = A.train_one_episode_v8(
                env, agent, st, ref_n, global_step, cfg.warmup_steps,
                updates_per_step=cfg.updates_per_step)
            s = episode_summary(L, rec["baseline_flooding"])
            row = dict(
                phase="train", episode=ep, storm_id=st.storm_id, global_step=global_step,
                alpha=getattr(agent, "alpha_value", lambda: float("nan"))(),
                warmup=global_step <= cfg.warmup_steps,
                rain_total_mm=float(st.depth.sum()),
                lam=getattr(agent, "lam", float("nan")),
                ep_cost=ep_cost,
                rung=(st.meta or {}).get("rung"),
                family=(st.meta or {}).get("family"),
                **s, **relative(s, rec, cfg.cso_floor))
        else:
            L, global_step = A.train_one_episode(
                env, agent, st, rec["baseline_flooding"], global_step,
                cfg.warmup_steps, cfg.update_every)
            s = episode_summary(L, rec["baseline_flooding"])
            row = dict(
                phase="train", episode=ep, storm_id=st.storm_id, global_step=global_step,
                alpha=agent.alpha_value(), warmup=global_step <= cfg.warmup_steps,
                rain_total_mm=float(st.depth.sum()), **s, **relative(s, rec, cfg.cso_floor))
        append_row(run / "train_log.csv", row)

        if ep % cfg.eval_every == 0 and global_step > cfg.warmup_steps:
            vdf = evaluate(agent, env, val, bstore, "val", ep, cso_floor=cfg.cso_floor)
            parts = [vdf]
            if cfg.eval_train_k:
                parts.append(evaluate(agent, env, train[: cfg.eval_train_k], bstore,
                                      "train_eval", ep, cso_floor=cfg.cso_floor))
            pd.concat(parts).to_csv(run / "eval_log.csv", mode="a",
                                    header=not (run / "eval_log.csv").exists(), index=False)
            if use_v8_train:
                from .metrics_v8 import aggregate_native
                sel = validation_selection(vdf, strict=strict_selection)
                agg = aggregate_native(vdf)
                log.info("ep %d | v8 sel %.2f | val native-red macro %.1f | lam %.3f | %.0f min",
                         ep, sel, agg.get("cso_red_macro", float("nan")),
                         getattr(agent, "lam", float("nan")),
                         (time.time() - t_start) / 60)
            else:
                agg = aggregate(vdf)
                sel = selection_score(agg, cfg.r6_cap, cfg.flood_ratio_cap)
                log.info("ep %d | val CSO red macro %.1f%% worst %.1f%% | flood x%.2f | sel %.2f | %.0f min",
                         ep, agg["cso_red_macro"], agg["cso_red_worst"],
                         agg["flood_ratio_mean"], sel, (time.time() - t_start) / 60)
            if np.isfinite(sel) and sel > -1e8 and sel > best_sel:
                best_sel = sel
                A.save_checkpoint(agent, run / "checkpoints" / "best_val.pt",
                                  dict(**checkpoint_common, episode=ep, sel=sel, best_sel=sel,
                                       agg=agg, global_step=global_step,
                                       sampler=sampler.state_dict() if hasattr(sampler, "state_dict") else {},
                                       lam=getattr(agent, "lam", None)))
            elif not np.isfinite(sel) or sel <= -1e8:
                log.warning("ep %d: skipping best_val checkpoint (sel=%.2f)", ep, sel)
        if ep % cfg.ckpt_every == 0:
            A.save_checkpoint(agent, run / "checkpoints" / f"ep{ep}.pt",
                              dict(**checkpoint_common, episode=ep, global_step=global_step,
                                   best_sel=best_sel, lam=getattr(agent, "lam", None),
                                   sampler=sampler.state_dict() if hasattr(sampler, "state_dict") else {}))

    A.save_checkpoint(agent, run / "checkpoints" / "final.pt",
                      dict(**checkpoint_common, episode=cfg.episodes, global_step=global_step,
                           best_sel=best_sel, lam=getattr(agent, "lam", None),
                           sampler=sampler.state_dict() if hasattr(sampler, "state_dict") else {}))

    best_path = run / "checkpoints" / "best_val.pt"
    if best_path.exists():
        A.load_checkpoint(agent, best_path)
    # Test evaluation must be explicitly requested after the protocol is frozen.
    if use_v8_train and strict_selection and not best_path.exists():
        env.close()
        raise RuntimeError("No safety-feasible validation checkpoint; stop before final evaluation")
    final_storms = _balanced_rung_cap(val_full, cfg.max_final_val_eval)
    log.info("Final eval on all %d validation storms; test data were not loaded", len(final_storms))
    frames = [evaluate(agent, env, final_storms, bstore, "final", None, cso_floor=cfg.cso_floor)]
    fdf = pd.concat(frames)
    fdf.to_csv(run / "final_eval.csv", index=False)
    from .metrics_v8 import aggregate_native
    aggregate_final = aggregate_native if use_v8_train else aggregate
    final_agg = {sp: aggregate_final(fdf[fdf.split == sp]) for sp in ("train", "val", "test")
                 if (fdf.split == sp).any()}
    final_agg["selection_on_train"] = split_info["selection_on_train"]
    (run / "final_agg.json").write_text(json.dumps(final_agg, indent=1, default=float))
    log.info("Done. Final aggregates: %s", json.dumps(final_agg, default=float)[:600])
    env.close()


if __name__ == "__main__":
    main()

"""Thin bridge to app.py — the ONLY multistorm module that imports app."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np
import torch

import app as _app
from .metrics import episode_summary
from .storms import Storm


def build(seed: int = 0):
    """Construct exactly what Trial 7 constructs."""
    return _app.build_stack(seed=seed, verbose=False)


def _action_tensor(values):
    return torch.tensor(values, dtype=torch.float32, device=_app.device)


def calibrate_fn(env) -> Callable[[Storm], float]:
    """
    Mean per-step flooding with gates=0.5, pumps=ON (same definition as
    app.run_baseline_episode). Uses the existing env to avoid pyswmm's
    MultiSimulationError (only one Simulation per process).
    """
    def _calibrate(storm: Storm) -> float:
        previous_projection = env.use_projection
        action = _action_tensor(
            [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0])
        obs, _ = env.reset(options={
            "storm": storm,
            "baseline_flooding": 0.0,
            "native": False,
            "physical_rain": bool(getattr(env, "physical_rain", False)),
            "use_projection": False,
        })
        done = False
        while not done:
            obs, _, term, trunc, _ = env.step(action)
            done = bool(term or trunc)
        fl = env.get_episode_log()["flooding"]
        env.use_projection = previous_projection
        return float(np.mean(fl))
    return _calibrate


def static_fn(env) -> Callable:
    """Run constant action (0.5×7 gates, 1.0×3 pumps) through the normal env path."""
    def _static(storm: Storm, baseline_flooding: float) -> dict:
        previous_projection = env.use_projection
        action = _action_tensor(
            [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0])
        obs, _ = env.reset(options={
            "storm": storm,
            "baseline_flooding": baseline_flooding,
            "native": False,
            "physical_rain": bool(getattr(env, "physical_rain", False)),
            "use_projection": False,
        })
        done = False
        while not done:
            obs, _, term, trunc, _ = env.step(action)
            done = bool(term or trunc)
        log = env.get_episode_log()
        env.use_projection = previous_projection
        return episode_summary(log, baseline_flooding)
    return _static


def native_fn(env) -> Callable:
    """Native SWMM [CONTROLS] reference (no target_setting writes / no projection)."""
    def _native(storm: Storm) -> dict:
        previous_projection = env.use_projection
        action = _action_tensor(
            [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0])
        obs, _ = env.reset(options={
            "storm": storm,
            "baseline_flooding": _app.BASELINE_FLOODING,
            "native": True,
            "physical_rain": bool(getattr(env, "physical_rain", False)),
        })
        done = False
        while not done:
            obs, _, term, trunc, _ = env.step(action)
            done = bool(term or trunc)
        log = env.get_episode_log()
        env.use_projection = previous_projection
        return episode_summary(log, _app.BASELINE_FLOODING)
    return _native


def train_one_episode(env, agent, storm, baseline_flooding, global_step,
                      warmup_steps, update_every):
    """
    Verbatim extraction of Trial 7's per-episode training loop,
    plus reset(options=...) for multi-storm support.
    """
    action_dim = env.action_space.shape[0]
    obs, _ = env.reset(options={
        "storm": storm,
        "baseline_flooding": baseline_flooding,
        "physical_rain": bool(getattr(env, "physical_rain", False)),
    })
    done = False
    while not done:
        if global_step < warmup_steps:
            action = _app.to_device(np.random.uniform(0.0, 1.0, action_dim))
        else:
            action = agent.select_action(obs)

        next_obs, reward, terminated, truncated, _ = env.step(action)
        done = bool(terminated or truncated)
        agent.store(obs, action, reward, next_obs, done)
        global_step += 1
        if global_step % update_every == 0:
            agent.update()
        obs = next_obs

    return env.get_episode_log(), global_step


def save_checkpoint(agent, path, extra: dict | None = None):
    agent.save(str(path), extra or {})


def load_checkpoint(agent, path) -> dict:
    return agent.load(str(path))


def run_baseline_episode_for(storm: Storm) -> float:
    return float(_app.run_baseline_episode(storm.depth))


def build_v8(seed, theta=None, use_projection=True, lagrangian=True, rain_features=True,
             cost_limit=0.05, lam_init=0.5, lam_lr=0.02, complete_overflow=False,
             policy_dim=7, topology_aware=True, w_store=2.0, native_pumps=True,
             policy_controls_pumps=False, hard_bypass_mask=False,
             input_file="7MPF_CSO_08.inp"):
    """P11 — v8 stack: KnowledgeBaseV8 + 7-D SAC-Lag + physical-rain-ready env."""
    import pandas as pd
    import torch
    from research.topology import to_kb_dict
    from multistorm.kb_v8 import KnowledgeBaseV8
    from multistorm.agents_lag import SACLagAgent

    network = json.loads(Path("configs/v8_network.json").read_text())
    actual_inp_sha = hashlib.sha256(Path(input_file).read_bytes()).hexdigest()
    if actual_inp_sha.lower() != network["inp_sha256"].lower():
        raise ValueError(
            "The v8 topology/geometry configuration does not match the selected INP: "
            f"{actual_inp_sha} != {network['inp_sha256']}")

    np.random.seed(seed)
    torch.manual_seed(seed)
    nodes = pd.read_csv(network["diag_nodes_csv"])
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}
    kb_class, env_class = KnowledgeBaseV8, _app.NeurosymbolicSWMMEnv
    if complete_overflow:
        from .complete_overflow import CompleteOverflowKB, CompleteOverflowEnv
        kb_class, env_class = CompleteOverflowKB, CompleteOverflowEnv
    topology = to_kb_dict(pd.read_csv(network["gate_topology_csv"]))
    if not topology_aware:
        # Controlled -topology ablation: retain the same v8 state, reward,
        # thresholds, agent and action dimensions, but give every gate the
        # same global context instead of gate-specific graph reachability.
        global_context = {
            name: sorted({item for ctx in topology.values() for item in ctx[name]})
            for name in ("risk_up", "storage_down", "weirs_down", "cso_outfalls_down")
        }
        topology = {g: {k: list(v) for k, v in global_context.items()} for g in range(7)}
    kb_kwargs = dict(
        theta=theta, use_rain_features=rain_features,
        w_store=w_store, horizon=288 if complete_overflow else 287,
        freeze_pumps=not policy_controls_pumps,
    )
    if complete_overflow:
        kb_kwargs["hard_bypass_mask"] = hard_bypass_mask
    kb = kb_class(full, list(nodes[nodes.junction].id), topology, **kb_kwargs)
    env = env_class(
        kb, input_file=input_file, use_projection=use_projection, policy_dim=policy_dim,
        time_limit_truncation=True, real_only=True,
        native_pumps=native_pumps,
        external_gate_control=not complete_overflow,
        policy_controls_pumps=policy_controls_pumps,
    )
    env.physical_rain = True
    agent = SACLagAgent(
        env.observation_space.shape[0], policy_dim,
        cost_limit=cost_limit if lagrangian else 1e9,
        lam_init=lam_init if lagrangian else 0.0,
        lam_lr=lam_lr if lagrangian else 0.0,
        lr=1e-4, gamma=0.99, tau=0.005, hidden=256,
        buffer_cap=50_000, batch_size=256,
        correct_action_logprob=True,
    )
    return env, agent, kb


def train_one_episode_v8(env, agent, storm, ref_native, global_step, warmup,
                         updates_per_step=0.25):
    """P12 — v8 training episode with cost-aware SAC-Lag updates."""
    obs, _ = env.reset(options=dict(
        storm=storm, physical_rain=True, baseline_flooding=0.0,
        reference_cso=ref_native["cso_total"],
    ))
    # Match the learned constraint to the published per-event flood cap.
    # Legacy summaries are sampled CFS totals; the complete objective is m3.
    flood_m3 = float(ref_native["flood_total"])
    if ref_native.get("volume_units") != "m3":
        flood_m3 *= 900.0 * 0.028316846592
    agent.cost_limit = (1.02 * flood_m3 + 10.0) / float(env.kb.v_scale)
    ep_cost, acc, done = 0.0, 0.0, False
    action_dim = int(env.action_space.shape[0])
    while not done:
        if global_step < warmup:
            a = np.random.uniform(0, 1, action_dim)
        else:
            a = agent.select_action(obs).detach().cpu().numpy()
        nobs, r, term, trunc, info = env.step(a)
        agent.store(obs, a, r, info.get("cost", 0.0), nobs, term)
        ep_cost += float(info.get("cost", 0.0))
        global_step += 1
        obs = nobs
        done = bool(term or trunc)
        if global_step > warmup:
            acc += updates_per_step
            while acc >= 1.0:
                agent.update()
                acc -= 1.0
    agent.end_episode(ep_cost)
    return env.get_episode_log(), global_step, ep_cost

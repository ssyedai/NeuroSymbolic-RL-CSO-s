"""Acceptance tests for APP_PATCHES P1–P8 (opt-in v8 flags; defaults keep v7).

One Simulation per process (pyswmm) — all tests share a module-scoped env.
"""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("pyswmm")

import app  # noqa: E402


@pytest.fixture(scope="module")
def env():
    e, _, _ = app.build_stack(seed=0, verbose=False)
    yield e
    e.close()


def test_defaults_match_v7_action_space(env):
    assert env.action_space.shape == (10,)
    assert env.use_projection is True
    assert env.time_limit_truncation is False
    assert env.real_only is False


def test_policy_dim_7_appends_pumps(env):
    env.policy_dim = 7
    env.reset()
    env.step(np.full(7, 0.5))
    proj7 = env.ep_proj_actions[-1].copy()
    env.reset()
    env.step(np.r_[np.full(7, 0.5), np.ones(3)])
    proj10 = env.ep_proj_actions[-1].copy()
    env.policy_dim = 10
    np.testing.assert_allclose(proj7, proj10, atol=1e-9)


def test_use_projection_false_leaves_gates_pumps_on(env):
    env.use_projection = False
    env.reset()
    raw = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0, 0.0, 0.0])
    env.step(raw)
    proj = env.ep_proj_actions[-1]
    env.use_projection = True
    np.testing.assert_allclose(proj[:7], raw[:7], atol=1e-9)
    np.testing.assert_allclose(proj[7:], np.ones(3), atol=1e-9)


def test_explicit_10d_policy_can_control_pumps(env):
    old = (env.use_projection, env.native_pumps, env.policy_controls_pumps)
    try:
        env.use_projection = False
        env.native_pumps = False
        env.policy_controls_pumps = True
        env.reset()
        raw = np.array([0.5] * 7 + [0.2, 0.4, 0.6])
        env.step(raw)
        np.testing.assert_allclose(env.ep_proj_actions[-1], raw, atol=1e-9)
    finally:
        env.use_projection, env.native_pumps, env.policy_controls_pumps = old


def test_time_limit_truncation(env):
    env.time_limit_truncation = True
    env.reset()
    env.t = env.T
    _, _, term, trunc, _ = env.step(np.full(10, 0.5))
    env.time_limit_truncation = False
    assert term is False
    assert trunc is True


def test_real_only_requires_physical_rain(env):
    env.real_only = True
    with pytest.raises(RuntimeError, match="real_only"):
        env.reset(options={"physical_rain": False})
    env.real_only = False

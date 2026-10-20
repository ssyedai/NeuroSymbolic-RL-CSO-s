"""Run on YOUR machine (needs torch and app.py importable). Skipped automatically otherwise."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("app")
from multistorm.agents_lag import SACLagAgent          # noqa: E402
from app import Actor                                  # noqa: E402


def make(obs_dim=12, act_dim=7, **kw):
    return SACLagAgent(obs_dim, act_dim, batch_size=32, buffer_cap=500, **kw)


def fill(agent, n=200, obs_dim=12, act_dim=7, cost=0.0):
    for _ in range(n):
        agent.store(np.random.randn(obs_dim), np.random.rand(act_dim), -np.random.rand(), cost,
                    np.random.randn(obs_dim), 0.0)


def test_update_runs_and_changes_weights():
    a = make(); fill(a)
    w0 = [p.detach().clone() for p in a.actor.parameters()]
    for _ in range(5):
        a.update()
    assert any((p.detach() != q).any() for p, q in zip(a.actor.parameters(), w0))
    assert a.target_entropy == -7.0


def test_dual_ascent_and_clipping():
    a = make(cost_limit=0.05, lam_init=0.5, lam_lr=0.1, lam_max=1.0)
    # 0.5 + 0.1*(5.05-0.05) = 1.0 → clips at lam_max
    a.end_episode(5.05); assert a.lam == 1.0
    a.end_episode(0.0); assert abs(a.lam - (1.0 - 0.1 * 0.05)) < 1e-9
    for _ in range(50):
        a.end_episode(0.0)
    assert a.lam >= 0.0


def test_cost_critic_learns_high_cost_actions():
    a = make(obs_dim=4, act_dim=7)
    for _ in range(400):
        act = np.random.rand(7)
        a.store(np.zeros(4), act, 0.0, float(act[3] > 0.5), np.zeros(4), 1.0)    # cost iff gate 3 > .5, terminal
    for _ in range(300):
        a.update()
    s = torch.zeros(1, 4)
    hi = torch.tensor([[0.5] * 3 + [0.95] + [0.5] * 3]); lo = torch.tensor([[0.5] * 3 + [0.05] + [0.5] * 3])
    dev = next(a.cost_critic.parameters()).device
    q = lambda act: float(torch.max(*a.cost_critic(s.to(dev), act.to(dev))))
    assert q(hi) > q(lo)


def test_checkpoint_restores_safety_state(tmp_path):
    a = make(lam_init=3.0, cost_limit=0.2, lam_lr=0.03)
    fill(a)
    a.update()
    a.end_episode(1.0)
    path = tmp_path / "lag.pt"
    a.save(path, {"episode": 7})
    b = make(lam_init=0.0)
    assert b.load(path)["episode"] == 7
    assert (b.lam, b.cost_limit, b.lam_lr) == (a.lam, a.cost_limit, a.lam_lr)
    assert b.lam_log == a.lam_log and not b.legacy_safety_state_missing
    assert len(b.replay) == len(a.replay)
    np.testing.assert_array_equal(b.replay.o[:b.replay.n], a.replay.o[:a.replay.n])
    for p, q in zip(a.cost_critic.parameters(), b.cost_critic.parameters()):
        assert torch.equal(p, q)
    for p, q in zip(a.cost_target.parameters(), b.cost_target.parameters()):
        assert torch.equal(p, q)
    assert b.cost_opt.state_dict()["state"]


def test_checkpoint_restores_rng_for_exact_resume(tmp_path):
    a = make(); fill(a, n=40)
    path = tmp_path / "rng.pt"
    a.save(path)
    expected_np = np.random.random(5)
    expected_torch = torch.rand(5)
    b = make()
    b.load(path)
    np.testing.assert_array_equal(np.random.random(5), expected_np)
    assert torch.equal(torch.rand(5), expected_torch)


def test_unit_interval_logprob_includes_affine_jacobian_opt_in():
    legacy = Actor(3, 7, hidden=8, correct_action_logprob=False)
    corrected = Actor(3, 7, hidden=8, correct_action_logprob=True)
    corrected.load_state_dict(legacy.state_dict())
    obs = torch.zeros(4, 3)
    torch.manual_seed(123); action0, lp0 = legacy.sample(obs)
    torch.manual_seed(123); action1, lp1 = corrected.sample(obs)
    assert torch.equal(action0, action1)
    expected = torch.full_like(lp0, 7 * np.log(2.0))
    assert torch.allclose(lp1 - lp0, expected, atol=1e-6)

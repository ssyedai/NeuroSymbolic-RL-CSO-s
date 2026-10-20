"""Generate and verify Trial 7 golden trajectory (30 fixed steps)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden_trial7.npz"


def _run_golden(n_steps: int = 30):
    import app

    # Seed everything as specified
    np.random.seed(0)
    torch.manual_seed(0)
    import random
    random.seed(0)

    env, agent, kb = app.build_stack(
        seed=0,
        rainfall_path=str(ROOT / "data/unused/rain/raindata.csv"),
        verbose=False,
    )
    assert kb.baseline_flooding == 7183.0

    rng = np.random.default_rng(123)
    actions = rng.uniform(0.0, 1.0, size=(n_steps, 10)).astype(np.float64)

    obs, _ = env.reset()
    rewards, cso, flood, proj, obs_snip = [], [], [], [], []
    obs_snip.append(obs.detach().cpu().numpy()[:50].copy())

    for i in range(n_steps):
        a = app.to_device(actions[i])
        obs, reward, terminated, truncated, _ = env.step(a)
        rewards.append(reward)
        cso.append(env.ep_cso_flows[-1])
        flood.append(env.ep_flooding[-1])
        proj.append(env.ep_proj_actions[-1].copy())
        obs_snip.append(obs.detach().cpu().numpy()[:50].copy())
        if terminated or truncated:
            break

    env.close()
    return {
        "reward": np.asarray(rewards, dtype=np.float64),
        "cso_flow": np.asarray(cso, dtype=np.float64),
        "flooding": np.asarray(flood, dtype=np.float64),
        "actions_projected": np.asarray(proj, dtype=np.float64),
        "obs_first50": np.asarray(obs_snip, dtype=np.float64),
        "actions_raw": actions,
    }


def make_golden():
    data = _run_golden()
    np.savez_compressed(GOLDEN, **data)
    print(f"Wrote {GOLDEN}")
    print(f"  reward sum={data['reward'].sum():.6f}  cso sum={data['cso_flow'].sum():.3f}")


def test_golden_trial7():
    if not GOLDEN.exists():
        make_golden()
    ref = np.load(GOLDEN)
    cur = _run_golden()
    for k in ("reward", "cso_flow", "flooding", "actions_projected", "obs_first50"):
        assert np.allclose(cur[k], ref[k], atol=1e-6, equal_nan=True), (
            f"mismatch on {k}: max abs diff="
            f"{np.nanmax(np.abs(cur[k] - ref[k]))}"
        )


if __name__ == "__main__":
    make_golden()

"""SAC with a cost critic and a Lagrange multiplier (SAC-Lag). 7-D policy; pumps are appended by the env.

NOT executed in the authoring sandbox (no torch there) - run tests/test_agents_lag.py on your machine first.
Adjust the import below if your SACAgent/Critic live in another module.
"""
from __future__ import annotations
import random
import numpy as np
import torch
import torch.nn.functional as F
import torch.nn.utils as nn_utils
import torch.optim as optim
import warnings
from app import SACAgent, Critic, device
from multistorm.replay import RingReplay


class SACLagAgent(SACAgent):
    def __init__(self, obs_dim, action_dim=7, cost_limit=0.05, lam_init=0.5, lam_lr=0.02, lam_max=50.0,
                 target_entropy=None, **kw):
        super().__init__(obs_dim, action_dim, **kw)
        hid, lr = kw.get("hidden", 256), kw.get("lr", 1e-4)
        self.cost_critic = Critic(obs_dim, action_dim, hid).to(device)
        self.cost_target = Critic(obs_dim, action_dim, hid).to(device)
        self.cost_target.load_state_dict(self.cost_critic.state_dict())
        self.cost_opt = optim.Adam(self.cost_critic.parameters(), lr=lr)
        self.replay = RingReplay(kw.get("buffer_cap", 50_000), obs_dim, action_dim)
        self.target_entropy = float(target_entropy) if target_entropy is not None else -float(action_dim)
        self.cost_limit, self.lam, self.lam_lr, self.lam_max = cost_limit, lam_init, lam_lr, lam_max
        self.lam_log: list[float] = []

    @staticmethod
    def _np(x):
        return x.detach().cpu().numpy() if isinstance(x, torch.Tensor) else np.asarray(x, np.float32)

    def store(self, s, a, r, c, ns, terminated):
        """`terminated` must be the TRUE termination flag; a time-limit truncation is stored as 0 (bootstraps)."""
        self.replay.push(self._np(s), self._np(a), r, c, self._np(ns), float(terminated))

    def end_episode(self, ep_cost: float):
        self.lam = float(np.clip(self.lam + self.lam_lr * (ep_cost - self.cost_limit), 0.0, self.lam_max))
        self.lam_log.append(self.lam)

    def save(self, path: str, extra: dict | None = None):
        """Persist the safety learner as well as the inherited reward learner."""
        super().save(path, extra)
        payload = torch.load(path, map_location=device, weights_only=False)
        payload["sac_lag"] = dict(
            version=2, cost_critic=self.cost_critic.state_dict(),
            cost_target=self.cost_target.state_dict(), cost_opt=self.cost_opt.state_dict(),
            lam=self.lam, cost_limit=self.cost_limit, lam_lr=self.lam_lr,
            lam_max=self.lam_max, target_entropy=self.target_entropy,
            lam_log=self.lam_log, replay=self.replay.state_dict(),
            rng=dict(
                python=random.getstate(), numpy=np.random.get_state(),
                torch=torch.get_rng_state(),
                cuda=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
            ),
        )
        torch.save(payload, path)

    def load(self, path: str) -> dict:
        payload = torch.load(path, map_location=device, weights_only=False)
        extra = super().load(path)
        state = payload.get("sac_lag")
        self.legacy_safety_state_missing = state is None
        if state is None:
            warnings.warn("Legacy checkpoint lacks cost critics and multiplier state; "
                          "policy evaluation is possible but safety training cannot resume faithfully",
                          RuntimeWarning)
            return extra
        self.cost_critic.load_state_dict(state["cost_critic"])
        self.cost_target.load_state_dict(state["cost_target"])
        self.cost_opt.load_state_dict(state["cost_opt"])
        for name in ("lam", "cost_limit", "lam_lr", "lam_max", "target_entropy"):
            setattr(self, name, float(state[name]))
        self.lam_log = list(state.get("lam_log", []))
        if "replay" not in state or "rng" not in state:
            self.legacy_safety_state_missing = True
            warnings.warn("Checkpoint lacks replay/RNG state; evaluation is valid but exact training resume is not",
                          RuntimeWarning)
            return extra
        self.replay.load_state_dict(state["replay"])
        rng = state["rng"]
        random.setstate(rng["python"])
        np.random.set_state(rng["numpy"])
        torch.set_rng_state(rng["torch"].cpu())
        if torch.cuda.is_available() and rng.get("cuda") is not None:
            torch.cuda.set_rng_state_all(rng["cuda"])
        return extra

    def _soft(self, net, tgt):
        for p, pt in zip(net.parameters(), tgt.parameters()):
            pt.data.copy_(self.tau * p.data + (1.0 - self.tau) * pt.data)

    def update(self):
        if len(self.replay) < self.batch_size:
            return
        t = lambda x: torch.as_tensor(x, device=device)
        s, a, r, c, ns, d = [t(x) for x in self.replay.sample(self.batch_size)]
        alpha = self.log_alpha.exp().detach()
        with torch.no_grad():
            na, lp = self.actor.sample(ns)
            y = r + self.gamma * (1.0 - d) * (self.critic_target.min_q(ns, na) - alpha * lp)
            yc = c + self.gamma * (1.0 - d) * torch.max(*self.cost_target(ns, na))
        q1, q2 = self.critic(s, a)
        self.critic_opt.zero_grad(); (F.mse_loss(q1, y) + F.mse_loss(q2, y)).backward()
        nn_utils.clip_grad_norm_(self.critic.parameters(), self.MAX_GRAD_NORM); self.critic_opt.step()
        c1, c2 = self.cost_critic(s, a)
        self.cost_opt.zero_grad(); (F.mse_loss(c1, yc) + F.mse_loss(c2, yc)).backward()
        nn_utils.clip_grad_norm_(self.cost_critic.parameters(), self.MAX_GRAD_NORM); self.cost_opt.step()
        a_new, lp_new = self.actor.sample(s)
        alpha = self.log_alpha.exp()
        qr = self.critic.min_q(s, a_new)
        qc = torch.max(*self.cost_critic(s, a_new))
        loss_pi = (alpha.detach() * lp_new - (qr - self.lam * qc) / (1.0 + self.lam)).mean()
        self.actor_opt.zero_grad(); loss_pi.backward()
        nn_utils.clip_grad_norm_(self.actor.parameters(), self.MAX_GRAD_NORM); self.actor_opt.step()
        al = -(self.log_alpha * (lp_new + self.target_entropy).detach()).mean()
        self.alpha_opt.zero_grad(); al.backward(); self.alpha_opt.step()
        self._soft(self.critic, self.critic_target); self._soft(self.cost_critic, self.cost_target)
        self.train_log["critic_loss"].append(float(F.mse_loss(q1, y).detach()))
        self.train_log["actor_loss"].append(float(loss_pi.detach()))
        self.train_log["alpha"].append(float(self.log_alpha.exp().detach()))

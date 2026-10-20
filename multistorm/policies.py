# multistorm/policies.py
"""Non-learned reference policies with SACAgent-compatible select_action."""
from __future__ import annotations

import numpy as np
import torch

import app as _app


class ConstantPolicy:
    """B0 / B2: same select_action signature as SACAgent so evaluate() works unchanged."""

    def __init__(self, gates=0.5, pumps=1.0):
        self.a = np.array([gates] * 7 + [pumps] * 3, dtype=np.float32)

    def select_action(self, obs, deterministic=True):
        return torch.tensor(self.a, dtype=torch.float32, device=_app.device)

    def alpha_value(self) -> float:
        return float("nan")

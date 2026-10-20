"""Numpy ring-buffer replay with cost (O(1) sampling; replaces random.sample over a deque)."""
from __future__ import annotations
import numpy as np


class RingReplay:
    def __init__(self, cap: int, obs_dim: int, act_dim: int):
        self.cap, self.i, self.n = int(cap), 0, 0
        self.o = np.zeros((cap, obs_dim), np.float32); self.no = np.zeros_like(self.o)
        self.a = np.zeros((cap, act_dim), np.float32)
        self.r = np.zeros((cap, 1), np.float32); self.c = np.zeros_like(self.r); self.d = np.zeros_like(self.r)

    def push(self, o, a, r, c, no, d):
        j = self.i
        self.o[j], self.a[j], self.r[j], self.c[j], self.no[j], self.d[j] = o, a, r, c, no, d
        self.i, self.n = (j + 1) % self.cap, min(self.n + 1, self.cap)

    def __len__(self):
        return self.n

    def sample(self, batch: int):
        k = np.random.randint(0, self.n, batch)
        return self.o[k], self.a[k], self.r[k], self.c[k], self.no[k], self.d[k]

    def state_dict(self) -> dict:
        """Compact exact state for deterministic training resume."""
        used = self.cap if self.n == self.cap else self.n
        return dict(
            version=1, cap=self.cap, i=self.i, n=self.n,
            o=self.o[:used].copy(), a=self.a[:used].copy(),
            r=self.r[:used].copy(), c=self.c[:used].copy(),
            no=self.no[:used].copy(), d=self.d[:used].copy(),
        )

    def load_state_dict(self, state: dict) -> None:
        if int(state.get("version", 0)) != 1:
            raise ValueError("Unsupported replay checkpoint version")
        n, cap = int(state["n"]), int(state["cap"])
        if cap != self.cap or not 0 <= n <= self.cap:
            raise ValueError(
                f"Replay shape mismatch: checkpoint cap/n={cap}/{n}, runtime cap={self.cap}")
        used = self.cap if n == self.cap else n
        arrays = (("o", self.o), ("a", self.a), ("r", self.r),
                  ("c", self.c), ("no", self.no), ("d", self.d))
        for name, target in arrays:
            source = np.asarray(state[name], dtype=np.float32)
            if source.shape != target[:used].shape:
                raise ValueError(
                    f"Replay {name} shape mismatch: {source.shape} != {target[:used].shape}")
            target.fill(0.0)
            target[:used] = source
        self.n, self.i = n, int(state["i"])
        if not 0 <= self.i < self.cap:
            raise ValueError(f"Invalid replay cursor {self.i}")

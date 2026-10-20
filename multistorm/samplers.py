"""Rung-stratified storm sampler (each rung equally likely; shuffled cycle inside a rung)."""
from __future__ import annotations
import numpy as np


def default_key(s):
    meta = s.get("meta", {}) if isinstance(s, dict) else getattr(s, "meta", {})
    return meta.get("rung", "R")


class StratifiedSampler:
    def __init__(self, storms, key=default_key, seed=0, rung_weights: dict | None = None):
        self.rng = np.random.default_rng(seed)
        self.groups: dict = {}
        for s in storms:
            self.groups.setdefault(key(s), []).append(s)
        self.rungs = sorted(self.groups, key=str)
        w = np.array([(rung_weights or {}).get(r, 1.0) for r in self.rungs], float)
        self.p = w / w.sum()
        self.queues = {r: [] for r in self.rungs}
        self.counts = {r: 0 for r in self.rungs}

    def next(self):
        r = self.rungs[int(self.rng.choice(len(self.rungs), p=self.p))]
        if not self.queues[r]:
            self.queues[r] = [int(i) for i in self.rng.permutation(len(self.groups[r]))]
        self.counts[r] += 1
        return self.groups[r][self.queues[r].pop()]

    def state_dict(self):
        return dict(rng=self.rng.bit_generator.state, queues={str(k): list(v) for k, v in self.queues.items()},
                    counts={str(k): int(v) for k, v in self.counts.items()})

    def load_state_dict(self, d):
        self.rng.bit_generator.state = d["rng"]
        self.queues = {r: list(d["queues"][str(r)]) for r in self.rungs}
        self.counts = {r: d["counts"][str(r)] for r in self.rungs}

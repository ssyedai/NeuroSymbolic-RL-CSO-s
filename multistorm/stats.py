# multistorm/stats.py
from __future__ import annotations
import numpy as np
from scipy import stats


def iqm(x):
    return float(stats.trim_mean(np.asarray(x, float), 0.25))


def hier_bootstrap(M: np.ndarray, stat=np.mean, n_boot=10_000, alpha=0.05, seed=0):
    """M: (n_seeds, n_events). Resample events AND seeds; average seeds; apply stat over events."""
    rng = np.random.default_rng(seed)
    S, E = M.shape
    point = stat(M.mean(axis=0))
    boots = np.empty(n_boot)
    for b in range(n_boot):
        si, ei = rng.integers(0, S, S), rng.integers(0, E, E)
        boots[b] = stat(M[np.ix_(si, ei)].mean(axis=0))
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(point), (float(lo), float(hi))


def paired_compare(A: np.ndarray, B: np.ndarray, higher_is_better=True, n_boot=10_000, seed=0) -> dict:
    """A, B: (n_seeds, n_events), same events in the same order."""
    d = A.mean(0) - B.mean(0)
    if not higher_is_better:
        d = -d
    try:
        p = 1.0 if np.all(d == 0) else float(stats.wilcoxon(d, alternative="two-sided", zero_method="wilcox").pvalue)
    except ValueError:
        p = float("nan")
    nz = d[d != 0]
    ranks = stats.rankdata(np.abs(nz)) if nz.size else np.array([])
    rbc = float((ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum()) if nz.size else 0.0
    sgn = 1 if higher_is_better else -1
    D = sgn * (A - B)
    point, ci = hier_bootstrap(D, np.mean, n_boot, seed=seed)
    return dict(n_events=int(d.size), mean_diff=point, mean_diff_ci=ci,
                median_diff=float(np.median(d)), p_wilcoxon=p, rank_biserial=rbc,
                prob_improvement=float((d > 0).mean() + 0.5 * (d == 0).mean()))


def holm(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(((k, v) for k, v in pvals.items() if v == v), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, v) in enumerate(items):
        running = max(running, min(1.0, (m - i) * v))
        out[k] = running
    return {**{k: float("nan") for k in pvals if k not in out}, **out}


def performance_profile(x: np.ndarray, taus: np.ndarray) -> np.ndarray:
    """Fraction of events with score >= tau."""
    x = np.asarray(x, float)
    return np.array([(x >= t).mean() for t in taus])

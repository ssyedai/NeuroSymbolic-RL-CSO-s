"""CSO-onset amplification factor: smallest k at which the network spills under TRUE native control."""
from __future__ import annotations
import numpy as np

GRID = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)


def find_onset_factor(run_cso, depth, floor=1.0, grid=GRID, tol=0.05):
    """run_cso(depth_array) -> cso_total. Verify monotonicity before bisection.

    Returns (k_onset or None, evaluations dict). None means no CSO even at max(grid).
    Cost: len(grid) worst case + ~3-4 bisection runs.
    """
    depth = np.asarray(depth, float)
    cache = {}

    def f(k):
        k = float(k)
        if k not in cache:
            cache[k] = float(run_cso(depth * k))
        return cache[k]

    grid = tuple(float(k) for k in grid)
    values = [f(k) for k in grid]
    numerical_tol = max(1e-6, 0.01 * float(floor))
    drops = [(grid[i - 1], grid[i], values[i - 1], values[i])
             for i in range(1, len(grid))
             if values[i] + numerical_tol < values[i - 1]]
    if drops:
        raise RuntimeError(
            "CSO dose response is non-monotone; onset bisection is invalid. "
            f"First drop (k0,k1,cso0,cso1)={drops[0]}")

    prev = None
    for k, value in zip(grid, values):
        if value >= floor:
            if prev is None:
                return k, cache
            lo, hi = prev, k
            while (hi - lo) / lo > tol:
                mid = round((lo * hi) ** 0.5, 4)
                if f(mid) >= floor:
                    hi = mid
                else:
                    lo = mid
            return hi, cache
        prev = k
    return None, cache

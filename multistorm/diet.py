"""Training-pool filters for scenario diets D1–D5 (AGENTS.md T08)."""
from __future__ import annotations

DIET_FAMILIES = {
    "D1_flat2": {"R", "F"},
    "D2_ladder100": {"R", "T", "C"},
    "D3_ladder1000": {"R", "T", "C"},
    "D4_real": {"R"},
    "D5_all": {"R", "T", "C", "F"},
}


def within_training_ceiling(meta: dict, ceiling: float) -> bool:
    """Honor fitted severity AND declared T rung; missing legacy metadata is allowed."""
    if not np_isfinite(ceiling) or float(ceiling) <= 0:
        raise ValueError('Training ceiling must be finite and positive')
    values=[]
    anchor=meta.get('T_anchor')
    if anchor is None and meta.get('family') in {'R','C','F'}:
        return False  # explicit research scenarios need a checkable severity
    if anchor is not None:
        if not np_isfinite(anchor) or float(anchor)<0: return False
        values.append(float(anchor))
    rung=str(meta.get('rung') or '')
    if meta.get('family')=='T' or rung.startswith('T'):
        try:
            nominal=float(rung[1:])
        except ValueError:
            return False
        if not np_isfinite(nominal) or nominal<=0: return False
        values.append(nominal)
        target=meta.get('T_target')
        if target is not None:
            if not np_isfinite(target) or float(target)<=0: return False
            values.append(float(target))
    return not values or max(values)<=float(ceiling)


def eligible_for_training(storm, diet: str, train_max_T: float,
                          allow_test_only_rungs: bool,
                          controllable: set | None = None) -> bool:
    """Train-pool rule: split==train, family in diet, T_anchor ≤ ceiling, not test_only (unless allowed)."""
    if storm.split != "train":
        return False
    meta = getattr(storm, "meta", {}) or {}
    fam = meta.get("family")
    if fam is None:
        # Pre-v8 catalogs: treat as observed real
        fam = "R"
    allowed = DIET_FAMILIES.get(diet, DIET_FAMILIES["D2_ladder100"])
    if fam not in allowed:
        return False
    if meta.get("test_only") and not (allow_test_only_rungs and diet == "D3_ladder1000"):
        return False
    if not within_training_ceiling(meta, train_max_T):
        return False
    if controllable is not None and storm.storm_id not in controllable:
        # Also allow by parent id if children share eligibility
        parent = meta.get("parent") or storm.storm_id
        if parent not in controllable and storm.storm_id not in controllable:
            return False
    return True


def np_isfinite(x) -> bool:
    try:
        import math
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def filter_train_pool(storms, diet, train_max_T, allow_test_only_rungs,
                      controllable=None, bad_rungs=None):
    """If bad_rungs is set (from G2), drop those rungs from training eligibility."""
    bad = set(bad_rungs or [])
    out = []
    for s in storms:
        if not eligible_for_training(
                s, diet, train_max_T, allow_test_only_rungs, controllable):
            continue
        rung = (s.meta or {}).get("rung")
        if rung in bad:
            continue
        out.append(s)
    return out


def load_uncontrollable_rungs(path="runs/controllability.csv.summary.json",
                              require_full_protocol=True):
    from pathlib import Path
    import json
    p = Path(path)
    if not p.exists():
        return []
    summary = json.loads(p.read_text())
    if require_full_protocol and summary.get("full_protocol_budget") is not True:
        return []
    return list(summary.get("uncontrollable_rungs") or [])

# multistorm/evaluate.py
from __future__ import annotations
import time
import pandas as pd
import torch
from .metrics import episode_summary, relative
from .metrics_ext import extended_summary


def evaluate(agent, env, storms, bstore, phase, episode=None,
             deterministic=True, cso_floor=1.0, hind_table=None) -> pd.DataFrame:
    from . import metrics_v8
    from . import stl

    rows = []
    hind_table = hind_table or {}
    for st in storms:
        rec = bstore.get(st)
        t0 = time.time()
        v8 = hasattr(env.kb, "set_reference")
        if v8 and not rec.get("native"):
            raise ValueError("v8 evaluation requires a true native reference")
        ref_n = rec.get("native") or rec["static"]
        opts = {"storm": st, "baseline_flooding": rec["baseline_flooding"],
                "physical_rain": bool(getattr(env, "physical_rain", False))}
        if hasattr(env.kb, "set_reference"):
            opts["reference_cso"] = ref_n["cso_total"]
        obs, _ = env.reset(options=opts)
        if hasattr(agent, "reset"):
            agent.reset()
        done = False
        with torch.no_grad():
            while not done:
                a = agent.select_action(obs, deterministic=deterministic)
                obs, _, term, trunc, _ = env.step(a)
                done = bool(term or trunc)
        L = env.get_episode_log()
        s = episode_summary(L, rec["baseline_flooding"])
        ext = extended_summary(L)
        ext.update(L.get("accounting_summary", {}))
        store = {}
        try:
            store = stl.storage_metrics(L)
        except Exception:
            pass
        # A parent's hindsight schedule is not valid for its amplified children.
        hind = hind_table.get(st.storm_id)
        enrich = {}
        try:
            enrich = metrics_v8.enrich(s, ref_n, hind, cso_floor=cso_floor) if v8 else {}
        except Exception:
            if v8:
                raise
            enrich = {}
        if not v8 and ref_n["cso_total"] > cso_floor:
            enrich["cso_reduction_vs_native_pct"] = (
                100.0 * (ref_n["cso_total"] - s["cso_total"]) / ref_n["cso_total"])
        meta = st.meta or {}
        rel = relative(s, rec, cso_floor)
        # Merge carefully: enrich (native-referenced) wins on overlapping keys
        row = dict(
            phase=phase, episode=episode, storm_id=st.storm_id, split=st.split,
            family=meta.get("family"), rung=meta.get("rung"), k=meta.get("k"),
            T_anchor=meta.get("T_anchor"), parent=meta.get("parent", st.storm_id),
            rain_total_mm=float(st.depth.sum()), rain_peak_mm=float(st.depth.max()),
            deterministic=deterministic, wall_s=time.time() - t0,
        )
        row.update(s); row.update(ext); row.update(store); row.update(rel); row.update(enrich)
        rows.append(row)
    return pd.DataFrame(rows)

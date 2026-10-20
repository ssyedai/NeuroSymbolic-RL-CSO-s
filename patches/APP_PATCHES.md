# APP_PATCHES.md — exact edits to `app.py` (v7) for the v8 track

Rules: apply in order; after **each** patch run `pytest tests/test_golden.py -q` (your Stage-0 regression). Every patch is **opt-in**: with the new flags at their defaults the env behaves exactly like v7. Strings below are copied from your `app.py`; if a "FIND" block does not match exactly, stop and report instead of guessing.

---

## P1 — constructor flags + spaces (class `NeurosymbolicSWMMEnv`)

**FIND**
```python
    def __init__(self, knowledge_base: SymbolicKnowledgeBase,
                 input_file: str = None,
                 control_time_step: int = CONTROL_TIME_STEP,
                 use_volume: bool = False,
                 rainfall_series: np.ndarray = None):
        self.kb          = knowledge_base
```
**REPLACE**
```python
    def __init__(self, knowledge_base: SymbolicKnowledgeBase,
                 input_file: str = None,
                 control_time_step: int = CONTROL_TIME_STEP,
                 use_volume: bool = False,
                 rainfall_series: np.ndarray = None,
                 use_projection: bool = True,          # v8: False bypasses kb.project_action (pumps still 1.0)
                 policy_dim: int = 10,                 # v8: 7 = gates only, env appends pumps = 1
                 time_limit_truncation: bool = False,  # v8: horizon returned as truncated, not terminated
                 real_only: bool = False):             # v8: refuse legacy (inflated) rain path
        self.kb          = knowledge_base
        self.use_projection = use_projection
        self.policy_dim = policy_dim
        self.time_limit_truncation = time_limit_truncation
        self.real_only = real_only
```

**FIND**
```python
        raw_dim = len(self.sys_state)
        sym_dim = 11
        self.action_space      = spaces.Box(0.0, 1.0, shape=(10,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf,
                                            shape=(raw_dim + sym_dim,), dtype=np.float32)
```
**REPLACE**
```python
        raw_dim = len(self.sys_state)
        sym_dim = 11
        extra_dim = getattr(self.kb, "extra_dim", 0)      # v8 rain features; v7 KB has none -> 0
        self.action_space      = spaces.Box(0.0, 1.0, shape=(self.policy_dim,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf,
                                            shape=(raw_dim + sym_dim + extra_dim,), dtype=np.float32)
```

---

## P2 — node semantics + native mode is really native (`_init_sim`)

**FIND**
```python
        self.list_nodes = [n.nodeid for n in self._node_obj]
```
**REPLACE**
```python
        self.list_nodes = [n.nodeid for n in self._node_obj]
        # v8: real node semantics from the INP (pyswmm Node.is_storage/is_junction/is_outfall)  [VERIFY API names]
        self.storage_ids  = [n.nodeid for n in self._node_obj if n.is_storage()]
        self.junction_ids = [n.nodeid for n in self._node_obj if n.is_junction()]
        self.outfall_ids  = [n.nodeid for n in self._node_obj if n.is_outfall()]
        self._storage_full = {n: max(self._node_obj[n].full_depth, 1e-6) for n in self.storage_ids}
```

**FIND**
```python
        self.sim.start()
        self._apply_defaults()
        self._refresh_state()
```
**REPLACE**
```python
        self.sim.start()
        if not self.native_mode:          # v8 FIX (A2): native mode must keep the INP's own initial settings
            self._apply_defaults()
        self._refresh_state()
```
Add test: in native mode, `env.O1360.target_setting` after reset equals the INP-native value printed by `research/diag_semantics.py`, and differs from 0.5 if the INP value differs.

---

## P3 — true storage state in the observation dict (`_refresh_state`)

**FIND** (the end of `_refresh_state`, right after the `build_obs_dict(...)` call closes)
```python
            self.W35391, self.W35444,
            use_volume=self._use_volume,
        )
```
**REPLACE**
```python
            self.W35391, self.W35444,
            use_volume=self._use_volume,
        )
        # v8: storage state from the REAL storage units (A1). If storage_ids is empty the INP has no storage units
        # -> STOP and re-read research/diag_semantics.py output; do not continue with v8.
        nd_ = self._obs_dict["node_depths"]
        tot_full = sum(self._storage_full.values())
        self._obs_dict["storage_unit_fill"] = {n: nd_[n] / self._storage_full[n]
                                                for n in self.storage_ids if n in nd_}
        self._obs_dict["store_fill_ratio"] = (sum(nd_[n] for n in self.storage_ids if n in nd_) / tot_full
                                              if tot_full > 0 else 0.0)
```

---

## P4 — observation builder (rain features; no change for v7)

**FIND**
```python
    def _build_obs(self) -> np.ndarray:
        preds = self.kb.evaluate_predicates(self._obs_dict)
        return np.clip(
            np.concatenate([self.sys_state, preds]), -1e4, 1e4
        ).astype(np.float32)
```
**REPLACE**
```python
    def _build_obs(self) -> np.ndarray:
        preds = self.kb.evaluate_predicates(self._obs_dict)
        parts = [self.sys_state, preds]
        if getattr(self.kb, "extra_dim", 0) > 0:
            # intervals already applied = t-1 (t is incremented BEFORE _build_obs in step()); causal, no forecast
            parts.append(self.kb.extra_features(self._obs_dict, self._rain, max(self.t - 1, 0)))
        return np.clip(np.concatenate(parts), -1e4, 1e4).astype(np.float32)
```

---

## P5 — extra logs (`_clear_logs`)

**FIND**
```python
        self.episode_states  = []
```
**REPLACE** (inside `_clear_logs`)
```python
        self.episode_states  = []
        self.ep_cso_35391    = []
        self.ep_cso_35444    = []
        self.ep_pump_flow    = []
        self.ep_store_ratio  = []
        self.ep_maxdr_j      = []
        self.ep_cost         = []
        self.ep_rule_flags   = []
```

---

## P6 — `step()` : 7-D action, projection flag, logs, truncation, cost in info

**FIND**
```python
        if not np.all(np.isfinite(raw_np)):
            raw_np = np.full(10, 0.5)
```
**REPLACE**
```python
        if not np.all(np.isfinite(raw_np)):
            raw_np = np.full(self.policy_dim, 0.5)
        if raw_np.size == 7:                       # v8: gates-only policy; pumps frozen ON
            raw_np = np.concatenate([raw_np, np.ones(3)])
```

**FIND**
```python
        else:
            proj = self.kb.project_action(raw_np, self._obs_dict)
            # Apply projected actions (35281_B/35291_B now freely set by agent)
```
**REPLACE**
```python
        else:
            if self.use_projection:
                proj = self.kb.project_action(raw_np, self._obs_dict)
            else:                                   # v8 ablation: shield off, pumps still ON
                proj = np.clip(raw_np, 0.0, 1.0)
                proj[self.kb.PUMP_IDXS] = 1.0
            # Apply projected actions (35281_B/35291_B now freely set by agent)
```

**FIND**
```python
        self.episode_states.append(self.sys_state.copy())

        info = {}
        if self.current_storm is not None:
            info['storm_id'] = getattr(self.current_storm, 'storm_id', None)

        # Gymnasium-style: obs, reward, terminated, truncated, info
        # Keep 5th return as sys_state for Trial 7 train() compatibility via adapters.
        return (to_device(self._build_obs()),
                reward, done, False, info)
```
**REPLACE**
```python
        self.episode_states.append(self.sys_state.copy())
        self.ep_cso_35391.append(float(self.W35391.flow))
        self.ep_cso_35444.append(float(self.W35444.flow))
        self.ep_pump_flow.append(float(self.PUMP27.flow + self.PUMP28.flow + self.PUMP29.flow))
        self.ep_store_ratio.append(float(self._obs_dict.get('store_fill_ratio', 0.0)))
        self.ep_maxdr_j.append(float(max(
            [self._obs_dict['node_depths'][n] / max(self.kb.node_full_depths.get(n, 1e-6), 1e-6)
             for n in self.junction_ids if n in self._obs_dict['node_depths']] or [0.0])))
        self.ep_cost.append(float(breakdown.get('cost', 0.0)))
        self.ep_rule_flags.append(dict(getattr(self.kb, 'last_info', {}).get('flags', {})))

        info = {'cost': float(breakdown.get('cost', 0.0)),
                'rule_flags': getattr(self.kb, 'last_info', {}).get('flags', {}),
                'intervention': getattr(self.kb, 'last_info', {}).get('intervention', 0.0)}
        if self.current_storm is not None:
            info['storm_id'] = getattr(self.current_storm, 'storm_id', None)

        obs_t = to_device(self._build_obs())
        if self.time_limit_truncation:              # v8: horizon is a truncation, bootstrap through it
            return obs_t, reward, False, done, info
        return obs_t, reward, done, False, info
```
Note: `self.kb.node_full_depths` exists on v7; add `self.node_full_depths = node_full_depths` to `KnowledgeBaseV8.__init__` if you prefer (it stores `self.full`); simplest is to replace `self.kb.node_full_depths` with `getattr(self.kb, "node_full_depths", getattr(self.kb, "full", {}))`.

---

## P7 — `reset()` options

**FIND**
```python
        if "baseline_flooding" in options:
            self.kb.set_baseline_flooding(options["baseline_flooding"])
        self.native_mode = bool(options.get("native", False))
        if "physical_rain" in options:
            self.physical_rain = bool(options["physical_rain"])
```
**REPLACE**
```python
        if "baseline_flooding" in options:
            self.kb.set_baseline_flooding(options["baseline_flooding"])
        if "reference_cso" in options and hasattr(self.kb, "set_reference"):
            self.kb.set_reference(options["reference_cso"])      # per-storm normaliser (TRUE native CSO total)
        if "use_projection" in options:
            self.use_projection = bool(options["use_projection"])
        self.native_mode = bool(options.get("native", False))
        if "physical_rain" in options:
            self.physical_rain = bool(options["physical_rain"])
        if self.real_only and not self.physical_rain:
            raise RuntimeError("real_only=True requires physical_rain=True (legacy path inflates rain 6.35x)")
```

---

## P8 — `get_episode_log()` additions

**FIND**
```python
            "r_flood": _bd("flood_penalty", "r_flood"),
        }
```
**REPLACE**
```python
            "r_flood": _bd("flood_penalty", "r_flood"),
            "actions_raw": (np.asarray(self.ep_raw_actions, dtype=np.float64)
                            if self.ep_raw_actions else np.zeros((0, 10))),
            "cso_flow_35391": np.asarray(self.ep_cso_35391, dtype=np.float64),
            "cso_flow_35444": np.asarray(self.ep_cso_35444, dtype=np.float64),
            "pump_flow": np.asarray(self.ep_pump_flow, dtype=np.float64),
            "store_fill_ratio": np.asarray(self.ep_store_ratio, dtype=np.float64),
            "max_dr_junction": np.asarray(self.ep_maxdr_j, dtype=np.float64),
            "max_depth_ratio": np.asarray(self.ep_maxdr_j, dtype=np.float64),   # name used by metrics_ext
            "cost": np.asarray(self.ep_cost, dtype=np.float64),
            "rule_flags": list(self.ep_rule_flags),
        }
```
(`routing_error_pct`/`runoff_error_pct`: read after `sim.close()` from `sim.flow_routing_error` / `sim.runoff_error` or parse the `.rpt`  **[VERIFY]**; add in `reset()` before `self.sim.close()` and store in `self._last_errors`.)

---

## P9 — cache key (BaselineStore) and reference choice

In `multistorm/baselines.py` change the tag so stale v7-unit/native records are never reused:
```python
BaselineStore(..., tag="v3|physrain|nativefix|kb8")
```
`rec["native"]` (TRUE native after P2) is the **primary reference** everywhere (`metrics.relative(..., ref="native")`). `rec["static"]` stays as secondary.

---

## P10 — loader: attach scenario metadata (`multistorm/storms.py`, in `load_storms` after the list is built)

```python
import json
from pathlib import Path
man_path = Path(rain_dir) / "data_manifest.json"
if man_path.exists():
    man = json.loads(man_path.read_text())["storms"]
    for s in storms:
        m = man.get(s.storm_id)
        if m:
            s.meta.update(provenance=m["provenance"], family=m["family"], rung=m["rung"], k=m["k"],
                          parent=m["parent"], test_only=m.get("test_only", False),
                          T_anchor=m["T_by_dur"]["360"], T_by_dur=m["T_by_dur"])
```
`assign_splits(..., manifest_path=<out>/splits.json)` already reads the variant→split map the builder writes.

---

## P11 — v8 stack builder (`multistorm/adapters.py`)

```python
def build_v8(seed, theta=None, use_projection=True, lagrangian=True, rain_features=True, cost_limit=0.05):
    import numpy as np, pandas as pd, torch, app
    from research.topology import to_kb_dict
    from multistorm.kb_v8 import KnowledgeBaseV8
    from multistorm.agents_lag import SACLagAgent
    np.random.seed(seed); torch.manual_seed(seed)
    nodes = pd.read_csv("runs/diag_nodes.csv")
    full = {r.id: max(r.full_depth, 0.1) for r in nodes.itertuples()}           # NO v7 manual overrides
    kb = KnowledgeBaseV8(full, list(nodes[nodes.junction].id), to_kb_dict(pd.read_csv("runs/gate_topology.csv")),
                         theta=theta, use_rain_features=rain_features)
    env = app.NeurosymbolicSWMMEnv(kb, use_projection=use_projection, policy_dim=7,
                                   time_limit_truncation=True, real_only=True)
    agent = SACLagAgent(env.observation_space.shape[0], 7, cost_limit=cost_limit if lagrangian else 1e9,
                        lr=1e-4, gamma=0.99, tau=0.005, hidden=256, buffer_cap=50_000, batch_size=256)
    return env, agent, kb
```
`lagrangian=False` makes λ stay at `lam_init` and effectively act as a fixed penalty weight; for a *true* "−Lagrangian" ablation also pass `lam_init=0.0, lam_lr=0.0`.

## P12 — training episode (`multistorm/adapters.py`) for v8

```python
def train_one_episode_v8(env, agent, storm, ref_native, global_step, warmup, updates_per_step=0.25):
    obs, _ = env.reset(options=dict(storm=storm, physical_rain=True, baseline_flooding=0.0,
                                    reference_cso=ref_native["cso_total"]))
    ep_cost, acc, done = 0.0, 0.0, False
    while not done:
        a = (np.random.uniform(0, 1, 7) if global_step < warmup else agent.select_action(obs).detach().cpu().numpy())
        nobs, r, term, trunc, info = env.step(a)
        agent.store(obs, a, r, info["cost"], nobs, term)          # term only: truncation bootstraps
        ep_cost += info["cost"]; global_step += 1; obs = nobs; done = bool(term or trunc)
        if global_step > warmup:
            acc += updates_per_step
            while acc >= 1.0:
                agent.update(); acc -= 1.0
    agent.end_episode(ep_cost)
    return env.get_episode_log(), global_step, ep_cost
```
`updates_per_step=0.25` reproduces v7's UTD; try 1.0 in the T2 hyper-parameter pilot.

---

## Acceptance tests for the whole patch set
1. `tests/test_golden.py` passes with all defaults (v7 numbers unchanged).
2. New test: with `policy_dim=7`, `env.step(np.full(7, .5))` equals `env.step(np.r_[np.full(7,.5), np.ones(3)])`.
3. New test: `use_projection=False` leaves gates 0–6 untouched while pumps are 1.0.
4. New test: `time_limit_truncation=True` ⇒ last step returns `terminated=False, truncated=True`.
5. New test: `real_only=True` + `physical_rain=False` raises.
6. `python -m research.diag_semantics` prints non-empty `storage_ids` (else STOP).

# =============================================================================
# NEUROSYMBOLIC RL FOR SWMM STORMWATER CONTROL — v7 (PRODUCTION)
#
# BUGS FIXED vs FINAL-VERSION
# ─────────────────────────────────────────────────────────────────────────────
# BUG-1  r_viol caused oscillating divergence (~400-ep cycle).
#        Mechanism: r_cso rewards closing gates → KB correctly overrides to
#        open when storage critical (R1/R2) → r_viol penalises agent for
#        triggering those beneficial overrides → agent learns to pre-open gates
#        to avoid violation → CSO rises → agent closes → cycle repeats.
#        FIX: r_viol REMOVED entirely.
#
# BUG-2  r_storage = +1.54/episode regardless of policy (all 1000 episodes).
#        Storage fill is driven by rainfall, not gate position. Zero gradient
#        signal — pure constant noise. FIX: r_storage REMOVED entirely.
#
# BUG-3  35281_B (a[3]) and 35291_B (a[4]) frozen to 0.0 increased CSO by
#        ~68k/episode (+29%) vs v5. These gates route flow toward non-CSO
#        outlets; opening them reduces pressure on W35391+W35444.
#        HoF rules set them to 0 because HoF optimised CSO+flooding jointly —
#        freezing at 0 minimised flooding but increased CSO.
#        FIX: both gates returned to learnable action space. R1/R2 rules NOT
#             applied to them (topology ambiguous). RL learns via r_cso only.
#
# BUG-4  target_entropy = -action_dim = -10. With 3 pump dims frozen at 1.0
#        (near-zero policy entropy), effective learnable dims = 7 gates.
#        -10 >> entropy capacity of 7 dims → alpha over-inflated, oscillated.
#        FIX: target_entropy = -7.0
#
# BUG-5  lr = 3e-4 produced unstable gradient steps for this episode length.
#        The ~400-ep oscillation cycle matched the time for bad policy to flush
#        through the 100k replay buffer.
#        FIX: lr = 1e-4
#
# BUG-6  buffer_cap = 100k (~350 episodes). After a bad policy phase, stale
#        bad experience persisted for 350+ episodes.
#        FIX: buffer_cap = 50_000 (~175 episodes — faster refresh).
#
# BUG-7  HoFPolicy warm-up gave CSO ~304k/episode — worse than SAC best of
#        291k at ep406. HoF was trained for CSO+flooding objective, not CSO-only.
#        FIX: HoFPolicy removed. Standard random warm-up (2000 steps) used.
#
# BUG-8  MAX_GRAD_NORM = 1.0 too loose for new lr=1e-4.
#        FIX: MAX_GRAD_NORM = 0.5
#
# WHAT IS KEPT FROM v6
# ─────────────────────────────────────────────────────────────────────────────
#   Pumps frozen = 1.0 (always ON). FloodMax 4000 < baseline 7183 confirms
#   always-on pumps reduce flooding. Physically correct.
#   baseline_flooding = 7183 (calibrated with pumps ON, all gates=0.5).
#   FLOODING_THRESHOLD = 9500 (R6 emergency override at 132% of baseline).
#   Input LayerNorm on actor/critic (handles un-normalised SWMM state).
#   Gradient clipping on all three optimisers.
#   Stored wrapper objects per episode (no new Nodes/Links allocation per step).
#
# EXPECTED TRAINING PROGRESSION
# ─────────────────────────────────────────────────────────────────────────────
#   Start  : score ≈ −900/episode
#   ep 50  : SAC begins closing a[3]/a[4] less → CSO expected to fall
#   ep 200 : monotonic improvement (no oscillation without r_viol)
#   ep 500 : target score > −700/episode (≥ 10% CSO reduction)
#   ep1000 : target score > −600/episode (≥ 20% CSO reduction)
#   r_flood : ≈ 0 throughout normal operation (baseline subtracted correctly)
#   R6%     : < 1% of timesteps (fires only on genuine surges)
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 0 — IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.utils as nn_utils
import torch.optim as optim
from torch.distributions import Normal

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import random
import math
import re
from pathlib import Path
from collections import deque, namedtuple
import os

os.environ['CONDA_DLL_SEARCH_MODIFICATION_ENABLE'] = "1"

from pyswmm import Simulation, Nodes, Links, Subcatchments, RainGages
from gymnasium import Env, spaces

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
CONTROL_TIME_STEP = 900   # seconds (15-min interval)
MM_PER_INCH = 25.4


def to_device(x, dtype=torch.float32):
    """Create a float tensor on the active compute device."""
    if isinstance(x, torch.Tensor):
        return x.to(device=device, dtype=dtype)
    return torch.tensor(x, dtype=dtype, device=device)


def rain_to_gage_value(depth_mm_per_15min: float) -> float:
    """
    Convert mm per 15-min depth to Design_RG INTENSITY (in/hr) for CFS models.
    Must stay identical to multistorm.storms.rain_to_gage_value.
    """
    return float(depth_mm_per_15min) / (MM_PER_INCH * 0.25)


# ─────────────────────────────────────────────────────────────────────────────
# BLOCK 1 — RAINFALL DATA (lazy — loaded by build_stack / main)
# ─────────────────────────────────────────────────────────────────────────────
test_rainfall = None  # set by load_trial7_rainfall() / build_stack()


def load_trial7_rainfall(path: str = 'data/unused/rain/raindata.csv') -> np.ndarray:
    """Trial 7 preprocessing: peak→24 mm/h, then depth mm per 15-min interval."""
    _raw = pd.read_csv(path, header=None).values.flatten().astype(np.float64)
    _raw_max = float(_raw.max())
    series = (
        (_raw / _raw_max * 24.0) * (CONTROL_TIME_STEP / 3600.0)
        if _raw_max > 0 else np.zeros(len(_raw))
    )
    return series


# =============================================================================
# BLOCK 2 — SYMBOLIC KNOWLEDGE BASE (v7)
# =============================================================================
class SymbolicKnowledgeBase:
    """
    Symbolic rules for 7MPF_CSO_08 stormwater network.

    ACTION VECTOR LAYOUT (10 dimensions):
    ┌─────────┬────────────┬────────────────────────────────────────────────┐
    │ Index   │ Link       │ v7 Status                                      │
    ├─────────┼────────────┼────────────────────────────────────────────────┤
    │ a[0]    │ 1360       │ ACTIVE — RL learns; R1/R2 applied              │
    │ a[1]    │ 1360_B     │ ACTIVE — RL learns; R1/R2 applied              │
    │ a[2]    │ 35263      │ ACTIVE — RL learns; R1/R2 applied              │
    │ a[3]    │ 35281_B    │ ACTIVE — RL learns; NO R1/R2 (topology open)   │
    │ a[4]    │ 35291_B    │ ACTIVE — RL learns; NO R1/R2 (topology open)   │
    │ a[5]    │ 3530       │ ACTIVE — RL learns; R1/R2 applied              │
    │ a[6]    │ 3530_B     │ ACTIVE — RL learns; R1/R2 applied              │
    │ a[7]    │ PUMP27     │ FROZEN = 1.0  (always ON — reduces flooding)   │
    │ a[8]    │ PUMP28     │ FROZEN = 1.0  (always ON — reduces flooding)   │
    │ a[9]    │ PUMP29     │ FROZEN = 1.0  (always ON — reduces flooding)   │
    └─────────┴────────────┴────────────────────────────────────────────────┘

    Reward components (v7 — 3 terms only):
      r_close  +W_GATE_CLOSE × (1 − avg_R1R2) × (1 − risk) × headroom / S
               Rewards keeping R1R2-governed gates [0,1,2,5,6] closed when
               storage fill < 70% and manhole depth is safe.
      r_cso    −W_CSO × cso_flow / S
               PRIMARY LEARNING SIGNAL. Sum of flow through W35391+W35444.
      r_flood  −W_FLOOD × max(flood − baseline, 0) / S
               ≈ 0 during normal operation. Safety signal for extreme surges.

    REMOVED vs v6:
      r_viol    → caused 400-ep oscillation by conflicting with R1/R2 logic.
      r_storage → constant +1.54/ep regardless of policy (rainfall-driven).
    """

    # ── Thresholds ────────────────────────────────────────────────────────
    STORAGE_OPEN_THRESHOLD = 0.85
    STORAGE_WARN_THRESHOLD = 0.70
    MANHOLE_CRITICAL_RATIO = 0.90
    MANHOLE_WARNING_RATIO  = 0.75
    FLOODING_THRESHOLD     = 9500.0   # 132% × baseline (7183)

    # ── Reward weights ────────────────────────────────────────────────────
    REWARD_SCALE   = 1_000.0
    W_CSO          = 3.0
    W_FLOOD        = 5.0
    W_GATE_CLOSE   = 10.0

    # ── Topology ──────────────────────────────────────────────────────────
    STORAGE_NODE_IDS = ["54", "54_B"]
    WETWELL_NODE_IDS = ["JCT-2114", "JCT-3090", "65", "65_B"]

    # R1/R2 hydraulic rules applied ONLY to these 5 topology-confirmed gates
    R1R2_GATE_IDXS = [0, 1, 2, 5, 6]   # 1360, 1360_B, 35263, 3530, 3530_B
    # All 7 gates are learnable (includes 35281_B and 35291_B)
    ALL_GATE_IDXS  = [0, 1, 2, 3, 4, 5, 6]
    # Pumps are frozen at 1.0 (always ON)
    PUMP_IDXS      = [7, 8, 9]

    def __init__(self, node_full_depths: dict,
                 storage_capacity: float,
                 baseline_flooding: float = 0.0):
        self.node_full_depths  = node_full_depths
        self.storage_capacity  = max(storage_capacity, 1e-6)
        self.baseline_flooding = baseline_flooding
        self._prev_storage     = 0.0

    def reset_episode(self):
        self._prev_storage = 0.0

    def set_baseline_flooding(self, v: float):
        """Per-storm baseline used by r_flood (Stage 3 plumbing)."""
        self.baseline_flooding = float(v)

    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def build_obs_dict(node_obj, link_obj, list_nodes,
                       storage_node_ids, wetwell_node_ids,
                       cso_link1, cso_link2,
                       use_volume: bool = False):
        node_depths = {n: node_obj[n].depth    for n in list_nodes}
        node_floods = {n: node_obj[n].flooding  for n in list_nodes}

        if use_volume:
            try:
                storage_fill = sum(
                    node_obj[n].volume for n in storage_node_ids if n in node_depths)
            except AttributeError:
                storage_fill = sum(node_depths.get(n, 0.0) for n in storage_node_ids)
        else:
            storage_fill = sum(node_depths.get(n, 0.0) for n in storage_node_ids)

        pump_depths = {n: node_depths.get(n, 0.0) for n in wetwell_node_ids}
        cso_flow    = cso_link1.flow + cso_link2.flow
        flooding    = sum(node_floods.values())

        return {
            'node_depths':  node_depths,
            'node_floods':  node_floods,
            'storage_fill': storage_fill,
            'pump_depths':  pump_depths,
            'cso_flow':     cso_flow,
            'flooding':     flooding,
        }

    # ─────────────────────────────────────────────────────────────────────
    # 1. PREDICATE EVALUATION → 11-dim symbolic feature vector
    # ─────────────────────────────────────────────────────────────────────
    def evaluate_predicates(self, obs_dict: dict) -> np.ndarray:
        """
        [0]  storage_critical  fill >= 85%             (binary)
        [1]  storage_warning   fill >= 70%             (binary)
        [2]  manhole_critical  max_dr >= 90%           (binary)
        [3]  manhole_warning   max_dr >= 75%           (binary)
        [4]  cso_active        cso_flow > 0            (binary)
        [5]  flooding_severe   flooding > threshold    (binary)
        [6]  fill_ratio        [0, 1]
        [7]  max_depth_ratio   [0, 1]
        [8]  mean_depth_ratio  [0, 1]
        [9]  cso_flow_norm     cso / 5000              [0, 1]
        [10] flooding_norm     flooding / 10000        [0, 1]
        """
        fill_ratio = obs_dict.get('storage_fill', 0.0) / self.storage_capacity
        cso        = obs_dict.get('cso_flow',     0.0)
        flood      = obs_dict.get('flooding',     0.0)

        known_drs = [
            d / max(self.node_full_depths[n], 1e-6)
            for n, d in obs_dict.get('node_depths', {}).items()
            if n in self.node_full_depths
        ]
        max_dr  = max(known_drs)            if known_drs else 0.0
        mean_dr = float(np.mean(known_drs)) if known_drs else 0.0

        return np.array([
            float(fill_ratio >= self.STORAGE_OPEN_THRESHOLD),
            float(fill_ratio >= self.STORAGE_WARN_THRESHOLD),
            float(max_dr     >= self.MANHOLE_CRITICAL_RATIO),
            float(max_dr     >= self.MANHOLE_WARNING_RATIO),
            float(cso        >  0.0),
            float(flood      >  self.FLOODING_THRESHOLD),
            np.clip(fill_ratio, 0.0, 1.0),
            np.clip(max_dr,     0.0, 1.0),
            np.clip(mean_dr,    0.0, 1.0),
            np.clip(cso   /  5_000.0, 0.0, 1.0),
            np.clip(flood / 10_000.0, 0.0, 1.0),
        ], dtype=np.float32)

    # ─────────────────────────────────────────────────────────────────────
    # 2. ACTION PROJECTION
    # ─────────────────────────────────────────────────────────────────────
    def project_action(self, raw_action: np.ndarray, obs_dict: dict) -> np.ndarray:
        """
        Step 1 — Freeze pumps:
          a[7] = a[8] = a[9] = 1.0  (always ON)

        Step 2 — Hydraulic rules on R1R2_GATE_IDXS = [0,1,2,5,6] ONLY:
          R6  flooding > 9500    → those gates = 1.0  (emergency drain)
          R1  fill >= 85%        → those gates >= 0.8 (release storage)
          R2  max_dr >= 90%      → those gates >= 0.5 (prevent surcharge)
          else: raw action passes through unchanged

        a[3] (35281_B) and a[4] (35291_B):
          Passed through unchanged — RL agent controls them freely via r_cso.
          Not subject to R1/R2: their downstream topology routes flow AWAY
          from CSO outlets, so opening them under high fill is safe/beneficial.
          Evidence: freezing at 0.0 (v6) caused +68k/ep CSO increase.
        """
        a = raw_action.copy().astype(np.float64)

        # Step 1: always-ON pumps
        a[self.PUMP_IDXS] = 1.0

        # Step 2: read hydraulic state
        fill  = obs_dict['storage_fill'] / self.storage_capacity
        flood = obs_dict.get('flooding', 0.0)
        known_drs = {
            n: d / max(self.node_full_depths[n], 1e-6)
            for n, d in obs_dict['node_depths'].items()
            if n in self.node_full_depths
        }
        max_dr = max(known_drs.values()) if known_drs else 0.0

        # Step 3: hydraulic rules on R1R2 gates only
        ag = self.R1R2_GATE_IDXS
        if flood > self.FLOODING_THRESHOLD:
            a[ag] = 1.0                          # R6: emergency drain
        elif fill >= self.STORAGE_OPEN_THRESHOLD:
            a[ag] = np.maximum(a[ag], 0.8)       # R1: release full storage
        elif max_dr >= self.MANHOLE_CRITICAL_RATIO:
            a[ag] = np.maximum(a[ag], 0.5)       # R2: prevent surcharge

        return np.clip(a, 0.0, 1.0)

    # ─────────────────────────────────────────────────────────────────────
    # 3. SYMBOLIC REWARD SHAPING (v7 — 3 terms, no r_viol, no r_storage)
    # ─────────────────────────────────────────────────────────────────────
    def shape_reward(self, obs_dict: dict,
                     raw_action: np.ndarray,
                     projected_action: np.ndarray) -> tuple:
        """
        r_close : +W_GATE_CLOSE × (1 − avg_R1R2) × (1 − depth_risk) × headroom / S
                  Soft incentive to keep R1R2 gates closed when fill < 70%
                  and manholes are not near-critical. Computed over [0,1,2,5,6].

        r_cso   : −W_CSO × cso_flow / S
                  PRIMARY SIGNAL. Measures W35391 + W35444 discharge.
                  Single, unambiguous objective. No confounding terms.

        r_flood : −W_FLOOD × max(flood − baseline, 0) / S
                  Effectively 0 at baseline (7183/step). Fires only when agent
                  causes flooding significantly above the background rate.

        NOT included:
          r_viol    Removed (BUG-1: drove 400-ep oscillation cycles).
          r_storage Removed (BUG-2: constant noise, zero policy gradient).
          r_depth   Removed in v6 (was missing /S, dominated by 5.3× over CSO).
        """
        S  = self.REWARD_SCALE
        ag = self.R1R2_GATE_IDXS

        cso   = obs_dict.get('cso_flow',     0.0)
        flood = obs_dict.get('flooding',     0.0)
        fill  = obs_dict.get('storage_fill', 0.0)

        known_drs = {
            n: d / max(self.node_full_depths[n], 1e-6)
            for n, d in obs_dict.get('node_depths', {}).items()
            if n in self.node_full_depths
        }
        max_dr = max(known_drs.values()) if known_drs else 0.0

        # R7: gate-close incentive (R1R2 gates, safe conditions)
        gate_avg_r1r2 = float(np.mean(projected_action[ag]))
        depth_risk    = min(max_dr / self.MANHOLE_CRITICAL_RATIO, 1.0) ** 2
        fill_ratio    = fill / self.storage_capacity
        safe_headroom = max(0.0, self.STORAGE_WARN_THRESHOLD - fill_ratio)
        r_close       = (self.W_GATE_CLOSE
                         * (1.0 - gate_avg_r1r2)
                         * (1.0 - depth_risk)
                         * safe_headroom / S)

        # R4: CSO penalty — PRIMARY SIGNAL
        r_cso = -self.W_CSO * max(cso, 0.0) / S

        # Excess flood safety signal (≈ 0 during normal operation)
        excess_flood = max(flood - self.baseline_flooding, 0.0)
        r_flood      = -self.W_FLOOD * excess_flood / S

        total = r_close + r_cso + r_flood

        return total, {
            'gate_close':    r_close,
            'cso_penalty':   r_cso,
            'flood_penalty': r_flood,
            'total':         total,
        }


# =============================================================================
# BLOCK 3 — ENVIRONMENT (v7)
# =============================================================================
INPUT_FILE = r"7MPF_CSO_08.inp"


class NeurosymbolicSWMMEnv(Env):

    INPUT_FILE = r"7MPF_CSO_08.inp"

    def __init__(self, knowledge_base: SymbolicKnowledgeBase,
                 input_file: str = None,
                 control_time_step: int = CONTROL_TIME_STEP,
                 use_volume: bool = False,
                 rainfall_series: np.ndarray = None,
                 use_projection: bool = True,          # v8: False bypasses kb.project_action
                 policy_dim: int = 10,                 # v8: 7 = gates only; 10 is an explicit pump ablation
                 time_limit_truncation: bool = False,  # v8: horizon returned as truncated, not terminated
                 real_only: bool = False,              # v8: refuse legacy (inflated) rain path
                 full_horizon: bool = False,          # opt-in: include final control interval
                 native_pumps: bool = False,           # diagnostic ablation: preserve pump interlocks
                 external_gate_control: bool = False, # v8: remove INP gate rules from generated episode INPs
                 policy_controls_pumps: bool = False): # 10-D ablation only: policy owns pumps too
        self.kb          = knowledge_base
        self.use_projection = use_projection
        self.policy_dim = policy_dim
        self.time_limit_truncation = time_limit_truncation
        self.real_only = real_only
        self.full_horizon = full_horizon
        self.native_pumps = native_pumps
        self.external_gate_control = external_gate_control
        self.policy_controls_pumps = policy_controls_pumps
        if self.policy_controls_pumps and self.policy_dim != 10:
            raise ValueError("policy_controls_pumps requires policy_dim=10")
        if self.policy_controls_pumps and self.native_pumps:
            raise ValueError("Pumps cannot be owned by both the policy and native rules")
        self._control_rules_removed = False
        self.base_input_file = input_file or self.INPUT_FILE
        self.input_file  = self.base_input_file
        self.ctrl_step   = control_time_step
        self._use_volume = use_volume
        # Per-instance rainfall (mm per control interval). Legacy default = Trial 7 series.
        self._rain = (np.asarray(rainfall_series, dtype=np.float64)
                      if rainfall_series is not None else None)
        self.current_storm = None
        self.native_mode = False
        # False = Trial 7 legacy (pass depth as-is to total_precip).
        # True  = physical in/hr via rain_to_gage_value (real-rainfall research).
        self.physical_rain = False
        self._init_sim()

        raw_dim = len(self.sys_state)
        sym_dim = 11
        extra_dim = getattr(self.kb, "extra_dim", 0)      # v8 rain features; v7 KB has none -> 0
        self.action_space      = spaces.Box(0.0, 1.0, shape=(self.policy_dim,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf,
                                            shape=(raw_dim + sym_dim + extra_dim,), dtype=np.float32)
        self._clear_logs()

    def _init_sim(self):
        self._prepare_external_gate_control()
        self.sim = Simulation(self.input_file)
        self.sim.step_advance(self.ctrl_step)

        # Allocate wrappers ONCE per episode — no re-allocation per step
        self._node_obj = Nodes(self.sim)
        self._link_obj = Links(self.sim)
        self._sub_obj  = Subcatchments(self.sim)
        self._rg_obj   = RainGages(self.sim)

        # pyswmm Nodes/Links/Subcatchments iterators are one-shot — materialise ids first.
        self.list_nodes = [n.nodeid for n in self._node_obj]
        self.list_links = [l.linkid for l in self._link_obj]
        self.list_sub   = [s.subcatchmentid for s in self._sub_obj]
        # v8: real node semantics from the INP (index access; do not re-iterate Nodes)
        self.storage_ids  = [n for n in self.list_nodes if self._node_obj[n].is_storage()]
        self.junction_ids = [n for n in self.list_nodes if self._node_obj[n].is_junction()]
        self.outfall_ids  = [n for n in self.list_nodes if self._node_obj[n].is_outfall()]
        self._storage_full = {n: max(self._node_obj[n].full_depth, 1e-6) for n in self.storage_ids}

        self.O1360     = self._link_obj["1360"]
        self.O1360_B   = self._link_obj["1360_B"]
        self.O35263    = self._link_obj["35263"]
        self.O35281_B  = self._link_obj["35281_B"]   # now active
        self.O35291_B  = self._link_obj["35291_B"]   # now active
        self.O3530     = self._link_obj["3530"]
        self.O3530_B   = self._link_obj["3530_B"]
        self.PUMP27    = self._link_obj["PUMP27@35395-3535"]
        self.PUMP28    = self._link_obj["PUMP28@35390-3535"]
        self.PUMP29    = self._link_obj["PUMP29@35445-3565"]
        self.W35391    = self._link_obj["35391"]
        self.W35444    = self._link_obj["35444"]
        self.rg1       = self._rg_obj['Design_RG']

        sim_len = self.sim.end_time - self.sim.start_time
        self.T  = int(sim_len.total_seconds() / self.ctrl_step) - (0 if self.full_horizon else 1)
        self.t  = 1

        self.sim.start()
        if not self.native_mode:          # v8 FIX (A2): native mode must keep the INP's own initial settings
            self._apply_defaults()
        self._refresh_state()

    def _prepare_external_gate_control(self):
        """Give an external policy exclusive gate ownership on generated INPs.

        Pump-only native interlocks are retained when ``native_pumps`` is true.
        This is opt-in so the frozen v7 path and true-native reference are
        byte-for-byte unchanged.
        """
        if not (self.external_gate_control and self.physical_rain and not self.native_mode):
            return
        self._control_rules_removed = False
        path = Path(self.input_file).resolve()
        root = Path("runs/_physical_inp").resolve()
        if path.parent != root:
            raise ValueError("External gate control may edit only generated episode INPs")
        text = path.read_text()

        def control_section(match):
            if not self.native_pumps:
                return "[CONTROLS]\n; External gates and pumps.\n\n"
            blocks = re.split(r"(?im)^(?=RULE\s)", match.group(0))
            kept = []
            for block in blocks:
                has_pump = re.search(r"(?im)^\s*(THEN|ELSE|AND)\s+PUMP\s", block)
                has_gate = re.search(
                    r"(?im)^\s*(THEN|ELSE|AND)\s+(ORIFICE|CONDUIT|WEIR|OUTLET)\s", block)
                if has_pump and has_gate:
                    raise ValueError("Cannot separate mixed pump/gate control rule")
                if has_pump:
                    kept.append(block)
            if not kept:
                raise ValueError("Native pump interlock rules missing")
            return ("[CONTROLS]\n; External gates; original pump rules retained.\n"
                    + "\n".join(kept) + "\n")

        text, count = re.subn(
            r"(?ms)^\[CONTROLS\][^\r\n]*\r?\n.*?(?=^\[|\Z)", control_section, text)
        if count != 1:
            raise ValueError("Expected exactly one native CONTROLS section")
        path.write_text(text)
        self._control_rules_removed = True

    def _apply_defaults(self):
        """
        v7 defaults: ALL 7 gates start at 0.5 (including 35281_B, 35291_B).
        Pumps start at 1.0 (always ON).
        """
        for lnk in [self.O1360, self.O1360_B, self.O35263,
                    self.O35281_B, self.O35291_B,
                    self.O3530, self.O3530_B]:
            lnk.target_setting = 0.5
        if not self.native_pumps:
            self.PUMP27.target_setting = 1.0
            self.PUMP28.target_setting = 1.0
            self.PUMP29.target_setting = 1.0

    def _refresh_state(self):
        nd = np.array([self._node_obj[n].depth        for n in self.list_nodes])
        ni = np.array([self._node_obj[n].total_inflow  for n in self.list_nodes])
        nh = np.array([self._node_obj[n].head          for n in self.list_nodes])
        lf = np.array([self._link_obj[l].flow          for l in self.list_links])
        ld = np.array([self._link_obj[l].depth         for l in self.list_links])
        lk = np.array([self._link_obj[l].froude        for l in self.list_links])
        sr = np.array([self._sub_obj[s].rainfall       for s in self.list_sub])
        self.sys_state = np.concatenate([nd, ni, nh, lf, ld, lk, sr])
        self._obs_dict = SymbolicKnowledgeBase.build_obs_dict(
            self._node_obj, self._link_obj, self.list_nodes,
            SymbolicKnowledgeBase.STORAGE_NODE_IDS,
            SymbolicKnowledgeBase.WETWELL_NODE_IDS,
            self.W35391, self.W35444,
            use_volume=self._use_volume,
        )
        # v8: storage state from the REAL storage units (A1).
        nd_ = self._obs_dict["node_depths"]
        tot_full = sum(self._storage_full.values())
        self._obs_dict["storage_unit_fill"] = {n: nd_[n] / self._storage_full[n]
                                                for n in self.storage_ids if n in nd_}
        self._obs_dict["store_fill_ratio"] = (sum(nd_[n] for n in self.storage_ids if n in nd_) / tot_full
                                              if tot_full > 0 else 0.0)

    def _build_obs(self) -> np.ndarray:
        preds = self.kb.evaluate_predicates(self._obs_dict)
        parts = [self.sys_state, preds]
        if getattr(self.kb, "extra_dim", 0) > 0:
            # Rain files remain 15-minute depths even when an opt-in controller
            # acts more frequently. Convert elapsed control time to completed
            # rain intervals; never expose a future depth.
            rain_n = int(max(self.t - 1, 0) * self.ctrl_step // CONTROL_TIME_STEP)
            parts.append(self.kb.extra_features(self._obs_dict, self._rain, rain_n))
        return np.clip(np.concatenate(parts), -1e4, 1e4).astype(np.float32)

    def _clear_logs(self):
        self.ep_rewards      = []
        self.ep_breakdowns   = []
        self.ep_proj_actions = []
        self.ep_raw_actions  = []
        self.ep_predicates   = []
        self.ep_cso_flows    = []
        self.ep_storage      = []
        self.ep_max_depths   = []
        self.ep_flooding     = []
        self.episode_states  = []
        self.ep_cso_35391    = []
        self.ep_cso_35444    = []
        self.ep_pump_flow    = []
        self.ep_store_ratio  = []
        self.ep_maxdr_j      = []
        self.ep_cost         = []
        self.ep_rule_flags   = []

    def step(self, raw_action: torch.Tensor, rainfall_series: np.ndarray = None):
        # Legacy callers may still pass rainfall_series; prefer instance _rain.
        rain = self._rain if rainfall_series is None else np.asarray(rainfall_series, dtype=np.float64)
        required_rain = (int(np.ceil(self.T * self.ctrl_step / CONTROL_TIME_STEP))
                         if self.physical_rain else self.T)
        assert rain is not None and len(rain) >= required_rain, (
            f"rainfall length {0 if rain is None else len(rain)} < required intervals {required_rain}")

        if isinstance(raw_action, torch.Tensor):
            with torch.no_grad():
                raw_np = raw_action.detach().cpu().numpy().astype(np.float64)
        else:
            raw_np = np.asarray(raw_action, dtype=np.float64).reshape(-1)
        if not np.all(np.isfinite(raw_np)):
            raw_np = np.full(self.policy_dim, 0.5)
        if raw_np.size == 7:                       # v8: gates-only policy; pumps frozen ON
            raw_np = np.concatenate([raw_np, np.ones(3)])

        if self.native_mode:
            # SWMM [CONTROLS] act; do not write target_setting / no KB projection
            proj = raw_np.copy()
            proj[self.kb.PUMP_IDXS] = 1.0
        else:
            if self.use_projection:
                proj = self.kb.project_action(raw_np, self._obs_dict)
            else:                                   # v8 ablation: shield off
                proj = np.clip(raw_np, 0.0, 1.0)
                if not self.policy_controls_pumps:
                    proj[self.kb.PUMP_IDXS] = 1.0
            # Apply projected actions (35281_B/35291_B now freely set by agent)
            self.O1360.target_setting    = proj[0]
            self.O1360_B.target_setting  = proj[1]
            self.O35263.target_setting   = proj[2]
            self.O35281_B.target_setting = proj[3]   # active — agent-controlled
            self.O35291_B.target_setting = proj[4]   # active — agent-controlled
            self.O3530.target_setting    = proj[5]
            self.O3530_B.target_setting  = proj[6]
            if not self.native_pumps:
                self.PUMP27.target_setting   = proj[7]   # always 1.0
                self.PUMP28.target_setting   = proj[8]   # always 1.0
                self.PUMP29.target_setting   = proj[9]   # always 1.0

        idx = self.t - 1
        # Physical-rain research: hyetograph is embedded as TIMESERIES STORM15 in a
        # temp INP (15-min gage). Do not API-override — that fights the timeseries.
        # Legacy Trial 7: write depth (treated as in/hr) each step on the stock INP.
        if not self.physical_rain:
            depth = float(rain[idx]) if rain[idx] > 0 else 0.0
            self.rg1.total_precip = depth if depth > 0 else 0.0

        try:
            self.sim.__next__()
        except StopIteration:
            # PySWMM advances to end_time before signalling exhaustion.
            if not self.full_horizon or self.sim.current_time < self.sim.end_time:
                raise
        self._refresh_state()

        reward, breakdown = self.kb.shape_reward(self._obs_dict, raw_np, proj)
        if not np.isfinite(reward):
            reward = -100.0

        done   = (self.t >= self.T)
        self.t += 1

        preds = self.kb.evaluate_predicates(self._obs_dict)
        self.ep_rewards.append(reward)
        self.ep_breakdowns.append(breakdown)
        self.ep_proj_actions.append(proj.copy())
        self.ep_raw_actions.append(raw_np.copy())
        self.ep_predicates.append(preds.copy())
        self.ep_cso_flows.append(self._obs_dict['cso_flow'])
        self.ep_storage.append(self._obs_dict['storage_fill'])
        self.ep_max_depths.append(float(preds[7]))
        self.ep_flooding.append(self._obs_dict['flooding'])
        self.episode_states.append(self.sys_state.copy())
        self.ep_cso_35391.append(float(self.W35391.flow))
        self.ep_cso_35444.append(float(self.W35444.flow))
        self.ep_pump_flow.append(float(self.PUMP27.flow + self.PUMP28.flow + self.PUMP29.flow))
        self.ep_store_ratio.append(float(self._obs_dict.get('store_fill_ratio', 0.0)))
        _full = getattr(self.kb, "node_full_depths", getattr(self.kb, "full", {}))
        self.ep_maxdr_j.append(float(max(
            [self._obs_dict['node_depths'][n] / max(_full.get(n, 1e-6), 1e-6)
             for n in self.junction_ids if n in self._obs_dict['node_depths']] or [0.0])))
        self.ep_cost.append(float(breakdown.get('cost', 0.0)))
        self.ep_rule_flags.append(dict(getattr(self.kb, 'last_info', {}).get('flags', {})))

        info = {'cost': float(breakdown.get('cost', 0.0)),
                'rule_flags': getattr(self.kb, 'last_info', {}).get('flags', {}),
                'intervention': getattr(self.kb, 'last_info', {}).get('intervention', 0.0)}
        if self.current_storm is not None:
            info['storm_id'] = getattr(self.current_storm, 'storm_id', None)

        # Gymnasium-style: obs, reward, terminated, truncated, info
        obs_t = to_device(self._build_obs())
        if self.time_limit_truncation:              # v8: horizon is a truncation, bootstrap through it
            return obs_t, reward, False, done, info
        return obs_t, reward, done, False, info

    def reset(self, *, seed=None, options=None):
        options = options or {}
        if seed is not None:
            np.random.seed(seed)
            torch.manual_seed(seed)
            random.seed(seed)

        if "storm" in options:
            storm = options["storm"]
            self.current_storm = storm
            depth = getattr(storm, "depth", storm)
            self._rain = np.asarray(depth, dtype=np.float64)
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

        if self._rain is None and test_rainfall is not None:
            self._rain = np.asarray(test_rainfall, dtype=np.float64)

        # Physical units: rebuild a 15-min TIMESERIES INP for this hyetograph.
        # Legacy Trial 7 keeps the stock INP + per-step API writes.
        if self.physical_rain:
            if self._rain is None:
                raise RuntimeError("physical_rain=True requires a storm / rainfall series")
            from multistorm.physical_inp import write_physical_storm_inp
            self.input_file = str(write_physical_storm_inp(
                self._rain, src=self.base_input_file))
        else:
            self.input_file = self.base_input_file

        self.sim.close()
        self._init_sim()
        if self._rain is not None:
            required_rain = (int(np.ceil(self.T * self.ctrl_step / CONTROL_TIME_STEP))
                             if self.physical_rain else self.T)
            assert len(self._rain) >= required_rain, (
                f"rainfall length {len(self._rain)} < required intervals {required_rain}")
        self.kb.reset_episode()
        self._clear_logs()
        obs = to_device(self._build_obs())
        info = {}
        if self.current_storm is not None:
            info['storm_id'] = getattr(self.current_storm, 'storm_id', None)
        return obs, info

    def get_episode_log(self) -> dict:
        """Per-step arrays for multistorm metrics (adapter contract)."""
        bd = self.ep_breakdowns
        def _bd(key, alt=None):
            if not bd:
                return np.zeros(0, dtype=np.float64)
            return np.asarray([b.get(key, b.get(alt, 0.0) if alt else 0.0) for b in bd],
                              dtype=np.float64)
        return {
            "cso_flow": np.asarray(self.ep_cso_flows, dtype=np.float64),
            "flooding": np.asarray(self.ep_flooding, dtype=np.float64),
            "storage_fill": np.asarray(self.ep_storage, dtype=np.float64),
            "actions_projected": (np.asarray(self.ep_proj_actions, dtype=np.float64)
                                  if self.ep_proj_actions else np.zeros((0, 10))),
            "reward": np.asarray(self.ep_rewards, dtype=np.float64),
            "r_close": _bd("gate_close", "r_close"),
            "r_cso": _bd("cso_penalty", "r_cso"),
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
            "control_step_s": int(self.ctrl_step),
        }

    def close(self):
        self.sim.close()


# =============================================================================
# BLOCK 4 — NEURAL NETWORKS (v7)
# =============================================================================
Transition = namedtuple('Transition', ['state', 'action', 'reward', 'next_state', 'done'])


class ReplayBuffer:
    """
    Capacity reduced to 50k (from 100k in v6).
    Rationale: 100k ≈ 350 episodes. After a bad policy phase, stale experience
    persisted for 350+ more episodes before flushing out.
    50k ≈ 175 episodes → faster recovery from exploration mistakes.
    """
    def __init__(self, capacity: int = 50_000):
        self.buf = deque(maxlen=capacity)

    def push(self, s, a, r, ns, d):
        self.buf.append(Transition(s, a, float(r), ns, float(d)))

    def sample(self, batch_size: int):
        batch = random.sample(self.buf, batch_size)
        s, a, r, ns, d = zip(*batch)
        return (torch.stack(s).to(device),
                torch.stack(a).to(device),
                torch.tensor(r, dtype=torch.float32, device=device).unsqueeze(1),
                torch.stack(ns).to(device),
                torch.tensor(d, dtype=torch.float32, device=device).unsqueeze(1))

    def __len__(self):
        return len(self.buf)


class Actor(nn.Module):
    LOG_STD_MIN, LOG_STD_MAX = -20, 2

    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 256,
                 correct_action_logprob: bool = False):
        super().__init__()
        # Trial-7 omitted the affine [-1, 1] -> [0, 1] Jacobian.  Keep that
        # historical behaviour by default; research stacks opt into the
        # mathematically correct density so the golden v7 path is unchanged.
        self.correct_action_logprob = bool(correct_action_logprob)
        self.net = nn.Sequential(
            nn.LayerNorm(obs_dim),
            nn.Linear(obs_dim, hidden), nn.LayerNorm(hidden), nn.ReLU(),
            nn.Linear(hidden,  hidden), nn.LayerNorm(hidden), nn.ReLU(),
        )
        self.mu  = nn.Linear(hidden, action_dim)
        self.std = nn.Linear(hidden, action_dim)

    def forward(self, obs):
        h = self.net(obs)
        return self.mu(h), self.std(h).clamp(self.LOG_STD_MIN, self.LOG_STD_MAX)

    def sample(self, obs):
        mu, lsig = self(obs)
        dist = Normal(mu, lsig.exp())
        x    = dist.rsample()
        y    = torch.tanh(x)
        a    = (y + 1.0) / 2.0
        lp   = (dist.log_prob(x)
                - torch.log(1.0 - y.pow(2) + 1e-6)).sum(-1, keepdim=True)
        if self.correct_action_logprob:
            lp = lp + y.shape[-1] * math.log(2.0)
        return a, lp

    def get_action(self, obs: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            a, _ = self.sample(obs.unsqueeze(0))
        return a.squeeze(0)


class Critic(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden: int = 256):
        super().__init__()
        in_dim = obs_dim + action_dim

        def _q():
            return nn.Sequential(
                nn.LayerNorm(in_dim),
                nn.Linear(in_dim, hidden), nn.LayerNorm(hidden), nn.ReLU(),
                nn.Linear(hidden, hidden), nn.LayerNorm(hidden), nn.ReLU(),
                nn.Linear(hidden, 1),
            )
        self.q1, self.q2 = _q(), _q()

    def forward(self, obs: torch.Tensor, a: torch.Tensor):
        x = torch.cat([obs, a], dim=-1)
        return self.q1(x), self.q2(x)

    def min_q(self, obs: torch.Tensor, a: torch.Tensor) -> torch.Tensor:
        return torch.min(*self(obs, a))


class SACAgent:
    """
    SAC with v7 hyperparameter corrections:

    lr              : 3e-4 → 1e-4   Prevents the ~400-ep gradient oscillation.
    target_entropy  : -10  → -7.0   Matches 7 learnable gate dims (3 pump
                                     dims frozen at 1.0 contribute ~0 entropy).
    MAX_GRAD_NORM   : 1.0  → 0.5    Extra stability at lower lr.
    buffer_cap      : 100k → 50k    Fresher experience; faster bad-policy flush.
    """
    MAX_GRAD_NORM = 0.5

    def __init__(self, obs_dim: int, action_dim: int,
                 lr: float         = 1e-4,
                 gamma: float      = 0.99,
                 tau: float        = 0.005,
                 hidden: int       = 256,
                 buffer_cap: int   = 50_000,
                 batch_size: int   = 256,
                 correct_action_logprob: bool = False):
        self.gamma, self.tau, self.batch_size = gamma, tau, batch_size

        self.actor         = Actor(
            obs_dim, action_dim, hidden,
            correct_action_logprob=correct_action_logprob,
        ).to(device)
        self.critic        = Critic(obs_dim, action_dim, hidden).to(device)
        self.critic_target = Critic(obs_dim, action_dim, hidden).to(device)
        self.critic_target.load_state_dict(self.critic.state_dict())

        self.actor_opt  = optim.Adam(self.actor.parameters(),  lr=lr)
        self.critic_opt = optim.Adam(self.critic.parameters(), lr=lr)

        # -7.0 for 7 learnable gate dims, not -10 for all action dims
        self.target_entropy = -7.0
        self.log_alpha      = torch.zeros(1, requires_grad=True, device=device)
        self.alpha_opt      = optim.Adam([self.log_alpha], lr=lr)

        self.replay    = ReplayBuffer(buffer_cap)
        self.train_log = {'critic_loss': [], 'actor_loss': [], 'alpha': []}

    def _soft_update(self):
        for p, pt in zip(self.critic.parameters(), self.critic_target.parameters()):
            pt.data.copy_(self.tau * p.data + (1.0 - self.tau) * pt.data)

    def select_action(self, obs: torch.Tensor, deterministic: bool = False) -> torch.Tensor:
        obs = to_device(obs)
        if not deterministic:
            return self.actor.get_action(obs)
        with torch.no_grad():
            if obs.dim() == 1:
                obs = obs.unsqueeze(0)
            mu, _ = self.actor(obs)
            a = (torch.tanh(mu) + 1.0) / 2.0
            return a.squeeze(0)

    def alpha_value(self) -> float:
        return float(self.log_alpha.exp().item())

    def save(self, path: str, extra: dict = None):
        payload = {
            'actor': self.actor.state_dict(),
            'critic': self.critic.state_dict(),
            'critic_target': self.critic_target.state_dict(),
            'actor_opt': self.actor_opt.state_dict(),
            'critic_opt': self.critic_opt.state_dict(),
            'alpha_opt': self.alpha_opt.state_dict(),
            'log_alpha': self.log_alpha.detach().cpu(),
            'device': str(device),
            'extra': extra or {},
        }
        torch.save(payload, path)

    def load(self, path: str) -> dict:
        ckpt = torch.load(path, map_location=device, weights_only=False)
        self.actor.load_state_dict(ckpt['actor'])
        self.critic.load_state_dict(ckpt['critic'])
        if 'critic_target' in ckpt:
            self.critic_target.load_state_dict(ckpt['critic_target'])
        else:
            self.critic_target.load_state_dict(ckpt['critic'])
        if 'actor_opt' in ckpt:
            self.actor_opt.load_state_dict(ckpt['actor_opt'])
            self.critic_opt.load_state_dict(ckpt['critic_opt'])
            self.alpha_opt.load_state_dict(ckpt['alpha_opt'])
        if 'log_alpha' in ckpt:
            self.log_alpha.data.copy_(ckpt['log_alpha'].to(device))
        return ckpt.get('extra', {})

    def store(self, s, a, r, ns, d):
        # Keep replay on CPU; batches are moved to GPU in sample()/update().
        self.replay.push(
            s.detach().cpu() if isinstance(s, torch.Tensor) else s,
            a.detach().cpu() if isinstance(a, torch.Tensor) else a,
            r, ns.detach().cpu() if isinstance(ns, torch.Tensor) else ns, d)

    def update(self):
        if len(self.replay) < self.batch_size:
            return
        s, a, r, ns, d = self.replay.sample(self.batch_size)
        alpha = self.log_alpha.exp().detach()

        with torch.no_grad():
            na, lp = self.actor.sample(ns)
            q_tgt  = r + self.gamma * (1.0 - d) * (
                self.critic_target.min_q(ns, na) - alpha * lp)

        q1, q2 = self.critic(s, a)
        c_loss  = F.mse_loss(q1, q_tgt) + F.mse_loss(q2, q_tgt)
        self.critic_opt.zero_grad()
        c_loss.backward()
        nn_utils.clip_grad_norm_(self.critic.parameters(), self.MAX_GRAD_NORM)
        self.critic_opt.step()

        a_new, lp_new = self.actor.sample(s)
        alpha  = self.log_alpha.exp()
        a_loss = (alpha.detach() * lp_new - self.critic.min_q(s, a_new)).mean()
        self.actor_opt.zero_grad()
        a_loss.backward()
        nn_utils.clip_grad_norm_(self.actor.parameters(), self.MAX_GRAD_NORM)
        self.actor_opt.step()

        al_loss = -(self.log_alpha * (lp_new + self.target_entropy).detach()).mean()
        self.alpha_opt.zero_grad()
        al_loss.backward()
        self.alpha_opt.step()

        self._soft_update()
        self.train_log['critic_loss'].append(c_loss.item())
        self.train_log['actor_loss'].append(a_loss.item())
        self.train_log['alpha'].append(self.log_alpha.exp().item())


# =============================================================================
# BLOCK 5 — GEOMETRY & SETUP
# =============================================================================

def inspect_geometry(input_file: str = INPUT_FILE):
    """Print node geometry table. Run once to verify NODE_FULL_DEPTHS."""
    print(f"\n{'Node ID':20s} {'full_depth':>12s} {'invert':>10s} "
          f"{'depth@t1':>10s} {'vol@t1':>10s}")
    print("-" * 68)
    with Simulation(input_file) as sim:
        nobj = Nodes(sim)
        sim.start()
        sim.__next__()
        for n in nobj:
            try:    ie  = n.invert_elevation
            except: ie  = float('nan')
            try:    vol = n.volume
            except: vol = float('nan')
            tag = (" ← STORAGE"  if n.nodeid in ["54", "54_B"] else
                   " ← wet-well" if n.nodeid in ["JCT-2114", "JCT-3090", "65", "65_B"] else "")
            print(f"{n.nodeid:20s} {n.full_depth:12.4f} {ie:10.4f} "
                  f"{n.depth:10.4f} {vol:10.4f}{tag}")


# ── Geometry constants (NODE_FULL_DEPTHS loaded lazily by load_geometry) ──────
STORAGE_CAPACITY   = 35.0   # depth-sum range observed: 4.06–30.86m; 35m is safe upper bound
STORAGE_USE_VOLUME = False
NODE_FULL_DEPTHS   = None   # set by load_geometry() / build_stack()

# Until re-calibrated, using 7183 is conservative (overestimates background
# flooding → r_flood fires slightly too early, but does not harm CSO learning).
BASELINE_FLOODING = 7183.0   # ← REPLACE with run_baseline_episode() result


def load_geometry(input_file: str = INPUT_FILE) -> dict:
    """Load node full depths from SWMM, then override key nodes with calibrated values."""
    with Simulation(input_file) as _sim:
        node_full_depths = {n.nodeid: max(n.full_depth, 0.1) for n in Nodes(_sim)}
    node_full_depths.update({
        "JCT-2114": 17.07,   # confirmed from geometry inspection
        "JCT-3090":  4.0,    # wet-well practical max
        "65":        5.0,    # wet-well practical max
        "65_B":      6.0,    # wet-well practical max
        "54":       17.5,    # storage node, storm equilibrium ~15m
        "54_B":     17.5,    # storage node, storm equilibrium ~15m
    })
    return node_full_depths


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE FLOODING CALIBRATION
# ─────────────────────────────────────────────────────────────────────────────
def run_baseline_episode(rainfall_series: np.ndarray,
                         input_file: str = INPUT_FILE,
                         ctrl_step: int  = CONTROL_TIME_STEP,
                         physical_rain: bool = False) -> float:
    """
    Runs ONE episode with v7 defaults:
      all 7 gates = 0.5, pumps = 1.0 (always ON)

    Returns mean per-step flooding = unavoidable background level.
    The v7 baseline will be LOWER than the v6 baseline (7183/step) because
    opening 35281_B/35291_B at 0.5 (vs 0.0 in v6) reroutes flow away from
    flooding junctions. Expected range: ~5000–6500/step.

    Re-run whenever rainfall series or gate defaults change.
    """
    print("Calibrating v7 baseline (all 7 gates=0.5, pumps=1.0)...")
    use_file = input_file
    if physical_rain:
        from multistorm.physical_inp import write_physical_storm_inp
        use_file = str(write_physical_storm_inp(rainfall_series))
    sim  = Simulation(use_file)
    sim.step_advance(ctrl_step)
    nobj = Nodes(sim); lobj = Links(sim); robj = RainGages(sim)
    nids = [n.nodeid for n in nobj]

    for g in ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B"]:
        lobj[g].target_setting = 0.5
    for p in ["PUMP27@35395-3535", "PUMP28@35390-3535", "PUMP29@35445-3565"]:
        lobj[p].target_setting = 1.0
    rg1 = robj['Design_RG']
    T   = int((sim.end_time - sim.start_time).total_seconds() / ctrl_step) - 1
    sim.start()

    floods = []
    for t in range(1, T + 1):
        # Physical path: STORM15 timeseries drives rain. Legacy: API write.
        if not physical_rain:
            depth = float(rainfall_series[t - 1]) if rainfall_series[t - 1] > 0 else 0.0
            rg1.total_precip = depth if depth > 0 else 0.0
        sim.__next__()
        nobj2 = Nodes(sim)
        floods.append(sum(nobj2[n].flooding for n in nids))
    sim.close()

    bl = float(np.mean(floods))
    print(f"  mean={bl:.1f}/step | max={max(floods):.1f} | min={min(floods):.1f}")
    print(f"  → Hardcode: BASELINE_FLOODING = {bl:.1f}")
    return bl


# ── IMPORTANT: Re-run once to get the v7 baseline (7 gates at 0.5) ──────────
# The v6 baseline (7183) used gates 35281_B=35291_B=0.0. Now they're 0.5,
# which routes more flow away from flooding junctions → lower baseline.
# Uncomment in main() / build_stack for first run, then hardcode the result:
#   bl = run_baseline_episode(test_rainfall)


# =============================================================================
# BLOCK 6 — INSTANTIATE EVERYTHING (lazy via build_stack)
# =============================================================================
kb = env = agent = None
obs_dim = action_dim = None


def build_stack(seed: int = 0,
                rainfall_path: str = 'data/unused/rain/raindata.csv',
                verbose: bool = True):
    """
    Construct exactly the Trial 7 stack (KB + env + SAC).
    Safe to call after `import app` — all SWMM I/O happens here.
    """
    global test_rainfall, NODE_FULL_DEPTHS, kb, env, agent, obs_dim, action_dim

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(seed)

    test_rainfall = load_trial7_rainfall(rainfall_path)
    if verbose:
        print(f"Rainfall: {len(test_rainfall)} steps | "
              f"{test_rainfall.min():.3f}–{test_rainfall.max():.3f} mm/interval | "
              f"72-hr total {test_rainfall.sum():.1f} mm")

    NODE_FULL_DEPTHS = load_geometry()
    if verbose:
        print(f"NODE_FULL_DEPTHS: {len(NODE_FULL_DEPTHS)} nodes loaded")
        print(f"  Storage nodes  : 54={NODE_FULL_DEPTHS['54']}m, "
              f"54_B={NODE_FULL_DEPTHS['54_B']}m")
        print(f"  Wet-well nodes : JCT-2114={NODE_FULL_DEPTHS['JCT-2114']}m, "
              f"JCT-3090={NODE_FULL_DEPTHS['JCT-3090']}m, "
              f"65={NODE_FULL_DEPTHS['65']}m")
        print(f"STORAGE_CAPACITY = {STORAGE_CAPACITY}m  |  "
              f"R1 > {STORAGE_CAPACITY * 0.85:.2f}m  |  "
              f"R7 < {STORAGE_CAPACITY * 0.70:.2f}m")

    kb = SymbolicKnowledgeBase(
        node_full_depths  = NODE_FULL_DEPTHS,
        storage_capacity  = STORAGE_CAPACITY,
        baseline_flooding = BASELINE_FLOODING,
    )

    env = NeurosymbolicSWMMEnv(
        knowledge_base    = kb,
        use_volume        = STORAGE_USE_VOLUME,
        rainfall_series   = test_rainfall,
    )

    obs_dim    = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0]

    agent = SACAgent(
        obs_dim    = obs_dim,
        action_dim = action_dim,
        lr         = 1e-4,
        gamma      = 0.99,
        tau        = 0.005,
        hidden     = 256,
        buffer_cap = 50_000,
        batch_size = 256,
    )

    if verbose:
        print(f"\nEnvironment ready")
        print(f"  Device         : {device}"
              + (f" ({torch.cuda.get_device_name(device)})" if device.type == 'cuda' else ""))
        print(f"  Obs dim        : {obs_dim}  ({obs_dim - 11} raw SWMM + 11 symbolic)")
        print(f"  Act dim        : {action_dim}  (7 active gates + 3 frozen pumps)")
        print(f"  Episode length : {env.T} steps (72 hrs @ 15-min intervals)")
        print(f"  Agent          : SAC | hidden=256 | lr=1e-4 | buf=50k | batch=256")
        print(f"  target_entropy : {agent.target_entropy}  (7 learnable gate dims)")
        print(f"  baseline_flood : {BASELINE_FLOODING:.1f}/step")
        print(f"  R6 threshold   : {kb.FLOODING_THRESHOLD:.0f}  (132% of baseline)")
        print(f"  DO NOT load v5/v6 checkpoints — reward structure is different.")

    return env, agent, kb


# =============================================================================
# BLOCK 7 — EVALUATION (v7 — correct baseline, no depth_penalty)
# =============================================================================
def run_evaluation(node_full_depths: dict   = NODE_FULL_DEPTHS,
                   storage_capacity: float  = STORAGE_CAPACITY,
                   baseline_flooding: float = BASELINE_FLOODING):
    """
    Sanity-check KB reward shaping with hand-crafted scenarios.

    All 4 v6 evaluation bugs are fixed:
      1. eval_kb receives baseline_flooding=7183 (not 0) → r_flood=0 below baseline
      2. depth_penalty display removed (not in shape_reward since v6)
      3. 35281_B/35291_B shown as active (not frozen)
      4. R1/R2 projection shown separately from a[3]/a[4] passthrough
    """
    eval_kb = SymbolicKnowledgeBase(
        node_full_depths  = node_full_depths,
        storage_capacity  = storage_capacity,
        baseline_flooding = baseline_flooding,
    )

    print(f"\n{'='*64}")
    print(f"  EVALUATION — KB sanity check (v7)")
    print(f"{'='*64}")
    print(f"  baseline_flooding  = {baseline_flooding:.1f}  (r_flood = 0 below this)")
    print(f"  R6 threshold       = {eval_kb.FLOODING_THRESHOLD:.0f}")
    print(f"  R1R2 gates         = {eval_kb.R1R2_GATE_IDXS}  (1360, 1360_B, 35263, 3530, 3530_B)")
    print(f"  a[3] (35281_B)     = ACTIVE — no R1/R2 rule applied")
    print(f"  a[4] (35291_B)     = ACTIVE — no R1/R2 rule applied")

    # Raw action: all 7 gates at 0.4, pumps at 1.0
    raw_action = np.array([0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 1.0, 1.0, 1.0])

    def _make_obs(fill_m, cso, flood):
        return {
            'node_depths':  {n: d * 0.3 for n, d in node_full_depths.items()},
            'storage_fill': fill_m,
            'pump_depths':  {},
            'cso_flow':     cso,
            'flooding':     flood,
        }

    scenarios = [
        ("Storage 30% — gate-close incentive active",
         storage_capacity * 0.30, 200.0,  500.0),
        (f"Storage at R7 warning ({storage_capacity*0.70:.1f}m — 70%)",
         storage_capacity * 0.70, 500.0,  1000.0),
        (f"Storage at R1 threshold ({storage_capacity*0.85:.1f}m — 85%)",
         storage_capacity * 0.85, 700.0,  1200.0),
        ("SEVERE flood = 13500 — R6 emergency drain",
         storage_capacity * 0.50, 1500.0, 13500.0),
    ]

    for label, fill_m, cso, flood in scenarios:
        eval_kb._prev_storage = fill_m * 0.85
        obs    = _make_obs(fill_m, cso, flood)
        proj   = eval_kb.project_action(raw_action, obs)
        preds  = eval_kb.evaluate_predicates(obs)
        eval_kb._prev_storage = fill_m * 0.85   # reset for shape_reward
        total, bd = eval_kb.shape_reward(obs, raw_action, proj)

        fill_pct   = fill_m / storage_capacity * 100.0
        r1_fires   = bool(preds[0] > 0.5)
        r6_fires   = bool(preds[5] > 0.5)
        r1r2_avg   = float(np.mean(proj[eval_kb.R1R2_GATE_IDXS]))
        excess     = max(flood - baseline_flooding, 0.0)
        exp_r_flood = -eval_kb.W_FLOOD * excess / eval_kb.REWARD_SCALE

        print(f"\n  ── {label}")
        print(f"     fill={fill_pct:.0f}% | cso={cso:.0f} | flood={flood:.0f} | "
              f"R1={r1_fires} | R6={r6_fires}")
        print(f"     R1R2 gates avg : raw=0.40 → proj={r1r2_avg:.2f}")
        print(f"     a[3] 35281_B   : raw=0.40 → proj={proj[3]:.2f}  (no R1/R2)")
        print(f"     a[4] 35291_B   : raw=0.40 → proj={proj[4]:.2f}  (no R1/R2)")
        print(f"     excess_flood   : max({flood:.0f}−{baseline_flooding:.0f}, 0) = "
              f"{excess:.0f}  →  expected r_flood={exp_r_flood:.4f}")
        print(f"     {'─'*42}")
        for k, v in bd.items():
            flag = ""
            if k == 'flood_penalty' and abs(v - exp_r_flood) > 0.001:
                flag = "  ← MISMATCH — check baseline_flooding"
            print(f"     {k:<18s} {v:>+10.4f}{flag}")
        print(f"     {'total':<18s} {total:>+10.4f}")

    print(f"\n  Checks:")
    print(f"   r_flood = 0 when flood ≤ {baseline_flooding:.0f}  (scenarios 1–3 above)")
    thr = 13500.0
    exp = -eval_kb.W_FLOOD * max(thr - baseline_flooding, 0.0) / eval_kb.REWARD_SCALE
    print(f"   r_flood < 0 when flood > baseline  (scenario 4: {exp:.3f})")
    print(f"   a[3]/a[4] unchanged by projection  ✓")
    print(f"   r_viol not present in reward  ✓  (removed — caused oscillation)")
    print(f"{'='*64}\n")



# =============================================================================
# BLOCK 8 — TRAINING LOOP (v7)
# =============================================================================
def train(env: NeurosymbolicSWMMEnv,
          agent: SACAgent,
          rainfall_series: np.ndarray,
          n_episodes:     int  = 1000,
          update_every:   int  = 4,
          warm_up_steps:  int  = 2000,
          log_every:      int  = 10,
          save_every:     int  = 100,
          checkpoint_dir: str  = './checkpoints_v7') -> dict:
    """
    v7 SAC training with standard random warm-up.

    warm_up_steps = 2000 random steps (~7 episodes).
    HoFPolicy is NOT used — it was trained for CSO+flooding objective,
    not CSO-only, and gave worse CSO than SAC at ep406 (304k vs 291k).

    Per-episode log columns:
      Score     total episode reward (higher = better)
      Avg(N)    rolling mean over last N episodes
      CSO       cumulative CSO flow per episode (lower = better)
      Stor      storage fill range min–max (m)
      FloodMax  peak per-step flooding (watch for agent-caused surges)
      R6%       fraction of steps with severe flooding (target < 1%)
      alpha     SAC temperature (rising = more exploration; stable = converged)

    Gate positions printed per log interval:
      Watch a[3] (35281_B) and a[4] (35291_B):
        If agent learns CSO objective correctly, they should tend OPEN (> 0.5)
        since opening them routes flow away from CSO outlets.

    Convergence criteria:
      ep500  : score consistently better than −870  (5% CSO reduction)
      ep1000 : score > −800                         (10%+ CSO reduction)
      Plateau: no improvement over 200 consecutive episodes → use best_model.pt
    """
    os.makedirs(checkpoint_dir, exist_ok=True)
    history = {k: [] for k in [
        'scores', 'cso_totals', 'storage_max', 'storage_min',
        'flooding_totals', 'flooding_max', 'r6_pct', 'breakdown_sums'
    ]}
    global_step = 0
    best_score  = -np.inf

    for ep in range(n_episodes):
        env._rain = np.asarray(rainfall_series, dtype=np.float64)
        state, _ = env.reset()
        done  = False
        score = 0.0

        while not done:
            if global_step < warm_up_steps:
                action = to_device(np.random.uniform(0.0, 1.0, action_dim))
            else:
                action = agent.select_action(state)

            next_state, reward, terminated, truncated, _ = env.step(action)
            done = bool(terminated or truncated)
            agent.store(state, action, reward, next_state, done)
            score       += reward
            global_step += 1

            if global_step % update_every == 0:
                agent.update()

            state = next_state

        # ── Episode statistics ────────────────────────────────────────────
        ep_store = env.ep_storage
        ep_flood = env.ep_flooding
        r6_frac  = (sum(p[5] for p in env.ep_predicates)
                    / max(len(env.ep_predicates), 1))

        history['scores'].append(score)
        history['cso_totals'].append(sum(env.ep_cso_flows))
        history['storage_max'].append(max(ep_store) if ep_store else 0.0)
        history['storage_min'].append(min(ep_store) if ep_store else 0.0)
        history['flooding_totals'].append(sum(ep_flood))
        history['flooding_max'].append(max(ep_flood) if ep_flood else 0.0)
        history['r6_pct'].append(r6_frac * 100.0)

        bd = {}
        if env.ep_breakdowns:
            for k in env.ep_breakdowns[0]:
                bd[k] = sum(b[k] for b in env.ep_breakdowns)
        history['breakdown_sums'].append(bd)

        # ── Save best model ───────────────────────────────────────────────
        if score > best_score:
            best_score = score
            torch.save(
                {'actor': agent.actor.state_dict(),
                 'critic': agent.critic.state_dict(),
                 'ep': ep + 1},
                os.path.join(checkpoint_dir, 'best_model.pt'))

        # ── Periodic logging ──────────────────────────────────────────────
        if (ep + 1) % log_every == 0:
            sl    = slice(-log_every, None)
            avg   = np.mean(history['scores'][sl])
            cso   = np.mean(history['cso_totals'][sl])
            s_max = np.mean(history['storage_max'][sl])
            s_min = np.mean(history['storage_min'][sl])
            f_max = np.mean(history['flooding_max'][sl])
            r6    = np.mean(history['r6_pct'][sl])
            alp   = agent.log_alpha.exp().item()
            bd_avg = ({k: np.mean([h[k] for h in history['breakdown_sums'][sl] if k in h])
                       for k in bd} if bd else {})

            # Gate position diagnostics (last episode)
            proj_arr   = np.array(env.ep_proj_actions)
            gate_means = proj_arr.mean(axis=0) if len(proj_arr) > 0 else np.zeros(10)

            phase = "warm" if global_step <= warm_up_steps else "SAC "
            print(f"[{phase}] Ep {ep+1:4d} | Score {score:8.2f} | "
                  f"Avg({log_every}) {avg:8.2f} | CSO {cso:8.0f} | "
                  f"Stor {s_min:.1f}–{s_max:.1f}m | "
                  f"FldMax {f_max:7.0f} | R6% {r6:4.1f}% | α={alp:.3f}")
            if bd_avg:
                print(f"         cso={bd_avg.get('cso_penalty',0):+.1f}  "
                      f"flood={bd_avg.get('flood_penalty',0):+.1f}  "
                      f"close={bd_avg.get('gate_close',0):+.4f}")
            if len(gate_means) >= 7:
                print(f"         1360={gate_means[0]:.2f} 1360B={gate_means[1]:.2f} "
                      f"35263={gate_means[2]:.2f} "
                      f"35281B={gate_means[3]:.2f} 35291B={gate_means[4]:.2f} "
                      f"3530={gate_means[5]:.2f} 3530B={gate_means[6]:.2f}")

        # ── Periodic checkpoint ───────────────────────────────────────────
        if (ep + 1) % save_every == 0:
            p = os.path.join(checkpoint_dir, f'sac_ep{ep+1}.pt')
            torch.save(
                {'actor': agent.actor.state_dict(),
                 'critic': agent.critic.state_dict(),
                 'ep': ep + 1, 'history': history}, p)
            print(f"  ↳ Checkpoint saved: {p}")

    return history


def load_checkpoint(agent: SACAgent, path: str) -> dict:
    """
    Resume v7 training from a saved checkpoint.
    WARNING: do NOT load v5 or v6 checkpoints — reward structure changed.
    """
    ckpt = torch.load(path, map_location=device)
    agent.actor.load_state_dict(ckpt['actor'])
    agent.critic.load_state_dict(ckpt['critic'])
    agent.critic_target.load_state_dict(ckpt['critic'])
    print(f"Loaded checkpoint from ep {ckpt['ep']}: {path}")
    return ckpt.get('history', {})


# =============================================================================
# BLOCK 9 — POST-TRAINING ANALYSIS
# =============================================================================
def print_final_summary(history: dict, tail: int = 50):
    """Compare first vs last N episodes to quantify improvement."""
    n    = len(history['scores'])
    head = min(tail, n)

    print("\n" + "=" * 64)
    print("  TRAINING SUMMARY — v7")
    print("=" * 64)
    print(f"  {'Metric':<22s}  {'First 50':>10s}  {'Last 50':>10s}  {'Δ':>10s}")
    print(f"  {'─'*58}")

    for label, key in [("Episode score",    "scores"),
                        ("CSO total/ep",     "cso_totals"),
                        ("Max flooding/ep",  "flooding_max"),
                        ("R6% (emergency)",  "r6_pct")]:
        early = np.mean(history[key][:head])
        late  = np.mean(history[key][-tail:])
        delta = late - early
        pct   = (delta / abs(early) * 100) if abs(early) > 1e-6 else 0.0
        sign  = "+" if delta > 0 else ""
        print(f"  {label:<22s}  {early:>10.1f}  {late:>10.1f}  "
              f"{sign}{delta:.1f} ({pct:+.1f}%)")

    print(f"  {'─'*58}")
    ec = np.mean(history['cso_totals'][:head])
    lc = np.mean(history['cso_totals'][-tail:])
    if ec > 0:
        print(f"  CSO reduction vs early  : {(ec - lc) / ec * 100:.1f}%")
    bi = int(np.argmax(history['scores'])) + 1
    print(f"  Best episode            : {bi}  (score = {max(history['scores']):.1f})")
    print("=" * 64)


def plot_training_history(history: dict,
                          save_path: str = './training_v7.png'):
    """
    4-panel training analysis:
      Panel 1: Episode score with target lines
      Panel 2: Cumulative CSO per episode (primary objective)
      Panel 3: Storage fill range with R1/R7 threshold lines
      Panel 4: Reward component breakdown (rolling averages)
    """
    n   = len(history['scores'])
    eps = np.arange(1, n + 1)
    win = min(20, max(n // 10, 1))
    roll = lambda x: pd.Series(x).rolling(win, min_periods=1).mean().values

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f'Neurosymbolic SAC v7  |  lr=1e-4  |  buf=50k  |  target_ent=-7\n'
        f'r_viol/r_storage REMOVED  |  35281B/35291B ACTIVE  |  baseline={BASELINE_FLOODING:.0f}',
        fontsize=10)

    # ── Score ─────────────────────────────────────────────────────────────
    ax = axes[0, 0]
    ax.plot(eps, history['scores'], alpha=0.2, color='steelblue', lw=0.5)
    ax.plot(eps, roll(history['scores']), color='steelblue', lw=2,
            label=f'Rolling avg ({win}ep)')
    ax.axhline(-900, color='gray',   ls=':',  lw=1,   label='Approx start (−900)')
    ax.axhline(-700, color='orange', ls='--', lw=1.2, label='Target −700 (10% CSO red.)')
    ax.axhline(-600, color='green',  ls='--', lw=1.2, label='Stretch −600 (20% CSO red.)')
    ax.set_title('Episode Score  ↑ = better')
    ax.set_xlabel('Episode'); ax.set_ylabel('Score')
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # ── CSO ───────────────────────────────────────────────────────────────
    ax = axes[0, 1]
    ax.plot(eps, history['cso_totals'], alpha=0.2, color='darkorange', lw=0.5)
    ax.plot(eps, roll(history['cso_totals']), color='darkorange', lw=2,
            label=f'Rolling avg ({win}ep)')
    ax.set_title('Cumulative CSO / Episode  ↓ = better')
    ax.set_xlabel('Episode'); ax.set_ylabel('Total CSO flow')
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # ── Storage fill ──────────────────────────────────────────────────────
    ax = axes[1, 0]
    ax.fill_between(eps, history['storage_min'], history['storage_max'],
                    alpha=0.2, color='teal', label='Min–Max band')
    ax.plot(eps, roll(history['storage_max']), color='teal', lw=1.5,
            label=f'Max (rolling {win}ep)')
    ax.axhline(STORAGE_CAPACITY * 0.85, color='tomato', ls='--', lw=1,
               label=f'R1 ({STORAGE_CAPACITY*0.85:.1f}m)')
    ax.axhline(STORAGE_CAPACITY * 0.70, color='orange', ls='--', lw=1,
               label=f'R7 ({STORAGE_CAPACITY*0.70:.1f}m)')
    ax.set_title('Storage Fill (m)'); ax.set_xlabel('Episode'); ax.set_ylabel('Depth (m)')
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    # ── Reward breakdown ──────────────────────────────────────────────────
    ax = axes[1, 1]
    components = [
        ('cso_penalty',   'tomato',         'CSO penalty (primary)'),
        ('flood_penalty', 'firebrick',       'Flood penalty'),
        ('gate_close',    'royalblue',       'Gate-close incentive'),
    ]
    for key, color, label in components:
        vals = [bd.get(key, 0.0) for bd in history['breakdown_sums']]
        ax.plot(eps, roll(vals), color=color, lw=1.5, label=label)
    ax.axhline(0, color='black', lw=0.5)
    ax.set_title(f'Reward Components (rolling {win}ep avg)')
    ax.set_xlabel('Episode'); ax.set_ylabel('Sum per episode')
    ax.legend(fontsize=8); ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved → {save_path}")
    plt.show()


# =============================================================================
# BLOCK 10 — RUN
# =============================================================================
def main():
    global test_rainfall, kb, env, agent

    env, agent, kb = build_stack(seed=0, verbose=True)
    run_evaluation()

    print("\n" + "=" * 60)
    print("  STARTING v7 TRAINING")
    print("=" * 60)
    print(f"  Episodes       : 1000")
    print(f"  Warm-up steps  : 2000 (random — ~7 episodes)")
    print(f"  Total SWMM calls: {1000 * env.T:,}  (~{1000 * env.T * 0.9 / 3600:.1f} sim-hours)")
    print(f"  Checkpoint dir : ./checkpoints_v7/")
    print(f"  Est. wall time : 2–4 hours (CPU)")
    print(f"  IMPORTANT: re-run BASELINE_FLOODING = run_baseline_episode()")
    print(f"             before the first long training run.")
    print("=" * 60)

    # Optional: re-calibrate baseline before training
    # bl = run_baseline_episode(test_rainfall)
    # kb.baseline_flooding = bl

    history = train(
        env             = env,
        agent           = agent,
        rainfall_series = test_rainfall,
        n_episodes      = 1000,
        update_every    = 4,
        warm_up_steps   = 2000,
        log_every       = 10,
        save_every      = 100,
        checkpoint_dir  = './checkpoints_v7',
    )

    print_final_summary(history)
    plot_training_history(history, save_path='./training_v7.png')


if __name__ == "__main__":
    main()

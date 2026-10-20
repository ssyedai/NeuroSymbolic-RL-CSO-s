"""Opt-in complete-overflow experiment; legacy app.py remains unchanged.

User-confirmed 2026-10-10: 54/65/54_B/65_B are untreated outfalls;
JCT-2112/JCT-3090 are excluded conveyance outlets. JCT-2114 is an upstream junction. CFS input only.
Volumes use SWMM cumulative node statistics, not 15-minute quadrature.
"""
from pathlib import Path
import re

import numpy as np

from app import NeurosymbolicSWMMEnv
from multistorm.kb_v8 import KnowledgeBaseV8

FT3_TO_M3 = 0.028316846592
CSO_OUTFALLS = ("54", "65", "54_B", "65_B")
TREATED_OUTFALLS = ("JCT-2112", "JCT-3090")
COMPLETE_BASELINE_TAG = "v6|physrain|nativefix|all4outfalls|gross_outward|nodeflood|external_control|72h"
EXPLORATORY_BASELINE_TAG = COMPLETE_BASELINE_TAG + "|exploratory|native_step_sensitive"


def storage_capacities(inp):
    """Integrate this INP's tabulated depth-area curves (ft, ft² -> ft³)."""
    sections, section = {}, None
    for line in Path(inp).read_text().splitlines():
        line = line.split(";", 1)[0].strip()
        if line.startswith("["):
            section = line.upper()
            sections.setdefault(section, [])
        elif line and section:
            sections[section].append(line.split())
    curves = {}
    for row in sections.get("[CURVES]", []):
        curves.setdefault(row[0], []).append((float(row[-2]), float(row[-1])))
    crest = {}
    for row in sections.get("[WEIRS]", []):
        crest[row[1]] = min(crest.get(row[1], float("inf")), float(row[4]))
    capacities, usable = {}, {}
    for row in sections["[STORAGE]"]:
        if row[4].upper() != "TABULAR":
            raise ValueError("Complete-overflow prototype requires tabulated storage curves")
        curve = np.array(sorted(curves[row[5]]))
        def volume(depth):
            if curve[0, 0] > 0:
                raise ValueError("Storage curve must start at zero depth")
            if depth > curve[-1, 0] and curve[-1, 1] != curve[-2, 1]:
                raise ValueError("Non-horizontal storage extrapolation is not supported")
            # SWMM extends a horizontal final area segment at constant area.
            x = np.r_[0, curve[(curve[:, 0] > 0) & (curve[:, 0] < depth), 0], depth]
            return float(np.trapz(np.interp(x, curve[:, 0], curve[:, 1]), x))
        capacities[row[0]] = volume(float(row[2]))
        usable[row[0]] = volume(min(float(row[2]), crest.get(row[0], float(row[2]))))
    return capacities, usable


class CompleteOverflowEnv(NeurosymbolicSWMMEnv):
    """Same action interface, with complete physical volume accounting."""

    def __init__(self, *args, **kwargs):
        kwargs["full_horizon"] = True
        super().__init__(*args, **kwargs)

    def _init_sim(self):
        self._previous_volumes = None
        self._control_rules_removed = False
        if self.physical_rain and not self.native_mode:
            path = Path(self.input_file).resolve()
            if path.parent != Path("runs/_physical_inp").resolve():
                raise ValueError("Only generated episode INPs may have native controls removed")
            text = path.read_text()
            def control_section(match):
                if not self.native_pumps:
                    return "[CONTROLS]\n; External gates and pumps; no native actuator rules.\n\n"
                blocks = re.split(r"(?im)^(?=RULE\s)", match.group(0))
                kept = []
                for block in blocks:
                    if re.search(r"(?im)^\s*(THEN|ELSE|AND)\s+PUMP\s", block):
                        if re.search(r"(?im)^\s*(THEN|ELSE|AND)\s+(ORIFICE|CONDUIT|WEIR|OUTLET)\s", block):
                            raise ValueError("Cannot separate mixed pump/gate control rule")
                        kept.append(block)
                if not kept:
                    raise ValueError("Native pump interlock rules missing")
                return "[CONTROLS]\n; External gates; original pump rules retained.\n" + "\n".join(kept) + "\n"
            text, count = re.subn(r"(?ms)^\[CONTROLS\][^\r\n]*\r?\n.*?(?=^\[|\Z)",
                                  control_section, text)
            if count != 1:
                raise ValueError("Expected exactly one native CONTROLS section")
            path.write_text(text)
            self._control_rules_removed = True
        self._vol_capacity, self._usable_capacity = storage_capacities(self.input_file)
        super()._init_sim()
        self.sim.add_after_end(self._finalize_accounting)
        if self.sim.flow_units != "CFS":
            raise ValueError("CompleteOverflowEnv requires FLOW_UNITS CFS")
        if set(CSO_OUTFALLS + TREATED_OUTFALLS) != set(self.outfall_ids):
            raise ValueError("Outfall inventory differs from confirmed classification")
        # Cumulative outfall inflow counts reverse inflow too. The untreated
        # outlets must retain their physical flap gates for this fast accounting.
        section = ""
        protected = set()
        for line in Path(self.input_file).read_text().splitlines():
            fields = line.split(";", 1)[0].split()
            if not fields:
                continue
            if fields[0].startswith("["):
                section = fields[0].upper()
            elif section == "[OUTFALLS]" and len(fields) >= 5 and fields[4].upper() == "YES":
                protected.add(fields[0])
        if not set(CSO_OUTFALLS).issubset(protected):
            raise ValueError("CSO reverse flow is possible: routing-step signed accounting is required")

    def _refresh_state(self):
        super()._refresh_state()
        out = {n: float(self._node_obj[n].cumulative_inflow) * FT3_TO_M3
               for n in self.outfall_ids}
        flood = {n: float(self._node_obj[n].statistics["flooding_volume"]) * FT3_TO_M3
                 for n in self.list_nodes if n not in self.outfall_ids}
        now = dict(cso=sum(out[n] for n in CSO_OUTFALLS), flood=sum(flood.values()))
        previous = self._previous_volumes or now
        cso_step = max(0.0, now["cso"] - previous["cso"])
        flood_step = max(0.0, now["flood"] - previous["flood"])
        self._obs_dict.update(
            # Interval means capture spills missed by a 15-minute endpoint.
            cso_flow=cso_step / (900.0 * FT3_TO_M3),
            flooding=flood_step / (900.0 * FT3_TO_M3),
            cso_step_m3=cso_step, flood_step_m3=flood_step,
        )
        volumes = {n: float(self._node_obj[n].volume) for n in self.storage_ids}
        physical_unit_fill = {n: volumes[n] / self._vol_capacity[n] for n in volumes}
        usable_unit_fill = {
            n: min(volumes[n], self._usable_capacity[n]) / self._usable_capacity[n]
            for n in volumes
        }
        physical_fill_ratio = sum(volumes.values()) / sum(self._vol_capacity.values())
        usable_fill_ratio = (
            sum(min(volumes[n], self._usable_capacity[n]) for n in volumes)
            / sum(self._usable_capacity.values())
        )
        self._obs_dict["storage_fill"] = sum(volumes.values()) * FT3_TO_M3
        self._obs_dict["storage_unit_fill"] = physical_unit_fill
        self._obs_dict["physical_store_fill_ratio"] = physical_fill_ratio
        self._obs_dict["usable_storage_unit_fill"] = usable_unit_fill
        # The complete-objective symbolic state follows capacity available
        # before overflow, not volume above an overflow crest.
        self._obs_dict["store_fill_ratio"] = usable_fill_ratio
        self._obs_dict["usable_store_fill_ratio"] = usable_fill_ratio
        self._previous_volumes = now
        from pyswmm import SystemStats
        routing = SystemStats(self.sim).routing_stats
        gross_outward = float(routing["outflow"]) * FT3_TO_M3
        treated = max(0.0, gross_outward - now["cso"])
        if not self._control_rules_removed:
            control_owner = "INP native"
            pump_control = "INP native"
        elif self.policy_controls_pumps:
            control_owner = "external gates and pumps"
            pump_control = "external policy"
        else:
            control_owner = "external gates"
            pump_control = "ON" if not self.native_pumps else "INP native"
        self._accounting = dict(
            volume_units="m3", volume_method="SWMM cumulative node statistics",
            control_owner=control_owner,
            pump_control=pump_control,
            flow_sampling="15-minute interval means from cumulative volumes",
            cso_definition="54+65+54_B+65_B", overflow_accounting_complete=True,
            cso_total=now["cso"], flood_total=now["flood"],
            cso_vol_m3=now["cso"], flood_vol_m3=now["flood"],
            total_overflow_vol_m3=now["cso"] + now["flood"],
            treated_outfall_vol_m3=treated,
            cumulative_outfall_inflow_vol_m3=sum(out.values()),
            boundary_reverse_inflow_vol_m3=max(0.0, sum(out.values()) - gross_outward),
            system_outflow_vol_m3=gross_outward,
            system_flood_vol_m3=float(routing["flooding"]) * FT3_TO_M3,
            flooding_definition="SWMM node statistics; includes ponding, right-endpoint integration",
            flooded_nodes=sum(v > 1e-6 for v in flood.values()),
            **{f"cso_outfall_{n}_vol_m3": out[n] for n in CSO_OUTFALLS},
        )
        captured = self._accounting["treated_outfall_vol_m3"]
        self._accounting["capture_ratio"] = captured / (captured + now["cso"]) if captured + now["cso"] > 0 else float("nan")
        self._node_flood_volumes = flood

    def _finalize_accounting(self):
        self._accounting.update(routing_error_pct=float(self.sim.flow_routing_error),
                                runoff_error_pct=float(self.sim.runoff_error))

    @staticmethod
    def _cleanup_owned(path):
        path = Path(path).resolve()
        root = Path("runs/_physical_inp").resolve()
        if path.parent == root and re.fullmatch(r"storm_\d+_[0-9a-f]{8}\.inp", path.name):
            for suffix in (".inp", ".out", ".rpt"):
                path.with_suffix(suffix).unlink(missing_ok=True)

    def reset(self, **kwargs):
        previous = self.input_file
        result = super().reset(**kwargs)
        self._cleanup_owned(previous)
        return result

    def close(self):
        super().close()
        self._cleanup_owned(self.input_file)

    def _clear_logs(self):
        super()._clear_logs()
        self._explanations = []
        self._usable_fill = []
        self._actual_actions = []
        self._target_actions = []
        self._node_peak_depths = {}

    def step(self, action, rainfall_series=None):
        result = super().step(action, rainfall_series)
        ids = ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B",
                   "PUMP27@35395-3535", "PUMP28@35390-3535", "PUMP29@35445-3565"]
        actual = np.asarray([self._link_obj[g].current_setting for g in ids])
        self._actual_actions.append(actual)
        self._target_actions.append(np.asarray([self._link_obj[g].target_setting for g in ids]))
        if self.native_mode:
            self.ep_proj_actions[-1] = actual
            self.ep_raw_actions[-1] = actual.copy()
        self._explanations.append(list(getattr(self.kb, "last_info", {}).get("explanations", [])))
        self._usable_fill.append(self._obs_dict["usable_store_fill_ratio"])
        if result[2] or result[3]:
            from pyswmm import SystemStats
            stats = SystemStats(self.sim).routing_stats
            self._accounting["system_outflow_vol_m3"] = stats["outflow"] * FT3_TO_M3
            self._accounting["system_flood_vol_m3"] = stats["flooding"] * FT3_TO_M3
            self._accounting["simulated_steps"] = self.t - 1
            self._node_peak_depths = {n: float(self._node_obj[n].statistics["max_depth"])
                                      for n in self.list_nodes}
            self.close()
        return result

    def get_episode_log(self):
        log = super().get_episode_log()
        log.update(accounting_summary=dict(self._accounting),
                   cso_definition=self._accounting["cso_definition"],
                   node_flood_volumes_m3=dict(self._node_flood_volumes),
                   actions_actual=np.asarray(self._actual_actions),
                   actions_target=np.asarray(self._target_actions),
                   node_peak_depth_ft=dict(getattr(self, "_node_peak_depths", {})),
                   rule_explanations=list(self._explanations),
                   usable_store_fill_ratio=np.asarray(self._usable_fill))
        return log


class CompleteOverflowKB(KnowledgeBaseV8):
    """Flood-priority candidate: prevent routine untreated bypass discharge.

    This reactive shield is interpretable, not a proof of hydraulic safety.
    Emergency openings may trade CSO for flood relief; the four-outfall reward
    ensures this release is still charged to the controller.
    """
    def project_action(self, raw, obs):
        a = super().project_action(raw, obs)
        direct = [g for g, ctx in self.topo.items()
                  if ctx.get("cso_outfalls_down") and not ctx.get("storage_down")]
        # Backward compatibility for old generated topology CSVs. New topology
        # files identify these gates from the graph instead of their indices.
        if not direct and not any("cso_outfalls_down" in ctx for ctx in self.topo.values()):
            direct = [3, 4]
        for gate in direct:
            ctx = self.topo[gate]
            risk = max(self._dr(obs, ctx["risk_up"]) or [0.0])
            emergency = risk >= self.theta["theta_f"] or float(obs["flooding"]) > self.theta["flood_cfs"]
            if not emergency and a[gate] > 0:
                self.last_info["explanations"].append(dict(
                    gate_idx=gate, rule="BYPASS_CLOSE", proposed=float(a[gate]), applied=0.0,
                    upstream_depth_ratio=float(risk), reason="Untreated bypass; no upstream flood trigger",
                    affected_outfalls=list(ctx.get("cso_outfalls_down", []))))
                a[gate] = 0.0
        self.last_info["intervention"] = float(np.abs(a[:7] - np.clip(np.asarray(raw)[:7], 0, 1)).mean())
        return a

    def cost(self, obs):
        # Physical flood volume; no cfs-step/m3 mismatch. The absolute flood
        # constraint may be infeasible for extreme storms: stop rather than relax.
        return float(obs["flood_step_m3"]) / self.v_scale

    def shape_reward(self, obs, raw, proj):
        cso = float(obs["cso_step_m3"])
        flood = float(obs["flood_step_m3"])
        # A fixed physical scale avoids enormous rewards on zero-CSO references.
        cso_penalty = -self.w_cso * cso / self.v_scale
        flood_penalty = -10.0 * self.w_cso * flood / self.v_scale
        fill = float(obs["usable_store_fill_ratio"])
        store = -self.w_store * float(cso > 0.01) * max(0, 1 - self.theta["delta"] - fill) / self.T
        total = cso_penalty + flood_penalty + store
        return total, dict(cso_penalty=cso_penalty, flood_penalty=flood_penalty,
                          store_first=store, gate_close=0.0, cost=self.cost(obs), total=total)

"""Run FIRST. Answers: what are nodes 54/54_B/65/65_B? is 'storage fill' rain-dependent? is native mode native? which units?"""
import re
import numpy as np
import pandas as pd
from pyswmm import Simulation, Nodes, Links
from multistorm import adapters as A
from multistorm.storms import load_storms, Storm

INP = "7MPF_CSO_08.inp"
WATCH = ["54", "54_B", "65", "65_B", "JCT-2114", "JCT-3090"]
GATES = ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B"]

with Simulation(INP) as sim:                                  # pyswmm API names: [VERIFY] against your version
    nd = pd.DataFrame([dict(id=n.nodeid, outfall=n.is_outfall(), storage=n.is_storage(), junction=n.is_junction(),
                            full_depth=n.full_depth) for n in Nodes(sim)])
    rows = []
    for l in Links(sim):
        up, dn = l.connections
        kind = ("orifice" if l.is_orifice() else "weir" if l.is_weir() else "pump" if l.is_pump()
                else "outlet" if l.is_outlet() else "conduit")
        rows.append(dict(id=l.linkid, kind=kind, up=up, dn=dn))
    lk = pd.DataFrame(rows)
    sim.start()
    init_settings = {g: Links(sim)[g].target_setting for g in GATES}
nd.to_csv("runs/diag_nodes.csv", index=False); lk.to_csv("runs/diag_links.csv", index=False)
print(nd[nd.id.isin(WATCH)].to_string()); print("node types:", nd[["outfall", "storage", "junction"]].sum().to_dict())
print(lk[lk.kind.isin(["orifice", "weir", "pump", "outlet"])].to_string())
txt = open(INP).read()
print(re.findall(r"FLOW_UNITS\s+\w+", txt)); print(re.search(r"\[RAINGAGES\][\s\S]{0,500}", txt).group(0))
print("INP-native initial gate settings:", init_settings)
STORAGE = list(nd.loc[nd.storage, "id"])

from pathlib import Path
_RAIN = next((p for p in ("rain_real_full", "data/useful/rain_real_full")
              if Path(p).is_dir()), "data/useful/rain_real_full")
env, agent, kb = A.build(0)
storms = load_storms(_RAIN, scaling="none")
wet = max(storms, key=lambda s: s.depth.sum())
dry = Storm("dry", "diag", np.zeros(288), np.zeros(288), "test", {"scaling": "none"})
big = Storm("wet_x3", "diag", wet.intensity * 3, wet.depth * 3, "test", {"scaling": "none"})
print(f"diag rain dir: {_RAIN}  (n_storms={len(storms)}, wet={wet.storm_id})")


def run(storm, native=False):
    env.reset(options={"storm": storm, "baseline_flooding": 0.0, "physical_rain": True, "native": native})
    d = {n: [] for n in STORAGE + WATCH}
    first = {g: env._link_obj[g].target_setting for g in GATES}
    done = False
    while not done:
        _, _, term, trunc, _ = env.step(np.full(10, 0.5))
        for n in STORAGE + WATCH:
            d[n].append(env._node_obj[n].depth)
        done = bool(term or trunc)
    return pd.DataFrame(d), first


d0, f_non = run(dry); d1, _ = run(wet); d3, _ = run(big)
wet_response = (d1[STORAGE] - d0[STORAGE]).abs().max()
big_response = (d3[STORAGE] - d0[STORAGE]).abs().max()
print("real storage nodes:", STORAGE)
print("max |storage depth(wet)-depth(dry)| (ft):\n", wet_response.round(4).to_string())
print("max |storage depth(x3)-depth(dry)| (ft):\n", big_response.round(4).to_string())
_, f_nat = run(wet, native=True)
env.close()
print("initial gate settings: non-native", f_non, "| native-mode", f_nat, "| INP-native", init_settings)

checks = {
    "storage_count_positive": len(STORAGE) > 0,
    "storage_responds_to_rain": float(wet_response.max()) > 0.0,
    "native_initial_matches_inp": all(abs(f_nat[g] - init_settings[g]) < 1e-12 for g in GATES),
    "flow_units_known": bool(re.search(r"FLOW_UNITS\s+(CFS|GPM|MGD|CMS|LPS|MLD)", txt)),
}
print("G0 checks:", checks)
if not all(checks.values()):
    raise SystemExit("G0 FAIL: " + ", ".join(k for k, value in checks.items() if not value))
print("G0: PASS")

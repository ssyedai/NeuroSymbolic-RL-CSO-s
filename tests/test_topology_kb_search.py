import numpy as np
import pandas as pd
from research.topology import build_graph, gate_context, to_kb_dict
from research.controllability import SchedulePolicy, static_search, cma_search, objective
from research.optimize_rules import decode, optimize
from multistorm.kb_v8 import KnowledgeBaseV8


def net():
    nodes = pd.DataFrame([dict(id=i, storage=i in ("S1",), junction=i.startswith("J")) for i in
                          ["J1", "J2", "J3", "S1", "OUT"]])
    links = pd.DataFrame([
        dict(id="G0", kind="orifice", up="J1", dn="S1"),      # gate0 feeds storage, storage spills over weir W
        dict(id="G1", kind="orifice", up="J2", dn="J3"),      # gate1 goes straight to weir W2 (no storage)
        dict(id="W", kind="weir", up="S1", dn="OUT"),
        dict(id="W2", kind="weir", up="J3", dn="OUT")])
    return nodes, links


def test_topology_context():
    nodes, links = net()
    ctx = gate_context(build_graph(links), nodes, links, gates=["G0", "G1"], cso_weirs=["W", "W2"])
    r0, r1 = ctx.iloc[0], ctx.iloc[1]
    assert r0.storage_down == "S1" and r0.weirs_down == "W" and not r0.feeds_weir_without_storage
    assert r1.storage_down == "" and r1.weirs_down == "W2" and r1.feeds_weir_without_storage
    assert "J1" in r0.risk_up and "J2" in r1.risk_up
    d = to_kb_dict(ctx)
    assert d[0]["storage_down"] == ["S1"] and d[1]["storage_down"] == [] and d[1]["weirs_down"] == ["W2"]


def kb():
    full = dict(J1=10.0, J2=10.0, J3=10.0, S1=20.0)
    topo = {0: dict(risk_up=["J1"], storage_down=["S1"], weirs_down=["W"]),
            1: dict(risk_up=["J2"], storage_down=[], weirs_down=["W2"])}
    return KnowledgeBaseV8(full, ["J1", "J2", "J3"], topo, horizon=287)


def obs(depths=None, cso=0.0, flood=0.0, fill=0.3):
    return dict(node_depths=depths or dict(J1=1.0, J2=1.0, J3=1.0, S1=6.0), cso_flow=cso, flooding=flood,
                store_fill_ratio=fill, storage_unit_fill=dict(S1=fill))


def test_shield_rules():
    k, raw = kb(), np.full(10, 0.1)
    a = k.project_action(raw, obs()); assert a[0] == 0.1 and a[7:].tolist() == [1, 1, 1] and k.last_info["flags"] == dict(F1=0, F2=0, S1=0)
    a = k.project_action(raw, obs(depths=dict(J1=9.5, J2=1, J3=1, S1=6)))                      # F1 on gate 0 only
    assert a[0] == 0.5 and a[1] == 0.1 and k.last_info["flags"]["F1"] == 1
    a = k.project_action(raw, obs(cso=10.0, fill=0.4))                                          # S1: spill + headroom -> admit to storage
    assert a[0] == 0.8 and a[1] == 0.1 and k.last_info["flags"]["S1"] == 1
    a = k.project_action(raw, obs(cso=10.0, fill=0.99))                                         # storage full -> no forced opening
    assert a[0] == 0.1 and k.last_info["flags"]["S1"] == 0
    a = k.project_action(raw, obs(flood=50.0, fill=0.4))                                        # F2: gate0 has headroom -> 1.0; gate1 spills direct -> theta_f_open
    assert a[0] == 1.0 and a[1] == 0.5 and k.last_info["flags"]["F2"] == 2
    assert k.last_info["intervention"] > 0
    assert (k.project_action(np.array([0.9] * 10), obs(cso=10.0, fill=0.4))[:7] == 0.9).all()  # never lowers a gate


def test_reward_cost_and_predicates():
    k = kb(); k.set_reference(1000.0)
    t, bd = k.shape_reward(obs(cso=100.0, fill=0.2), None, None)
    assert abs(bd["cso_penalty"] - (-10 * 100 / 1000)) < 1e-12 and bd["store_first"] < 0 and bd["gate_close"] == 0.0
    t2, bd2 = k.shape_reward(obs(cso=100.0, fill=1.0), None, None); assert bd2["store_first"] == 0.0     # overflow at full storage: no penalty
    t3, bd3 = k.shape_reward(obs(cso=0.0, fill=0.1), None, None); assert t3 == 0.0
    # return of a reference-level episode ~ -w_cso
    ep = sum(k.shape_reward(obs(cso=1000.0 / 287, fill=1.0), None, None)[0] for _ in range(287)); assert abs(ep + 10.0) < 1e-6
    assert k.cost(obs()) == 0.0 and k.cost(obs(flood=100.0)) > 0
    # Depth risk drives the hard shield; the learned constraint is reserved
    # for physical flood volume so its budget matches flood non-regression.
    assert k.cost(obs(depths=dict(J1=9.0, J2=1, J3=1, S1=6))) == 0
    p = k.evaluate_predicates(obs(depths=dict(J1=9.2, J2=1, J3=1, S1=6), cso=5.0, flood=0.0, fill=0.9)); assert p.shape == (11,)
    assert p[0] == 0 and p[1] == 1 and p[2] == 1 and p[4] == 1 and p[5] == 0     # fill .9: warning yes, critical (>=.95) no
    assert k.extra_features(obs(), np.zeros(288), 5).shape == (7,)


def test_controllability_search_with_fake_evaluator():
    ref = dict(cso_total=1000.0, flood_total=0.0)
    def ev(policy, storm, proj):                                    # CSO falls as gate0 opens; flood if gate3 > 0.8
        p = policy.p.mean(axis=0)
        return dict(cso_total=1000.0 * (1 - 0.5 * p[0]), flood_total=500.0 if p[3] > 0.8 else 0.0)
    c, x, s = static_search(ev, None, ref, n=64)
    assert s["cso_total"] < 600 and s["flood_total"] == 0.0
    pol = SchedulePolicy(np.vstack([np.full(7, .2), np.full(7, .8)]), n_steps=10)
    acts = np.array([pol.select_action() for _ in range(10)])
    assert acts.shape == (10, 10) and acts[0, 0] == np.float32(.2) and acts[9, 0] == np.float32(.8) and (acts[:, 7:] == 1).all()
    f, best, s2 = cma_search(ev, None, ref, n_seg=2, iters=8, pop=8)
    assert s2["flood_total"] == 0.0 and f < 0.75


def test_rule_optimizer_finds_known_optimum():
    names = ("theta_f", "theta_s")
    def ev(theta, storm):                                           # best at theta_s = 0.6 -> lowest CSO
        return dict(cso_total=500 + 1000 * abs(theta["theta_s"] - 0.6), flood_total=0.0), dict(cso_total=1000.0, flood_total=0.0)
    th, v = optimize(ev, [0], [0], names=names, iters=15, pop=8)
    assert abs(th["theta_s"] - 0.6) < 0.1 and v < 0.6
    assert set(decode([0, 1], names)) == set(names)


def test_topology_cli_roundtrip(tmp_path):
    from research.topology import main, to_kb_dict
    nodes, links = net()
    nodes.to_csv(tmp_path / "n.csv", index=False); links.to_csv(tmp_path / "l.csv", index=False)
    import research.topology as T
    ctx = T.gate_context(T.build_graph(links), nodes, links, gates=["G0", "G1"], cso_weirs=["W", "W2"])
    ctx.to_csv(tmp_path / "g.csv", index=False)
    d = to_kb_dict(pd.read_csv(tmp_path / "g.csv"))                   # CSV round trip turns empty cells into NaN
    assert d[1]["storage_down"] == [] and d[0]["storage_down"] == ["S1"]

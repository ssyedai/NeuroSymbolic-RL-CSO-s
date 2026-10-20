"""Derive gate/storage/weir relationships from the SWMM network graph (replaces hand-written node lists)."""
from __future__ import annotations
import networkx as nx
import pandas as pd

GATES = ["1360", "1360_B", "35263", "35281_B", "35291_B", "3530", "3530_B"]   # action indices 0..6
CSO_WEIRS = ["35391", "35444"]
CSO_OUTFALLS = ["54", "65", "54_B", "65_B"]


def build_graph(links: pd.DataFrame) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    for r in links.itertuples():
        G.add_edge(r.up, r.dn, key=r.id, kind=r.kind)
    return G


def gate_context(G, nodes: pd.DataFrame, links: pd.DataFrame, gates=GATES,
                 cso_weirs=CSO_WEIRS, cso_outfalls=CSO_OUTFALLS) -> pd.DataFrame:
    nd = nodes.set_index("id")
    storage = set(nd.index[nd["storage"].astype(bool)])
    junction = set(nd.index[nd["junction"].astype(bool)])
    lk = links.set_index("id")
    rows = []
    for gi, g in enumerate(gates):
        up, dn = lk.loc[g, "up"], lk.loc[g, "dn"]
        down = nx.descendants(G, dn) | {dn}
        upstream = nx.ancestors(G, up) | {up}
        weirs = [w for w in cso_weirs if lk.loc[w, "up"] in down]
        outfalls = sorted(down & set(cso_outfalls))
        stor = sorted(down & storage)
        rows.append(dict(gate_idx=gi, gate=g, up=up, dn=dn,
                         storage_down=";".join(stor), weirs_down=";".join(weirs),
                         cso_outfalls_down=";".join(outfalls),
                         risk_up=";".join(sorted(upstream & junction)),
                         feeds_weir_without_storage=bool(weirs) and not stor,
                         feeds_cso_without_storage=bool(weirs or outfalls) and not stor))
    return pd.DataFrame(rows)


def to_kb_dict(ctx: pd.DataFrame) -> dict:
    """Convert the topology table to per-gate knowledge-base context."""
    sp = lambda s: [x for x in str(s).split(";") if x and x != "nan"]
    result = {}
    legacy_direct = {"35281_B": ["65_B"], "35291_B": ["54_B"]}
    for r in ctx.itertuples():
        direct = sp(getattr(r, "cso_outfalls_down", ""))
        if not direct:
            direct = legacy_direct.get(str(getattr(r, "gate", "")), [])
        result[int(r.gate_idx)] = dict(
            risk_up=sp(r.risk_up), storage_down=sp(r.storage_down),
            weirs_down=sp(r.weirs_down),
            cso_outfalls_down=direct,
        )
    return result


def main(nodes_csv="runs/diag_nodes.csv", links_csv="runs/diag_links.csv", out_csv="runs/gate_topology.csv"):
    nodes, links = pd.read_csv(nodes_csv), pd.read_csv(links_csv)
    ctx = gate_context(build_graph(links), nodes, links)
    ctx.to_csv(out_csv, index=False)
    print(ctx.to_string())
    bad = ctx[ctx.feeds_cso_without_storage]
    if len(bad):
        print("\nGates whose downstream reaches untreated discharge with NO storage in between:", list(bad.gate))
    return ctx


if __name__ == "__main__":
    main()

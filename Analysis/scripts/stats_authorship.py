"""Authorship network statistics (brief section 6b, 7b) with a null-model comparison (course: ER / configuration models).
Network analysed (within our institutes): nodes = faculty of IIT Kharagpur and IIT Roorkee with >= 1 analysis-set
paper; edge = the two co-authored >= 1 paper; weight = number of joint papers (from authorship_network.csv rows where
both ends are faculty). Faculty without faculty co-authors are isolated nodes.
  degree centrality   networkx degree_centrality (distinct faculty co-authors / (n-1)); also weighted degree
  betweenness         networkx betweenness_centrality, unweighted, normalised
  communities         Louvain (networkx louvain_communities, weight = joint papers, resolution 1) for 10 seeds;
                      seed 42 is reported, stability = adjusted Rand index between seeds; modularity Q
  null models         10 samples each, same number of nodes and edges:
                      ER G(n, m)                    - same density, random wiring
                      degree-preserving rewiring    - same degree of every node (double edge swaps, 10 per edge)
                      compared on clustering, transitivity, giant component, mean shortest path, assortativity, Louvain Q
  bridging faculty    faculty with the most distinct Indian partner institutions among their co-authors (all of
                      authorship_network.csv; Indian = a partner listed in indian_connections.csv)
Outputs (results/): authorship_summary.csv, faculty_centrality.csv, top_collaborators.csv, top_brokers.csv,
  communities.csv, community_stability.csv, null_model_comparison.csv, bridging_faculty.csv
Figures: coauthor_degree_ccdf.png, community_sizes.png, faculty_network.png
usage: python stats_authorship.py"""
import os, random, statistics as st, collections as C
import numpy as np
import networkx as nx
from sklearn.metrics import adjusted_rand_score
from common import (INSTS, DATA, load_records, read_csv, write_csv, style, save, COLOR, TEXT2, MUTED, GRID, plt, short_name)

SEEDS = list(range(10))
REPORT_SEED = 42


def louvain(G, seed):
    return nx.community.louvain_communities(G, weight="weight", seed=seed, resolution=1)


def labels(G, comms):
    lab = {}
    for i, c in enumerate(comms):
        for n in c:
            lab[n] = i
    return [lab[n] for n in G]


def graph_stats(H):
    giant = H.subgraph(max(nx.connected_components(H), key=len))
    return {"avg_clustering": nx.average_clustering(H), "transitivity": nx.transitivity(H),
            "giant_component_share": giant.number_of_nodes() / H.number_of_nodes(),
            "mean_shortest_path_giant": nx.average_shortest_path_length(giant),
            "degree_assortativity": nx.degree_assortativity_coefficient(H),
            "louvain_modularity": nx.community.modularity(H, nx.community.louvain_communities(H, seed=1))}


def main():
    style()
    # ------------------------------------------------ graph
    info = {}
    for inst, name in INSTS.items():
        for r in load_records(inst):
            for f in r["faculty"]:
                info[f["roster_id"]] = {"name": f["name"], "department": f["department"], "institution": name}
    G = nx.Graph()
    for rid, d in info.items():
        G.add_node(rid, **d)
    pairs = C.defaultdict(set)
    for e in read_csv(os.path.join(DATA, "authorship_network.csv")):
        if e["a_is_faculty"] == "TRUE" and e["b_is_faculty"] == "TRUE" and e["author_a_id"] in info and e["author_b_id"] in info:
            pairs[frozenset((e["author_a_id"], e["author_b_id"]))].add(e["paper_doi"] or e["author_a_id"] + e["year"])
    for p, papers in pairs.items():
        a, b = tuple(p)
        G.add_edge(a, b, weight=len(papers))
    n, m = G.number_of_nodes(), G.number_of_edges()
    cross = [(a, b) for a, b in G.edges if info[a]["institution"] != info[b]["institution"]]

    # ------------------------------------------------ centralities
    dc = nx.degree_centrality(G)
    bc = nx.betweenness_centrality(G, normalized=True)
    wdeg = dict(G.degree(weight="weight"))
    comms = sorted(louvain(G, REPORT_SEED), key=len, reverse=True)
    cid = {node: i + 1 for i, c in enumerate(comms) for node in c}
    crow = [{"roster_id": v, "faculty": info[v]["name"], "institution": info[v]["institution"], "department": info[v]["department"],
             "faculty_coauthors": G.degree(v), "joint_papers_with_faculty": wdeg[v], "degree_centrality": round(dc[v], 5),
             "betweenness": round(bc[v], 5), "community": cid[v]} for v in G]
    crow.sort(key=lambda x: -x["degree_centrality"])
    write_csv("faculty_centrality.csv", crow)
    top_c, top_b = [], []
    for name in INSTS.values():
        rows = [c for c in crow if c["institution"] == name]
        top_c += sorted(rows, key=lambda x: (-x["degree_centrality"], -x["joint_papers_with_faculty"]))[:10]
        top_b += sorted(rows, key=lambda x: -x["betweenness"])[:10]
    write_csv("top_collaborators.csv", top_c)
    write_csv("top_brokers.csv", top_b)

    # ------------------------------------------------ communities
    Q = nx.community.modularity(G, comms, weight="weight")
    runs = {s: louvain(G, s) for s in SEEDS}
    labs = {s: labels(G, c) for s, c in runs.items()}
    srows = [{"seed": s, "communities": len(c), "communities_size_ge_5": sum(1 for x in c if len(x) >= 5),
              "modularity": round(nx.community.modularity(G, c, weight="weight"), 4)} for s, c in runs.items()]
    ari = [adjusted_rand_score(labs[a], labs[b]) for i, a in enumerate(SEEDS) for b in SEEDS[i + 1:]]
    srows.append({"seed": "mean ARI between seeds", "communities": "", "communities_size_ge_5": "", "modularity": round(st.mean(ari), 4)})
    write_csv("community_stability.csv", srows)
    comrows = []
    for i, c in enumerate(comms, 1):
        if len(c) < 5:
            continue
        depts = C.Counter(info[v]["department"] for v in c)
        insts = C.Counter(info[v]["institution"] for v in c)
        hub = max(c, key=lambda v: G.degree(v))
        internal = G.subgraph(c).number_of_edges()
        comrows.append({"community": i, "faculty": len(c), "internal_edges": internal,
                        "IIT Kharagpur": insts["IIT Kharagpur"], "IIT Roorkee": insts["IIT Roorkee"],
                        "top_department": depts.most_common(1)[0][0],
                        "top_department_share": round(depts.most_common(1)[0][1] / len(c), 3),
                        "departments": len(depts), "most_connected_member": info[hub]["name"]})
    write_csv("communities.csv", comrows)

    # ------------------------------------------------ null models
    rng = random.Random(7)
    real = graph_stats(G)
    nulls = {"ER G(n,m)": [], "degree-preserving rewiring": []}
    for s in range(10):
        nulls["ER G(n,m)"].append(graph_stats(nx.gnm_random_graph(n, m, seed=s)))
        R = nx.Graph(G.edges())
        R.add_nodes_from(G)
        nx.double_edge_swap(R, nswap=10 * m, max_tries=200 * m, seed=rng.randint(0, 10 ** 9))
        nulls["degree-preserving rewiring"].append(graph_stats(R))
    nrows = []
    for k in real:
        row = {"metric": k, "faculty network": round(real[k], 4)}
        for name, samples in nulls.items():
            vals = [x[k] for x in samples]
            row[name + " mean"] = round(st.mean(vals), 4)
            row[name + " sd"] = round(st.stdev(vals), 4)
        nrows.append(row)
    write_csv("null_model_comparison.csv", nrows)

    # ------------------------------------------------ bridging faculty (Indian partner institutions)
    indian = {r["partner_inst"] for r in read_csv(os.path.join(DATA, "indian_connections.csv"))}
    partners = C.defaultdict(set)
    for e in read_csv(os.path.join(DATA, "authorship_network.csv")):
        for me, other_inst, other_fac in (("author_a_id", "inst_b", "b_is_faculty"), ("author_b_id", "inst_a", "a_is_faculty")):
            fac_side = "a_is_faculty" if me == "author_a_id" else "b_is_faculty"
            if e[fac_side] == "TRUE" and e["cross_inst"] == "TRUE" and e[me] in info:
                for x in e[other_inst].split(";"):
                    if x in indian and x not in ("Indian Institute of Technology Kharagpur", "Indian Institute of Technology Roorkee") \
                            or (x in ("Indian Institute of Technology Kharagpur", "Indian Institute of Technology Roorkee")
                                and not x.endswith(info[e[me]]["institution"].split()[-1])):
                        partners[e[me]].add(x)
    brow = []
    for name in INSTS.values():
        rows = sorted((v for v in partners if info[v]["institution"] == name), key=lambda v: -len(partners[v]))[:10]
        brow += [{"institution": name, "faculty": info[v]["name"], "department": info[v]["department"],
                  "indian_partner_institutions": len(partners[v]),
                  "examples": "; ".join(short_name(x, 30) for x in sorted(partners[v])[:5])} for v in rows]
    write_csv("bridging_faculty.csv", brow)

    # ------------------------------------------------ summary
    summ = [{"metric": k, "value": v} for k, v in [
        ("faculty (nodes)", n), ("faculty pairs with >= 1 joint paper (edges)", m),
        ("Kharagpur-Roorkee faculty pairs", len(cross)), ("isolated faculty (no faculty co-author)", sum(1 for v in G if G.degree(v) == 0)),
        ("mean faculty co-authors", round(2 * m / n, 2)), ("density", f"{nx.density(G):.4f}"),
        ("Louvain communities (seed 42)", len(comms)), ("communities with >= 5 faculty", len(comrows)),
        ("modularity Q (seed 42, weighted)", round(Q, 4)), ("mean ARI between Louvain seeds", round(st.mean(ari), 4))]]
    write_csv("authorship_summary.csv", summ)

    # ------------------------------------------------ figures
    fig, ax = plt.subplots(figsize=(6.5, 4.3))
    deg = np.array([d for _, d in G.degree()])
    er = np.array([d for _, d in nx.gnm_random_graph(n, m, seed=0).degree()])
    for arr, lab, col, ls in ((deg, "faculty network", "#2a78d6", "-"), (er, "ER G(n,m), same n and m", MUTED, (0, (3, 3)))):
        ks = np.arange(1, arr.max() + 1)
        ax.loglog(ks, [(arr >= k).mean() for k in ks], color=col, linestyle=ls, label=lab)
    ax.set_xlabel("k = number of faculty co-authors")
    ax.set_ylabel("P(degree >= k)")
    ax.set_title("Faculty co-authorship degree distribution vs ER")
    ax.legend()
    save(fig, "coauthor_degree_ccdf.png")

    fig, ax = plt.subplots(figsize=(8, 3.8))
    top = comrows[:20]
    left = np.zeros(len(top))
    for name in INSTS.values():
        vals = np.array([c[name] for c in top])
        ax.bar(range(len(top)), vals, bottom=left, color=COLOR[name], width=0.7, label=name)
        left += vals
    ax.set_xticks(range(len(top)), [str(c["community"]) for c in top], fontsize=8)
    ax.set_xlabel("community (Louvain, largest first)")
    ax.set_ylabel("faculty")
    ax.grid(axis="x", visible=False)
    ax.legend()
    ax.set_title(f"Faculty communities: {len(comrows)} with >= 5 members, Q = {Q:.2f}")
    save(fig, "community_sizes.png")

    giant = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    pos = nx.spring_layout(giant, seed=3, k=0.6 / np.sqrt(giant.number_of_nodes()), iterations=80, weight=None)
    # coloured by institute (the entity colours used in every chart); communities are in community_sizes.png
    fig, ax = plt.subplots(figsize=(9, 9))
    nx.draw_networkx_edges(giant, pos, ax=ax, edge_color=GRID, width=0.4, alpha=0.7)
    for name in INSTS.values():
        vs = [v for v in giant if info[v]["institution"] == name]
        nx.draw_networkx_nodes(giant, pos, nodelist=vs, ax=ax, node_size=[6 + 2.5 * giant.degree(v) for v in vs],
                               node_color=COLOR[name], linewidths=0.4, edgecolors="#fcfcfb", label=f"{name} ({len(vs)})")
    ax.legend(loc="lower left", fontsize=9)
    ax.set_axis_off()
    ax.set_title(f"Faculty co-authorship network: largest component ({giant.number_of_nodes()} faculty); node size = faculty co-authors")
    save(fig, "faculty_network.png")

    for s in summ:
        print(f"  {s['metric']}: {s['value']}")
    for r in nrows:
        print("  ", r)


if __name__ == "__main__":
    main()

"""Co-authorship network beyond the brief: structure, robustness, spreading and growth (course: dynamical processes).
Same faculty graph as stats_authorship.py (weight = joint papers, first_year = year of the pair's first joint paper);
Louvain communities are read from results/faculty_centrality.csv (seed 42), so run stats_authorship.py first.
  communities vs     NMI and adjusted Rand index between the Louvain partition and the department labels (department
  departments        = institute + department); attribute assortativity by department and by institute; share of ties
                     inside one department
  Leiden             leidenalg (RB configuration = modularity at resolution 1), seed 42, compared with Louvain over a
                     resolution sweep (at resolution 1, Louvain = the reported partition): communities with >= 5
                     faculty, modularity Q, ARI with the reported partition, and whether every community is connected
                     (Louvain can return disconnected ones; Leiden cannot)
  hierarchy          k-core decomposition; clustering spectrum C(k) ~ k^-beta (slope of log C(k) on log k, k >= 2);
                     rich-club coefficient phi(k) divided by its mean over 10 degree-preserving rewirings (> 1 =
                     well-connected faculty work with each other more than their degrees explain)
  small world        sigma = (C / C_rand) / (L / L_rand), against ER G(n, m) (results/null_model_comparison.csv)
  centrality vs      Spearman rho of degree / betweenness with h-index, citations and papers (results/faculty.csv),
  impact             and the partial rho of each with h-index holding the paper count fixed (rank residuals)
  robustness         share of faculty in the largest component as faculty are removed: at random (mean of 20 orders),
                     by degree and by betweenness (both recomputed after every step, 'adaptive' attacks); f_50 = share
                     removed when the largest component falls to half its size. Molloy-Reed kappa = <k^2>/<k>.
  spreading (SIR)    SIR with transmission probability T per tie and recovery after one step is exactly bond
                     percolation with occupation T (Newman 2002): the outbreak started by faculty i = the size of i's
                     cluster after keeping each tie with probability T. 1,000 samples per T. Mean-field threshold
                     T_c = <k> / (<k^2> - <k>). Spreader ranking at T = 0.2 (just above T_c): Spearman rho between each
                     centrality and the expected outbreak size (Kitsak et al. 2010: k-core beats degree).
  growth             cumulative network at the end of each year (ties by first joint paper): faculty with a tie, ties,
                     mean degree, largest component, transitivity, Kharagpur-Roorkee ties; densification exponent a
                     in E ~ N^a (Leskovec et al. 2005)
  tie types          every row of authorship_network.csv with a faculty end, by the other author's institution: faculty
                     of our IITs / same IIT, not faculty (students, staff) / other Indian / foreign / unknown
Outputs (results/): authorship_structure.csv, leiden_comparison.csv, rich_club.csv, robustness.csv, sir_outbreaks.csv,
  spreader_ranking.csv, top_spreaders.csv, network_growth.csv, centrality_vs_impact.csv, coauthor_tie_types.csv,
  top_collaborators_all_coauthors.csv
Figures: faculty_communities.png, robustness.png, sir_spreading.png, network_growth.png, clustering_richclub.png
usage: python stats_authorship_dynamics.py   (needs: pip install python-igraph leidenalg)"""
import os, random, collections as C
import numpy as np
import networkx as nx
import igraph as ig
import leidenalg as la
from scipy.stats import spearmanr, rankdata
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from common import INSTS, YEARS, DATA, RES, read_csv, write_csv, style, save, COLOR, TEXT2, MUTED, GRID, plt
from stats_authorship import faculty_graph

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OWN = {"IIT Kharagpur", "IIT Roorkee", "Indian Institute of Technology Kharagpur", "Indian Institute of Technology Roorkee"}
T_RANK = 0.2


def giant_share(H, n):
    return max((len(c) for c in nx.connected_components(H)), default=0) / n


def attack(G, order_fn, steps, per):
    """Largest-component share after removing `per` nodes per step, re-ranking with order_fn after every step."""
    H, n, out = G.copy(), G.number_of_nodes(), []
    for _ in range(steps + 1):
        out.append(giant_share(H, n))
        H.remove_nodes_from(order_fn(H)[:per])
    return out


def partial_rho(x, y, z):
    x, y, z = (rankdata(a) for a in (x, y, z))
    rx = x - np.polyval(np.polyfit(z, x, 1), z)
    ry = y - np.polyval(np.polyfit(z, y, 1), z)
    return np.corrcoef(rx, ry)[0, 1]


def main():
    style()
    G, info = faculty_graph()
    nodes = list(G)
    n, m = G.number_of_nodes(), G.number_of_edges()
    cent = {r["roster_id"]: r for r in read_csv(os.path.join(RES, "faculty_centrality.csv"))}
    fac = {r["roster_id"]: r for r in read_csv(os.path.join(RES, "faculty.csv"))}
    com = {v: int(cent[v]["community"]) for v in nodes}
    bc = {v: float(cent[v]["betweenness"]) for v in nodes}
    deg = dict(G.degree())
    summary = []

    # ------------------------------------------------ communities vs departments
    dept = [info[v]["institution"] + " | " + info[v]["department"] for v in nodes]
    dept_of = dict(zip(nodes, dept))
    tied = [i for i, v in enumerate(nodes) if deg[v] > 0]
    summary += [("NMI(Louvain communities, departments)", normalized_mutual_info_score(dept, [com[v] for v in nodes])),
                ("NMI, faculty with >= 1 faculty tie", normalized_mutual_info_score([dept[i] for i in tied], [com[nodes[i]] for i in tied])),
                ("ARI(Louvain communities, departments)", adjusted_rand_score(dept, [com[v] for v in nodes])),
                ("share of ties inside one department", np.mean([dept_of[a] == dept_of[b] for a, b in G.edges])),
                ("department assortativity", nx.attribute_assortativity_coefficient(G, "department")),
                ("institute assortativity", nx.attribute_assortativity_coefficient(G, "institution"))]

    # ------------------------------------------------ Leiden vs Louvain, resolution sweep
    idx = {v: i for i, v in enumerate(nodes)}
    g = ig.Graph(n=n, edges=[(idx[a], idx[b]) for a, b in G.edges])
    g.es["weight"] = [G[a][b]["weight"] for a, b in G.edges]
    base = [com[v] for v in nodes]
    lrows = []
    for res in (0.25, 0.5, 1.0, 2.0, 4.0):
        p = la.find_partition(g, la.RBConfigurationVertexPartition, weights="weight", resolution_parameter=res, seed=42)
        if res == 1.0:                                # the reported partition (Louvain's tie-breaking varies across networkx versions)
            groups = C.defaultdict(set)
            for v in nodes:
                groups[com[v]].add(v)
            lv = list(groups.values())
        else:
            lv = nx.community.louvain_communities(G, weight="weight", seed=42, resolution=res)
        lab_of = {v: i for i, c in enumerate(lv) for v in c}
        lv_lab = [lab_of[v] for v in nodes]
        for algo, lab, comms in (("Louvain", lv_lab, lv), ("Leiden", p.membership, [set(nodes[i] for i in c) for c in p])):
            lrows.append({"algorithm": algo, "resolution": res, "communities": len(comms),
                          "communities_size_ge_5": sum(1 for c in comms if len(c) >= 5),
                          "largest": max(len(c) for c in comms),
                          "modularity_Q_at_resolution_1": round(g.modularity(lab, weights="weight"), 4),
                          "ari_vs_louvain_resolution_1": round(adjusted_rand_score(base, lab), 3),
                          "disconnected_communities": sum(1 for c in comms if len(c) > 1 and not nx.is_connected(G.subgraph(c)))})
    write_csv("leiden_comparison.csv", lrows)

    # ------------------------------------------------ hierarchy: k-core, C(k), rich club
    core = nx.core_number(G)
    kmax = max(core.values())
    summary += [("maximum k-core", kmax), ("faculty in the maximum k-core", sum(1 for v in nodes if core[v] == kmax))]
    clus = nx.clustering(G)
    byk = C.defaultdict(list)
    for v in nodes:
        if deg[v] >= 2:
            byk[deg[v]].append(clus[v])
    ks = np.array(sorted(byk))
    ck = np.array([np.mean(byk[k]) for k in ks])
    ok = ck > 0
    beta = -np.polyfit(np.log(ks[ok]), np.log(ck[ok]), 1)[0]
    summary.append(("clustering spectrum exponent beta, C(k) ~ k^-beta", beta))
    simple = nx.Graph(G.edges())
    phi = nx.rich_club_coefficient(simple, normalized=False)
    rand_phi = C.defaultdict(list)
    for s in range(10):
        R = simple.copy()
        nx.double_edge_swap(R, nswap=10 * m, max_tries=200 * m, seed=s)
        for k, v in nx.rich_club_coefficient(R, normalized=False).items():
            rand_phi[k].append(v)
    rrows = [{"k": k, "faculty_with_degree_gt_k": sum(1 for v in nodes if deg[v] > k), "phi": round(phi[k], 4),
              "phi_rewired_mean": round(np.mean(rand_phi[k]), 4),
              "rho_normalised": round(phi[k] / np.mean(rand_phi[k]), 3) if np.mean(rand_phi[k]) > 0 else ""}
             for k in sorted(phi) if sum(1 for v in nodes if deg[v] > k) >= 10]
    write_csv("rich_club.csv", rrows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.scatter(ks, ck, s=[10 + 3 * len(byk[k]) ** 0.5 for k in ks], color="#2a78d6", edgecolors="#fcfcfb", linewidths=1, zorder=3)
    ax.plot(ks, np.exp(np.polyval(np.polyfit(np.log(ks[ok]), np.log(ck[ok]), 1), np.log(ks))), color=TEXT2, linewidth=1.2,
            label=f"C(k) ~ k^-{beta:.2f}")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([2, 5, 10, 20, 40], ["2", "5", "10", "20", "40"]); ax.set_xticks([], minor=True)
    ax.set_yticks([0.05, 0.1, 0.2, 0.4], ["0.05", "0.1", "0.2", "0.4"]); ax.set_yticks([], minor=True)
    ax.set_xlabel("k = faculty co-authors"); ax.set_ylabel("mean clustering C(k)")
    ax.set_title("Clustering falls with degree: hierarchical groups", fontsize=10)
    ax.legend()
    ax = axes[1]
    rk = [r for r in rrows if r["rho_normalised"] != ""]
    ax.plot([r["k"] for r in rk], [r["rho_normalised"] for r in rk], color="#2a78d6", marker="o", markersize=3)
    ax.axhline(1, color=TEXT2, linewidth=0.8)
    ax.text(rk[0]["k"], 1.04, "no rich club", fontsize=8, color=TEXT2)
    ax.set_xlabel("k"); ax.set_ylabel("phi(k) / phi_rewired(k)")
    ax.set_title("Rich club: highly connected faculty link to each other", fontsize=10)
    fig.tight_layout()
    save(fig, "clustering_richclub.png")

    # ------------------------------------------------ small world, centrality vs impact
    nm = {r["metric"]: r for r in read_csv(os.path.join(RES, "null_model_comparison.csv"))}
    c_r, l_r = (float(nm[k]["ER G(n,m) mean"]) for k in ("avg_clustering", "mean_shortest_path_giant"))
    c, l = (float(nm[k]["faculty network"]) for k in ("avg_clustering", "mean_shortest_path_giant"))
    summary.append(("small-world sigma = (C/C_ER) / (L/L_ER)", (c / c_r) / (l / l_r)))
    vs = [v for v in nodes if v in fac]
    papers = [float(fac[v]["papers"]) for v in vs]
    irows = []
    for metric in ("h_index", "citations", "papers"):
        y = [float(fac[v][metric]) for v in vs]
        for cname, x in (("degree", [deg[v] for v in vs]), ("betweenness", [bc[v] for v in vs])):
            irows.append({"centrality": cname, "impact": metric, "spearman_rho": round(spearmanr(x, y).statistic, 3),
                          "partial_rho_given_papers": round(partial_rho(x, y, papers), 3) if metric != "papers" else "", "faculty": len(vs)})
    write_csv("centrality_vs_impact.csv", irows)

    # ------------------------------------------------ robustness
    steps, per = 40, max(1, n // 80)                  # remove up to 50 % of faculty, 1.25 % per step
    rnd = [attack(G, lambda H, s=s: random.Random(s).sample(list(H), H.number_of_nodes()), steps, per) for s in range(20)]
    curves = {"random": list(np.mean(rnd, axis=0)),
              "degree (adaptive)": attack(G, lambda H: sorted(H, key=lambda v: -H.degree(v)), steps, per),
              "betweenness (adaptive)": attack(G, lambda H: sorted((b := nx.betweenness_centrality(H)), key=lambda v: -b[v]), steps, per)}
    frac = [i * per / n for i in range(steps + 1)]
    write_csv("robustness.csv", [{"fraction_removed": round(f, 4), **{k: round(v[i], 4) for k, v in curves.items()}} for i, f in enumerate(frac)])
    for k, v in curves.items():
        f50 = next((f for f, s in zip(frac, v) if s <= v[0] / 2), None)
        summary.append((f"f_50, {k}: share removed until the largest component halves", f50 if f50 is not None else "> 0.5"))
    k1, k2 = np.mean(list(deg.values())), np.mean([d * d for d in deg.values()])
    summary += [("Molloy-Reed kappa = <k^2>/<k>", k2 / k1), ("mean-field random-failure threshold 1 - 1/(kappa-1)", 1 - 1 / (k2 / k1 - 1))]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for (k, v), col, ls in zip(curves.items(), (MUTED, "#2a78d6", "#eb6834"), ((0, (3, 3)), "-", "-")):
        ax.plot([100 * f for f in frac], [100 * s for s in v], color=col, linestyle=ls, label=k)
    b = curves["betweenness (adaptive)"]
    drop = max(range(1, len(b)), key=lambda i: b[i - 1] - b[i])
    ax.annotate(f"the two campuses separate\n({drop * per} bridging faculty removed)", (100 * frac[drop], 100 * b[drop]),
                xytext=(14, -6), textcoords="offset points", fontsize=8, color=TEXT2, arrowprops=dict(arrowstyle="-", color=TEXT2, lw=0.8))
    ax.set_xlabel("% of faculty removed"); ax.set_ylabel("% of faculty in the largest component")
    ax.set_title("Robustness: losing the hubs splits the network fast")
    ax.legend()
    save(fig, "robustness.png")

    # ------------------------------------------------ SIR spreading = bond percolation
    edges = list(G.edges())
    k_c = k1 / (k2 - k1)
    rng = np.random.default_rng(0)

    def outbreaks(T, R):
        tot = np.zeros(n)
        for _ in range(R):
            H = nx.Graph()
            H.add_nodes_from(nodes)
            H.add_edges_from(e for e, u in zip(edges, rng.random(len(edges))) if u < T)
            for comp in nx.connected_components(H):
                for v in comp:
                    tot[idx[v]] += len(comp)
        return tot / R

    srows = []
    for T in (0.02, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.7, 1.0):
        o = outbreaks(T, 300)
        srows.append({"T": T, "mean_outbreak_share": round(o.mean() / n, 4), "largest_outbreak_share": round(o.max() / n, 4)})
    write_csv("sir_outbreaks.csv", srows)
    o = outbreaks(T_RANK, 1000)
    measures = {"k-core": core, "degree": deg, "strength (joint papers)": dict(G.degree(weight="weight")), "betweenness": bc}
    top_o = set(sorted(nodes, key=lambda v: -o[idx[v]])[:n // 20])
    write_csv("spreader_ranking.csv", [{"centrality": k, "spearman_rho_with_outbreak": round(spearmanr([d[v] for v in nodes], o).statistic, 3),
                                        "top5pct_overlap_with_best_spreaders": round(len(set(sorted(nodes, key=lambda v: -d[v])[:n // 20]) & top_o) / (n // 20), 3)}
                                       for k, d in measures.items()])
    write_csv("top_spreaders.csv", [{"faculty": info[v]["name"], "institution": info[v]["institution"], "department": info[v]["department"],
                                     "expected_outbreak_share": round(o[idx[v]] / n, 4), "degree": deg[v], "k_core": core[v],
                                     "betweenness": round(bc[v], 5)} for v in sorted(nodes, key=lambda v: -o[idx[v]])[:20]])
    summary.append(("mean-field epidemic threshold T_c = <k>/(<k^2>-<k>)", k_c))
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.plot([r["T"] for r in srows], [100 * r["mean_outbreak_share"] for r in srows], color="#2a78d6", marker="o", markersize=4, label="mean outbreak")
    ax.plot([r["T"] for r in srows], [100 * r["largest_outbreak_share"] for r in srows], color="#eb6834", marker="o", markersize=4, label="from the best spreader")
    ax.axvline(k_c, color=TEXT2, linewidth=0.8, linestyle=(0, (3, 3)))
    ax.text(k_c, 72, f" mean-field T_c = {k_c:.2f}", fontsize=8, color=TEXT2)
    ax.set_xlabel("T = transmission probability per co-author tie"); ax.set_ylabel("% of faculty reached")
    ax.set_title("SIR spreading on the faculty network", fontsize=10)
    ax.legend(loc="center right")
    ax = axes[1]
    for name in INSTS.values():
        vv = [v for v in nodes if info[v]["institution"] == name]
        ax.scatter([core[v] + random.Random(v).uniform(-0.25, 0.25) for v in vv], [100 * o[idx[v]] / n for v in vv], s=10,
                   color=COLOR[name], alpha=0.6, linewidths=0, label=name)
    ax.set_xlabel("k-core of the starting faculty member (jittered)"); ax.set_ylabel(f"expected % reached (T = {T_RANK})")
    ax.set_title("Who spreads best: the k-core predicts it", fontsize=10)
    ax.legend(loc="upper left")
    fig.tight_layout()
    save(fig, "sir_spreading.png")

    # ------------------------------------------------ growth
    grows = []
    for Y in YEARS:
        H = nx.Graph([(a, b) for a, b, d in G.edges(data=True) if d["first_year"] and d["first_year"] <= Y])
        N, E = H.number_of_nodes(), H.number_of_edges()
        grows.append({"year": Y, "faculty_with_a_tie": N, "ties": E, "mean_degree": round(2 * E / N, 3),
                      "largest_component": max(len(c) for c in nx.connected_components(H)), "largest_component_share": round(giant_share(H, N), 4),
                      "transitivity": round(nx.transitivity(H), 4),
                      "kharagpur_roorkee_ties": sum(1 for a, b in H.edges if info[a]["institution"] != info[b]["institution"])})
    write_csv("network_growth.csv", grows)
    a_dens = np.polyfit(np.log([r["faculty_with_a_tie"] for r in grows]), np.log([r["ties"] for r in grows]), 1)[0]
    summary.append(("densification exponent a, ties ~ faculty^a", a_dens))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, key, scale, title in ((axes[0], "largest_component_share", 100, "Largest component, % of faculty with a tie"),
                                  (axes[1], "mean_degree", 1, "Mean number of faculty co-authors")):
        ax.plot(YEARS, [scale * r[key] for r in grows], color="#2a78d6", marker="o", markersize=4)
        ax.set_xlabel("end of year (cumulative ties)")
        ax.set_ylim(0, 100 if scale == 100 else None)
        ax.set_title(title, fontsize=10)
    axes[1].set_ylim(bottom=0)
    ax = axes[2]
    xs, ys = [r["faculty_with_a_tie"] for r in grows], [r["ties"] for r in grows]
    ax.loglog(xs, ys, color="#2a78d6", marker="o", markersize=4, linestyle="none")
    ax.loglog(xs, np.exp(np.polyval(np.polyfit(np.log(xs), np.log(ys), 1), np.log(xs))), color=TEXT2, linewidth=1.2, label=f"ties ~ faculty^{a_dens:.2f}")
    for r in (grows[0], grows[-1]):
        ax.annotate(str(r["year"]), (r["faculty_with_a_tie"], r["ties"]), xytext=(5, -10), textcoords="offset points", fontsize=8, color=TEXT2)
    ax.set_xlabel("faculty with a tie (N)"); ax.set_ylabel("ties (E)")
    ax.set_title("Densification: ties grow faster than people", fontsize=10)
    ax.legend()
    fig.tight_layout()
    save(fig, "network_growth.png")

    # ------------------------------------------------ tie types and all co-authors
    indian = {r["partner_inst"] for r in read_csv(os.path.join(DATA, "indian_connections.csv"))}
    types, coauthors = C.Counter(), C.defaultdict(set)
    for e in read_csv(os.path.join(DATA, "authorship_network.csv")):
        for me, mine, other in (("author_a_id", "a_is_faculty", "author_b_id"), ("author_b_id", "b_is_faculty", "author_a_id")):
            if e[mine] == "TRUE" and e[me] in info:
                coauthors[e[me]].add(e[other])
        if e["a_is_faculty"] == "TRUE" and e["b_is_faculty"] == "TRUE":
            types["faculty of our two IITs"] += 1
            continue
        other = [x for x in (e["inst_b"] if e["a_is_faculty"] == "TRUE" else e["inst_a"]).split(";") if x]
        types["unknown institution" if not other else "same IIT, not faculty (students, staff)" if OWN & set(other)
              else "other Indian institution" if indian & set(other) else "foreign institution"] += 1
    tot = sum(types.values())
    write_csv("coauthor_tie_types.csv", [{"tie_type": k, "pair_paper_rows": v, "share": round(v / tot, 4)} for k, v in types.most_common()])
    tops = []
    for name in INSTS.values():
        vv = sorted((v for v in coauthors if info[v]["institution"] == name), key=lambda v: -len(coauthors[v]))[:10]
        tops += [{"institution": name, "faculty": info[v]["name"], "department": info[v]["department"], "distinct_coauthors": len(coauthors[v]),
                  "faculty_coauthors": deg.get(v, 0)} for v in vv]
    write_csv("top_collaborators_all_coauthors.csv", tops)
    summary.append(("median distinct co-authors per faculty (everyone, not only faculty)", np.median([len(s) for s in coauthors.values()])))

    # ------------------------------------------------ community map (brief 6b: visualise collaboration clusters)
    giant = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    pos = nx.spring_layout(giant, seed=3, k=0.6 / np.sqrt(giant.number_of_nodes()), iterations=80, weight=None)
    comrows = {int(r["community"]): r for r in read_csv(os.path.join(RES, "communities.csv"))}
    top_c = [c for c, _ in C.Counter(com[v] for v in giant).most_common(len(CATEGORICAL))]
    fig, ax = plt.subplots(figsize=(9.5, 9))
    nx.draw_networkx_edges(giant, pos, ax=ax, edge_color=GRID, width=0.4, alpha=0.7)
    rest = [v for v in giant if com[v] not in top_c]
    nx.draw_networkx_nodes(giant, pos, nodelist=rest, ax=ax, node_size=[5 + 2 * giant.degree(v) for v in rest], node_color="#c9c8c3",
                           linewidths=0, label="other communities")
    for c, col in zip(top_c, CATEGORICAL):
        vv = [v for v in giant if com[v] == c]
        r = comrows.get(c, {})
        lab = f"{c}: {r.get('top_department', '')} ({'KGP' if int(r.get('IIT Kharagpur', 0)) >= int(r.get('IIT Roorkee', 0)) else 'Roorkee'}, {len(vv)})"
        nx.draw_networkx_nodes(giant, pos, nodelist=vv, ax=ax, node_size=[6 + 2.5 * giant.degree(v) for v in vv], node_color=col,
                               linewidths=0.4, edgecolors="#fcfcfb", label=lab)
        cx, cy = np.mean([pos[v] for v in vv], axis=0)
        ax.text(cx, cy, str(c), fontsize=11, fontweight="bold", color=TEXT2, ha="center", va="center",
                bbox=dict(boxstyle="circle,pad=0.2", fc="#fcfcfb", ec=col, lw=1.5))
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=2, fontsize=8,
                    title="Louvain community: largest department (campus, faculty in this component)", title_fontsize=8)
    for h in leg.legend_handles:
        h.set_sizes([40])
    ax.set_axis_off()
    ax.set_title("Collaboration clusters: the 8 largest Louvain communities of the largest component")
    save(fig, "faculty_communities.png")

    rows = [{"metric": k, "value": round(v, 4) if isinstance(v, float) else v} for k, v in summary]
    write_csv("authorship_structure.csv", rows)
    for r in rows + lrows + irows:
        print(r)


if __name__ == "__main__":
    main()

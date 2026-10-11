"""Build data.js for the static dashboard (index.html) from the computed statistics.
Reads Analysis/results/*.csv (small) and, for the two network panels and paper titles, Enrichment/out/
(citation_network.csv, authorship_network.csv, group3_data.csv). Graph layouts are precomputed here with networkx so
the browser only draws. Output: data.js (window.DASH = {...}), loaded by index.html. No network access, no API key.
usage: python Dashboard/site/build_data.py   (re-run after Analysis/scripts/run_all.sh)"""
import os, csv, json, math, collections as C
import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RES = os.path.join(REPO, "Analysis", "results")
OUT = os.path.join(REPO, "Enrichment", "out")
csv.field_size_limit(10 ** 8)
INSTS = ["IIT Kharagpur", "IIT Roorkee"]
N_HUBS = 30                     # citation-network panel: top papers by PageRank, drawn with every paper citing them


def rd(name, folder=RES):
    with open(os.path.join(folder, name), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(x, f=float):
    try:
        return f(x)
    except (TypeError, ValueError):
        return None


def by_inst(rows, key="institution"):
    d = C.defaultdict(list)
    for r in rows:
        d[r[key]].append(r)
    return d


def packed_layout(G, aspect=1.25, gap=0.12):
    """Lay out each connected component on its own (spring layout scaled to its size), then pack the components in
    rows, largest first. A single spring layout pushes disconnected clusters far apart and shrinks each one."""
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    radius = lambda c: 0.09 * math.sqrt(len(c))          # component radius grows with its size
    area = sum((2 * radius(c) + gap) ** 2 for c in comps)
    width = max(2 * radius(comps[0]) + gap, math.sqrt(area * aspect) * 1.08)   # rows as wide as the panel's shape
    pos, x, y, row_h = {}, 0.0, 0.0, 0.0
    for comp in comps:
        H = G.subgraph(comp)
        r = radius(comp)
        p = nx.spring_layout(H, seed=3, iterations=200) if len(comp) > 1 else {next(iter(comp)): (0.0, 0.0)}
        xs, ys = [v[0] for v in p.values()], [v[1] for v in p.values()]
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
        if x > 0 and x + 2 * r > width:                    # next row
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        for v, (a, b) in p.items():
            pos[v] = (x + r + (a - cx) / span * 2 * r, -(y + r + (b - cy) / span * 2 * r))
        x += 2 * r + gap
        row_h = max(row_h, 2 * r)
    return pos


def main():
    D = {"generated": "October 2026", "insts": INSTS}

    # ---------------- overview numbers
    trend = by_inst(rd("trend.csv"))
    quart = {r["institution"]: r for r in rd("quartiles.csv")}
    core = {r["institution"]: r for r in rd("core_ranks.csv")}
    fac = rd("faculty.csv")
    cent = {r["roster_id"]: r for r in rd("faculty_centrality.csv")}
    flow = {r["institution"]: r for r in rd("citation_flow_summary.csv")}
    kpi = {}
    for i in INSTS:
        hs = sorted(int(r["h_index"]) for r in fac if r["institution"] == i)
        kpi[i] = {"papers": sum(int(r["total"]) for r in trend[i]),
                  "faculty": len(hs), "median_h": hs[len(hs) // 2], "max_h": hs[-1],
                  "q1_share": float(quart[i]["q1_fraction_of_ranked"]),
                  "journal_papers": int(quart[i]["journal_papers"]),
                  "in_flow": int(flow[i]["in_flow"]), "out_flow": int(flow[i]["out_flow"]),
                  "impact_ratio": float(flow[i]["impact_ratio_in_over_out"]),
                  "first_year_papers": int(trend[i][0]["total"]), "last_full_year_papers": int(trend[i][-2]["total"])}
    D["kpi"] = kpi

    # ---------------- output & quality
    types = ["journal", "conference", "book-chapter", "preprint", "other"]
    D["years"] = [int(r["year"]) for r in trend[INSTS[0]]]
    D["trend"] = {i: {"total": [int(r["total"]) for r in trend[i]], **{t: [int(r[t]) for r in trend[i]] for t in types}}
                  for i in INSTS}
    D["quartiles"] = {i: {k: int(quart[i][k]) for k in ("Q1", "Q2", "Q3", "Q4", "not_in_scimago")} for i in INSTS}
    D["core"] = {i: {k: int(core[i][k]) for k in ("A*", "A", "B", "C", "not_core_ranked", "conference_papers")} for i in INSTS}
    D["top_journals"] = {i: [{"journal": r["journal"], "papers": int(r["papers"]), "q": r["most_common_quartile"]}
                             for r in rows] for i, rows in by_inst(rd("top_journals.csv")).items()}
    areas = by_inst(rd("research_areas.csv"))
    D["areas"] = {i: [{"field": r["field"], "share": float(r["share"]), "papers": int(r["papers"])} for r in areas[i]] for i in INSTS}

    # ---------------- people
    D["faculty"] = []
    for r in fac:
        c = cent.get(r["roster_id"], {})
        D["faculty"].append({"id": r["roster_id"], "name": r["faculty"], "inst": r["institution"], "dept": r["department"],
                             "papers": int(r["papers"]), "cites": int(r["citations"]), "h": int(r["h_index"]),
                             "q1": int(r["q1_papers"]), "journal": r["top_journal"], "from": int(r["first_year"]),
                             "to": int(r["last_year"]), "coauthors": num(c.get("faculty_coauthors"), int),
                             "betw": num(c.get("betweenness")), "community": num(c.get("community"), int)})
    D["departments"] = [{"inst": r["institution"], "dept": r["department"], "faculty": int(r["faculty_with_papers"]),
                         "papers": int(r["papers"]), "cites": int(r["citations"]),
                         "q1": num(r["q1_fraction_of_ranked"]), "median_h": float(r["median_h_index"]), "max_h": int(r["max_h_index"])}
                        for r in rd("departments.csv")]

    # ---------------- papers
    D["most_cited"] = {s: [{"title": r["title"], "journal": r["journal"], "year": int(r["year"]), "cites": int(r["citations"]),
                            "doi": r["doi"], "insts": r["institutions"]} for r in rows]
                       for s, rows in by_inst(rd("most_cited.csv"), "scope").items()}
    # slide 12: most-cited Indian papers that cite each institute (Analysis/scripts/stats_citing_top.py)
    if os.path.exists(os.path.join(RES, "top_citing_papers.csv")):     # online step; the panel hides until it has run
        D["top_citing"] = {s: [{"title": r["title"], "journal": r["journal"], "year": int(r["year"]) if r["year"] else None,
                                "cites": int(r["citations"]), "doi": r["doi"], "insts": r["citing_institutions"],
                                "n": int(r["papers_cited"])} for r in rows]
                           for s, rows in by_inst(rd("top_citing_papers.csv"), "scope").items()}
    D["pagerank_top"] = {s: [{"title": r["title"], "journal": r["journal"], "year": int(r["year"]), "pr": float(r["pagerank"]),
                              "indeg": int(r["in_degree"]), "indeg_rank": int(r["in_degree_rank"]), "doi": r["doi"]}
                             for r in rows] for s, rows in by_inst(rd("pagerank_top10.csv"), "scope").items()}
    D["netsum"] = {r["scope"]: {k: r[k] for k in r if k != "scope"} for r in rd("citation_network_summary.csv")}
    D["indegree"] = {s: [[int(r["in_degree"]), int(r["papers"])] for r in rows]
                     for s, rows in by_inst(rd("indegree_distribution.csv"), "scope").items()}

    # ---------------- citation flow
    D["flow_yearly"] = {i: {"in": [int(r["in_flow"]) for r in rows], "out": [int(r["out_flow"]) for r in rows]}
                        for i, rows in by_inst(rd("citation_flow_yearly.csv")).items()}
    fp = by_inst(rd("citation_flow_partners.csv"))
    D["top_citers"] = {i: [{"partner": r["partner"], "cites": int(r["citations_from_partner"]),
                            "out": int(r["citations_to_partner"])} for r in fp[i][:10]] for i in INSTS}

    # ---------------- collaboration
    D["auth_summary"] = {r["metric"]: r["value"] for r in rd("authorship_summary.csv")}
    D["null_models"] = [{k: r[k] for k in r} for r in rd("null_model_comparison.csv")]
    D["communities"] = [{"id": int(r["community"]), "size": int(r["faculty"]), "kgp": int(r["IIT Kharagpur"]),
                         "rkg": int(r["IIT Roorkee"]), "dept": r["top_department"], "dept_share": float(r["top_department_share"]),
                         "hub": r["most_connected_member"]} for r in rd("communities.csv")]
    D["bridging"] = [{"inst": r["institution"], "name": r["faculty"], "dept": r["department"],
                      "partners": int(r["indian_partner_institutions"])} for r in rd("bridging_faculty.csv")]

    # ---------------- partners
    part = by_inst(rd("partners.csv"))
    D["partners"] = {i: [{"partner": r["partner"], "shared": int(r["shared_papers"]), "cluster": r["cluster"],
                          "cross": r["cross_cluster"] == "True", "jaccard": num(r["jaccard_top20"]),
                          "cites_in": int(r["citations_from_partner"]), "cites_out": int(r["citations_to_partner"])}
                         for r in part[i][:15]] for i in INSTS}
    D["clusters"] = [{"inst": r["institution"], "cluster": r["cluster"], "cross": r["cross_cluster"] == "True",
                      "partners": int(r["partners"]), "shared": int(r["shared_papers"])} for r in rd("cluster_summary.csv")]
    D["jaccard"] = [{"inst": r["institution"], "partner": r["partner"], "shared": int(r["shared_papers"]),
                     "j": float(r["jaccard_top20"]), "cluster": r["cluster"]} for r in rd("jaccard_topics.csv")]

    # ---------------- citation network panel: the most influential papers (PageRank) and the papers citing them
    pm = {r["node"]: r for r in rd("paper_citation_metrics.csv")}
    titles = {}
    for r in rd("group3_data.csv", OUT):
        for k in (r["openalex_id"], (r["doi"] or "").lower()):
            if k and k not in titles:
                titles[k] = (r["title"], r["journal_name"])
    full = nx.DiGraph()
    for e in rd("citation_network.csv", OUT):
        if e["edge_type"] != "internal":
            continue
        s = e["source_openalex"] or e["source_doi"].lower()
        t = e["target_openalex"] or e["target_doi"].lower()
        if s in pm and t in pm and s != t:
            full.add_edge(s, t)
    hubs = sorted((n for n in pm if n in full), key=lambda n: -float(pm[n]["pagerank_cluster"]))[:N_HUBS]
    keep = set(hubs)
    for h in hubs:
        keep |= set(full.predecessors(h))                    # papers in our corpus that cite a hub
    G = full.subgraph(keep).copy()
    top = {n: pm[n] for n in G}
    D["citation_graph_hubs"] = hubs
    pos = packed_layout(G.to_undirected())
    nodes = []
    for n, r in top.items():
        t = titles.get(n) or titles.get((r["doi"] or "").lower()) or ("(title unavailable)", "")
        nodes.append({"id": n, "x": round(pos[n][0] * 1000, 1), "y": round(pos[n][1] * 1000, 1), "title": t[0], "journal": t[1],
                      "year": int(r["year"]), "insts": r["institutions"], "pr": float(r["pagerank_cluster"]),
                      "indeg": int(r["in_degree_cluster"]), "cites": num(r["global_citations"], int), "doi": r["doi"]})
    D["citation_graph"] = {"nodes": nodes, "edges": [[s, t] for s, t in G.edges]}

    # ---------------- faculty co-authorship network (faculty with >= 1 faculty co-author)
    w = C.Counter()
    for e in rd("authorship_network.csv", OUT):
        if e["a_is_faculty"] == "TRUE" and e["b_is_faculty"] == "TRUE":
            a, b = sorted((e["author_a_id"], e["author_b_id"]))
            w[(a, b, e["paper_doi"] or e["year"])] += 1
    pairs = C.Counter((a, b) for a, b, _ in w)
    F = nx.Graph()
    for (a, b), k in pairs.items():
        if a in cent and b in cent:
            F.add_edge(a, b, weight=k)
    pos = nx.spring_layout(F, seed=3, k=1.1 / math.sqrt(F.number_of_nodes()), iterations=250, weight=None)
    hidx = {r["roster_id"]: int(r["h_index"]) for r in fac}
    D["faculty_graph"] = {
        "nodes": [{"id": v, "x": round(pos[v][0] * 1000, 1), "y": round(pos[v][1] * 1000, 1), "name": cent[v]["faculty"],
                   "inst": cent[v]["institution"], "dept": cent[v]["department"], "deg": F.degree(v),
                   "community": int(cent[v]["community"]), "betw": float(cent[v]["betweenness"]), "h": hidx.get(v, 0)}
                  for v in F],
        "edges": [[a, b, d["weight"], cent[a]["institution"] != cent[b]["institution"]] for a, b, d in F.edges(data=True)]}

    js = "window.DASH = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n"
    open(os.path.join(HERE, "data.js"), "w", encoding="utf8").write(js)
    print(f"data.js {len(js) / 1e6:.2f} MB | citation graph {G.number_of_nodes()} nodes / {G.number_of_edges()} edges | "
          f"faculty graph {F.number_of_nodes()} nodes / {F.number_of_edges()} edges")


if __name__ == "__main__":
    main()

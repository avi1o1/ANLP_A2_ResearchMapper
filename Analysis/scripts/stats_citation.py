"""Citation network statistics (brief sections 6a and 7a).
Network analysed = the 'internal' edges of citation_network.csv: citations between analysis-set papers of IIT Kharagpur
and IIT Roorkee (our cluster). Every analysis-set paper is a node, so uncited / non-citing papers are included.
  in-degree   per institute: citations received from papers of the SAME institute's corpus (brief: "within your
              institution's corpus"); cluster: from either institute
  PageRank    damping 0.85 (networkx), on the cluster graph and on each institute's own subgraph
Citation flow uses every cross-institute edge: external Indian edges (OpenAlex) plus internal edges between the two
IITs (a Roorkee paper citing a Kharagpur paper is Indian in-flow for Kharagpur).
  in-flow     citation edges from works of another Indian institution to the institute's papers
  out-flow    citation edges from the institute's papers to works of another Indian institution
  impact ratio = in-flow / out-flow
  An edge whose other side lists several Indian institutions counts once for each of them in per-partner tables and
  once in the institute totals.
Outputs (results/): citation_network_summary.csv, pagerank_top10.csv, paper_citation_metrics.csv,
  indegree_distribution.csv, citation_flow_summary.csv, citation_flow_partners.csv, citation_flow_yearly.csv
Figures: indegree_ccdf.png, citation_flow_yearly.png, top_citing_institutes.png
usage: python stats_citation.py"""
import os, collections as C
import numpy as np
import networkx as nx
from scipy.stats import spearmanr
from common import (INSTS, YEARS, DATA, load_records, cites, read_csv, write_csv, style, save, COLOR, TEXT2, MUTED, plt, short_name)

OA_NAME = {"IIT Kharagpur": "Indian Institute of Technology Kharagpur", "IIT Roorkee": "Indian Institute of Technology Roorkee"}


def node_of(oa, doi):
    return oa or (doi or "").lower()


def main():
    style()
    meta = {}
    for inst, name in INSTS.items():
        for r in load_records(inst):
            k = node_of(r.get("openalex_id"), r["doi"] if not str(r["doi"]).startswith("TODO") else "")
            m = meta.setdefault(k, {"insts": set(), "title": r["title"], "year": r["year"], "doi": r["doi"],
                                    "venue": r["venue"], "citations": cites(r)})
            m["insts"].add(name)
    edges = read_csv(os.path.join(DATA, "citation_network.csv"))
    G = nx.DiGraph()
    G.add_nodes_from(meta)
    for e in edges:
        if e["edge_type"] == "internal":
            s, t = node_of(e["source_openalex"], e["source_doi"]), node_of(e["target_openalex"], e["target_doi"])
            if s in meta and t in meta and s != t:
                G.add_edge(s, t)

    # ------------------------------------------------ network metrics
    summ, prow, mrows, drows = [], [], {}, []
    scopes = {"Cluster (both IITs)": G}
    for name in INSTS.values():
        scopes[name] = G.subgraph([n for n in G if name in meta[n]["insts"]]).copy()
    pr_all = {}
    for scope, H in scopes.items():
        pr = nx.pagerank(H, alpha=0.85)
        pr_all[scope] = pr
        indeg = dict(H.in_degree())
        wcc = max(nx.weakly_connected_components(H), key=len) if H.number_of_nodes() else set()
        yrs = [meta[n]["year"] for n in H]
        rho = spearmanr([pr[n] for n in H], yrs).statistic
        summ.append({"scope": scope, "papers": H.number_of_nodes(), "citation_edges": H.number_of_edges(),
                     "mean_in_degree": round(H.number_of_edges() / H.number_of_nodes(), 3),
                     "papers_cited_at_least_once": sum(1 for v in indeg.values() if v > 0),
                     "papers_citing_none_in_corpus": sum(1 for n in H if H.out_degree(n) == 0),
                     "largest_weak_component": len(wcc), "density": f"{nx.density(H):.2e}",
                     "reciprocal_pairs": sum(1 for u, v in H.edges if H.has_edge(v, u)) // 2,
                     "spearman_pagerank_vs_year": round(rho, 3)})
        for k, c in sorted(C.Counter(indeg.values()).items()):
            drows.append({"scope": scope, "in_degree": k, "papers": c})
        for rank, n in enumerate(sorted(H, key=lambda n: -pr[n])[:10], 1):
            m = meta[n]
            prow.append({"scope": scope, "rank": rank, "pagerank": f"{pr[n]:.6f}", "in_degree": indeg[n],
                         "in_degree_rank": 1 + sum(1 for v in indeg.values() if v > indeg[n]), "year": m["year"],
                         "title": m["title"], "journal": m["venue"], "doi": m["doi"],
                         "global_citations": m["citations"], "institutions": ";".join(sorted(m["insts"]))})
    for n in G:
        m = meta[n]
        row = {"node": n, "doi": m["doi"], "year": m["year"], "institutions": ";".join(sorted(m["insts"])),
               "global_citations": m["citations"], "in_degree_cluster": G.in_degree(n),
               "pagerank_cluster": f"{pr_all['Cluster (both IITs)'][n]:.8f}"}
        for name in INSTS.values():
            H = scopes[name]
            row["in_degree_" + name.split()[-1].lower()] = H.in_degree(n) if n in H else ""
        mrows[n] = row
    write_csv("citation_network_summary.csv", summ)
    write_csv("pagerank_top10.csv", prow)
    write_csv("paper_citation_metrics.csv", list(mrows.values()))
    write_csv("indegree_distribution.csv", drows)
    fig, ax = plt.subplots(figsize=(6.5, 4.3))
    for name in INSTS.values():
        deg = np.array([d for _, d in scopes[name].in_degree()])
        ks = np.arange(1, deg.max() + 1)
        ccdf = [(deg >= k).mean() for k in ks]
        ax.loglog(ks, ccdf, color=COLOR[name], label=name, marker="o", markersize=3, linewidth=1.5)
    ax.set_xlabel("in-degree k (citations from the same institute's papers)")
    ax.set_ylabel("P(in-degree >= k)")
    ax.set_title("In-degree distribution (CCDF, log-log)")
    ax.legend()
    save(fig, "indegree_ccdf.png")

    # ------------------------------------------------ citation flow
    inflow, outflow = C.Counter(), C.Counter()                    # (inst, partner) -> edges
    tot_in, tot_out = C.Counter(), C.Counter()
    yr_in, yr_out = C.Counter(), C.Counter()                      # (inst, year)
    for e in edges:
        si = [x for x in e["source_inst"].split(";") if x]
        ti = [x for x in e["target_inst"].split(";") if x]
        y = int(e["year"]) if e["year"] else None
        if e["edge_type"] == "internal":
            if e["cross_inst"] != "TRUE":
                continue
            for t in ti:                          # e.g. Roorkee paper -> Kharagpur paper
                partners = [OA_NAME[s] for s in si if s != t]
                if partners and t not in si:
                    tot_in[t] += 1; yr_in[(t, y)] += 1
                    for p in partners:
                        inflow[(t, p)] += 1
            for s in si:
                partners = [OA_NAME[t] for t in ti if t != s]
                if partners and s not in ti:
                    tot_out[s] += 1; yr_out[(s, y)] += 1
                    for p in partners:
                        outflow[(s, p)] += 1
        elif e["edge_type"] == "in_from_indian":
            for t in ti:
                tot_in[t] += 1; yr_in[(t, y)] += 1
                for p in si:
                    inflow[(t, p)] += 1
        elif e["edge_type"] == "out_to_indian":
            for s in si:
                tot_out[s] += 1; yr_out[(s, y)] += 1
                for p in ti:
                    outflow[(s, p)] += 1
    fsum = [{"institution": n, "in_flow": tot_in[n], "out_flow": tot_out[n],
             "impact_ratio_in_over_out": round(tot_in[n] / tot_out[n], 3) if tot_out[n] else ""} for n in INSTS.values()]
    write_csv("citation_flow_summary.csv", fsum)
    prow2 = []
    for n in INSTS.values():
        partners = {p for (i, p) in list(inflow) + list(outflow) if i == n}
        rows = [{"institution": n, "partner": p, "citations_from_partner": inflow[(n, p)], "citations_to_partner": outflow[(n, p)],
                 "impact_ratio_in_over_out": round(inflow[(n, p)] / outflow[(n, p)], 3) if outflow[(n, p)] else ""}
                for p in partners]
        rows.sort(key=lambda x: -x["citations_from_partner"])
        for rank, r in enumerate(rows, 1):
            r["rank_by_in_flow"] = rank
        prow2 += rows
    write_csv("citation_flow_partners.csv", prow2,
              ["institution", "rank_by_in_flow", "partner", "citations_from_partner", "citations_to_partner", "impact_ratio_in_over_out"])
    yrows = [{"institution": n, "year": y, "in_flow": yr_in[(n, y)], "out_flow": yr_out[(n, y)]} for n in INSTS.values() for y in YEARS]
    write_csv("citation_flow_yearly.csv", yrows)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
    for ax, (key, label) in zip(axes, [("in_flow", "In-flow: Indian works citing our papers"),
                                       ("out_flow", "Out-flow: our papers citing Indian works")]):
        for n in INSTS.values():
            ys = [r[key] for r in yrows if r["institution"] == n]
            ax.plot(YEARS[:-1], ys[:-1], color=COLOR[n], marker="o", markersize=3, label=n)
            ax.plot(YEARS[-2:], ys[-2:], color=COLOR[n], linestyle=(0, (3, 3)))
        ax.set_title(label, fontsize=10)
        ax.set_xticks(YEARS[::2])
        ax.set_xlabel("year of the citing paper (2026 partial)")
    axes[0].set_ylabel("citation edges")
    axes[0].legend(loc="upper left")
    fig.suptitle("Citation flow with other Indian institutions, 2016-2026", x=0.01, y=1.04, ha="left", fontweight="bold", fontsize=12)
    save(fig, "citation_flow_yearly.png")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for ax, n in zip(axes, INSTS.values()):
        top = [r for r in prow2 if r["institution"] == n][:10]
        ax.barh(range(len(top)), [r["citations_from_partner"] for r in top], color=COLOR[n], height=0.6)
        ax.set_yticks(range(len(top)), [short_name(r["partner"]) for r in top], fontsize=8)
        ax.invert_yaxis()
        ax.grid(axis="y", visible=False)
        for i, r in enumerate(top):
            ax.text(r["citations_from_partner"], i, f" {r['citations_from_partner']:,}", va="center", fontsize=8, color=TEXT2)
        ax.set_title(f"Citing {n}", fontsize=10)
        ax.set_xlabel("citation edges to the institute's papers")
        ax.margins(x=0.15)
    fig.suptitle("Top 10 Indian institutions citing each institute", x=0.01, y=1.03, ha="left", fontweight="bold", fontsize=12)
    fig.tight_layout()
    save(fig, "top_citing_institutes.png")

    for s in summ:
        print(s)
    for f in fsum:
        print(f)


if __name__ == "__main__":
    main()

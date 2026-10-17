"""Citation network beyond the brief: self-citation, PageRank corrections, distribution fits, preferential attachment.
Same graph as stats_citation.py (internal edges between analysis-set papers of both IITs).
  self-citation      an internal edge whose citing and cited paper share an author (same OpenAlex author id, or the
                     same faculty member by roster id). The brief's in-degree "within your institution's corpus" is
                     mostly this, so every ranking below is also given on the network without self-citations.
  PageRank variants  'all'        PageRank (0.85) on every internal edge (= stats_citation.py)
                     'no self'    PageRank on the edges that are not self-citations
                     'age-rescaled'  z-score of the 'no self' PageRank among papers of the same publication year
                                  (Mariani, Medo & Zhang 2016, with the year as the age window); 2026 papers are left
                                  out of this ranking (partial year, too few citations to rescale)
  age bias           Mariani et al.'s test: share of each publication year's papers that reach the overall top 1 %
                     (2016-2025 papers); an unbiased ranking gives ~1 % for every year. CV = SD / mean of the shares.
  distribution fits  Clauset-Shalizi-Newman (python 'powerlaw'): x_min by KS distance, then log-likelihood ratios of
                     the power law against lognormal, exponential and truncated power law (normalised R, p). R < 0 with
                     p < 0.05 = the alternative fits better; p >= 0.05 = the data cannot tell them apart.
  preferential       for each year T in 2017-2025 and each of our papers published before T: k = citations it had
  attachment         received up to T-1, new = citations received in year T (internal edges + citations from other
                     Indian works, the citations we can date). A(k) = mean new citations per paper with k
                     (Jeong, Neda & Barabasi 2003). Fit A(k) = c (k + k0)^alpha on k with >= 50 paper-years:
                     alpha = 1 is linear preferential attachment, k0 the initial attractiveness.
  field mixing       share of citation edges between papers of the same OpenAlex field; field assortativity
Outputs (results/): self_citation_summary.csv, self_citation_yearly.csv, self_citation_outliers.csv,
  pagerank_variants_top10.csv, pagerank_variant_agreement.csv, pagerank_age_bias.csv, distribution_fits.csv,
  preferential_attachment.csv, citation_field_mixing.csv, citation_dynamics_summary.csv
Figures: self_citation_yearly.png, pagerank_age_bias.png, citation_distribution_fit.png, preferential_attachment.png
usage: python stats_citation_dynamics.py   (needs: pip install powerlaw)"""
import collections as C
import warnings
import numpy as np
import networkx as nx
import powerlaw
from scipy.optimize import curve_fit
from scipy.stats import spearmanr
from common import INSTS, YEARS, PARTIAL_YEAR, write_csv, style, save, COLOR, TEXT2, MUTED, plt
from stats_citation import citation_graph, node_of

warnings.filterwarnings("ignore", module="powerlaw")
CLUSTER = "Cluster (both IITs)"


def main():
    style()
    G, meta, edges = citation_graph()
    is_self = {(u, v): bool(meta[u]["authors"] & meta[v]["authors"] or meta[u]["faculty"] & meta[v]["faculty"]) for u, v in G.edges}
    H = nx.DiGraph()
    H.add_nodes_from(G)
    H.add_edges_from(e for e, s in is_self.items() if not s)

    # ------------------------------------------------ self-citation
    srows, yrows = [], []
    scopes = {CLUSTER: lambda n: True, **{name: (lambda n, name=name: name in meta[n]["insts"]) for name in INSTS.values()}}
    for scope, keep in scopes.items():
        es = [e for e in G.edges if keep(e[0]) and keep(e[1])]
        ns = sum(is_self[e] for e in es)
        srows.append({"scope": scope, "citation_edges": len(es), "self_citations": ns, "self_share": round(ns / len(es), 4),
                      "non_self_edges": len(es) - ns,
                      "papers_cited_at_least_once": len({v for _, v in es}),
                      "papers_cited_at_least_once_non_self": len({e[1] for e in es if not is_self[e]})})
        for y in YEARS:
            ey = [e for e in es if meta[e[0]]["year"] == y]
            yrows.append({"scope": scope, "year": y, "citation_edges": len(ey),
                          "self_share": round(sum(is_self[e] for e in ey) / len(ey), 4) if ey else ""})
    write_csv("self_citation_summary.csv", srows)
    write_csv("self_citation_yearly.csv", yrows)
    # papers that look influential inside the corpus but nobody else cites
    out = [n for n in G if meta[n]["citations"] == 0 and G.in_degree(n) >= 5]
    write_csv("self_citation_outliers.csv", sorted(
        [{"year": meta[n]["year"], "title": meta[n]["title"], "journal": meta[n]["venue"], "doi": meta[n]["doi"],
          "institutions": ";".join(sorted(meta[n]["insts"])), "internal_in_degree": G.in_degree(n),
          "self_citations": sum(is_self[(u, n)] for u in G.predecessors(n)), "global_citations": 0} for n in out],
        key=lambda r: -r["internal_in_degree"]))

    fig, ax = plt.subplots(figsize=(6.5, 4))
    for name in INSTS.values():
        rs = [r for r in yrows if r["scope"] == name and r["self_share"] != ""]
        ax.plot([r["year"] for r in rs], [100 * r["self_share"] for r in rs], color=COLOR[name], marker="o", markersize=4, label=name)
    ax.set_ylim(70, 100)
    ax.set_ylabel("% of internal citations that are self-citations")
    ax.set_xlabel("year of the citing paper (2026 partial)")
    ax.set_title("Most citations inside an institute come from the same authors")
    ax.legend(loc="lower left")
    save(fig, "self_citation_yearly.png")

    # ------------------------------------------------ PageRank variants
    pr_all, pr_ns = nx.pagerank(G, alpha=0.85), nx.pagerank(H, alpha=0.85)
    by_year = C.defaultdict(list)
    for n in H:
        by_year[meta[n]["year"]].append(pr_ns[n])
    mu = {y: (np.mean(v), np.std(v)) for y, v in by_year.items()}
    rescaled = {n: (pr_ns[n] - mu[meta[n]["year"]][0]) / mu[meta[n]["year"]][1] for n in H if meta[n]["year"] != PARTIAL_YEAR}
    variants = {"PageRank (all citations)": pr_all, "PageRank (no self-citations)": pr_ns, "age-rescaled PageRank (no self-citations)": rescaled}
    indeg, indeg_ns = dict(G.in_degree()), dict(H.in_degree())
    trows, arows, brows = [], [], []
    known = [n for n in G if meta[n]["citations"] is not None]
    full_years = [n for n in G if meta[n]["year"] != PARTIAL_YEAR]
    per_year = C.Counter(meta[n]["year"] for n in full_years)
    top100 = {}
    for name, sc in {"internal in-degree": indeg, **variants}.items():
        # ranking bias (Mariani et al. 2016): each year's share of the top 1 % should be ~1 % of its papers
        top = sorted(full_years, key=lambda n: -sc[n])[:len(full_years) // 100]
        tc = C.Counter(meta[n]["year"] for n in top)
        shares = [100 * tc[y] / per_year[y] for y in sorted(per_year)]
        brows.append({"ranking": name, **{str(y): round(s, 2) for y, s in zip(sorted(per_year), shares)},
                      "cv_of_shares": round(np.std(shares) / np.mean(shares), 3)})
    write_csv("pagerank_age_bias.csv", brows)
    cv = {r["ranking"]: r["cv_of_shares"] for r in brows}
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ys = sorted(per_year)
    for r, col, ls in ((brows[1], MUTED, (0, (3, 3))), (brows[2], "#eb6834", "-"), (brows[3], "#2a78d6", "-")):
        ax.plot(ys, [r[str(y)] for y in ys], color=col, linestyle=ls, marker="o", markersize=4,
                label=f"{r['ranking']} (CV {r['cv_of_shares']:.2f})")
    ax.axhline(1, color=TEXT2, linewidth=0.8, label="unbiased ranking: 1 % of every year")
    ax.set_xlabel("publication year")
    ax.set_ylabel("% of the year's papers in the overall top 1 %")
    ax.set_title("PageRank favours old papers; rescaling by age removes it")
    ax.legend(loc="upper right", fontsize=8)
    save(fig, "pagerank_age_bias.png")
    for name, sc in variants.items():
        ranked = sorted(sc, key=lambda n: -sc[n])
        top100[name] = set(ranked[:100])
        for rank, n in enumerate(ranked[:10], 1):
            m = meta[n]
            trows.append({"variant": name, "rank": rank, "score": f"{sc[n]:.6g}", "year": m["year"], "title": m["title"],
                          "journal": m["venue"], "doi": m["doi"], "institutions": ";".join(sorted(m["insts"])),
                          "internal_in_degree": indeg[n], "non_self_in_degree": indeg_ns[n], "global_citations": m["citations"]})
        ns = [n for n in known if n in sc]
        arows.append({"variant": name, "papers_ranked": len(sc), "age_bias_cv_top1pct": cv[name],
                      "spearman_vs_global_citations": round(spearmanr([sc[n] for n in ns], [meta[n]["citations"] for n in ns]).statistic, 3),
                      "top100_median_global_citations": float(np.median([meta[n]["citations"] or 0 for n in top100[name]])),
                      "top100_share_from_2016_2017": round(sum(meta[n]["year"] <= 2017 for n in top100[name]) / 100, 2),
                      "top100_overlap_with_all": len(top100[name] & top100["PageRank (all citations)"])})
    write_csv("pagerank_variants_top10.csv", trows)
    write_csv("pagerank_variant_agreement.csv", arows)

    # ------------------------------------------------ distribution fits
    data = {"internal in-degree (all)": [d for d in indeg.values() if d > 0],
            "internal in-degree (no self-citations)": [d for d in indeg_ns.values() if d > 0],
            "global citations": [meta[n]["citations"] for n in known if meta[n]["citations"] > 0]}
    frows, fits = [], {}
    for name, xs in data.items():
        f = powerlaw.Fit(xs, discrete=True, verbose=False)
        fits[name] = f
        row = {"quantity": name, "papers_with_value_ge_1": len(xs), "max": max(xs), "alpha": round(f.power_law.alpha, 3),
               "alpha_sigma": round(f.power_law.sigma, 3), "x_min": int(f.power_law.xmin),
               "papers_in_tail": sum(1 for x in xs if x >= f.power_law.xmin)}
        verdict = []
        for alt in ("lognormal", "exponential", "truncated_power_law"):
            R, p = f.distribution_compare("power_law", alt, normalized_ratio=True)
            row[f"R_vs_{alt}"], row[f"p_vs_{alt}"] = round(R, 2), round(p, 4)
            verdict.append(f"{alt} better" if R < 0 and p < 0.05 else f"power law better than {alt}" if R > 0 and p < 0.05
                           else f"not distinguishable from {alt}")
        row["verdict"] = "; ".join(verdict)
        frows.append(row)
    write_csv("distribution_fits.csv", frows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, name in zip(axes, ("internal in-degree (all)", "global citations")):
        f = fits[name]
        f.plot_ccdf(ax=ax, color="#2a78d6", linewidth=2, label="data (tail, x >= x_min)")
        f.power_law.plot_ccdf(ax=ax, color=MUTED, linestyle=(0, (4, 3)), linewidth=1.5, label=f"power law, alpha = {f.power_law.alpha:.2f}")
        f.lognormal.plot_ccdf(ax=ax, color="#eb6834", linestyle=(0, (1, 2)), linewidth=2, label="lognormal")
        ax.set_xlabel("in-degree k" if "in-degree" in name else "citations c (collection date)")
        ax.set_ylabel("P(X >= x | x >= x_min)")
        ax.set_title(f"{name.capitalize()}: x_min = {int(f.power_law.xmin)}", fontsize=10)
        ax.legend(loc="lower left", fontsize=8)
    fig.suptitle("Heavy tails: power law or lognormal? (maximum-likelihood fits)", x=0.01, y=1.03, ha="left", fontweight="bold", fontsize=12)
    fig.tight_layout()
    save(fig, "citation_distribution_fit.png")

    # ------------------------------------------------ preferential attachment
    dated = C.defaultdict(list)                                    # our paper -> years of the citations it received
    for e in edges:
        if e["edge_type"] in ("internal", "in_from_indian") and e["year"]:
            t = node_of(e["target_openalex"], e["target_doi"])
            if t in meta:
                dated[t].append(int(e["year"]))
    num, den = C.Counter(), C.Counter()
    for T in range(2017, PARTIAL_YEAR):
        for n, m in meta.items():
            if m["year"] < T:
                ys = dated.get(n, [])
                k = sum(1 for y in ys if y < T)
                num[k] += sum(1 for y in ys if y == T)
                den[k] += 1
    ks = [k for k in sorted(den) if den[k] >= 50]
    write_csv("preferential_attachment.csv", [{"k_citations_before_year": k, "paper_years": den[k], "new_citations": num[k],
                                               "attachment_rate_A_k": round(num[k] / den[k], 4)} for k in ks])
    kk = np.array(ks, float)
    ak = np.array([num[k] / den[k] for k in ks])
    (c, k0, alpha), cov = curve_fit(lambda k, c, k0, a: c * (k + k0) ** a, kk, ak, p0=(0.2, 3, 1), sigma=1 / np.sqrt([den[k] for k in ks]))
    se = np.sqrt(np.diag(cov))
    slope = np.polyfit(np.log(kk[kk >= 1]), np.log(ak[kk >= 1]), 1)[0]
    pa_rows = [("fit A(k) = c (k + k0)^alpha: alpha", round(alpha, 3)), ("alpha standard error", round(se[2], 3)),
               ("k0 (initial attractiveness)", round(k0, 2)), ("c", round(c, 4)),
               ("naive log-log slope for k >= 1 (no k0)", round(slope, 3)), ("largest k with >= 50 paper-years", ks[-1])]

    fig, ax = plt.subplots(figsize=(6.5, 4.3))
    ax.scatter(kk + 1, ak, s=[8 + 2 * np.log1p(den[k]) ** 2 for k in ks], color="#2a78d6", edgecolors="#fcfcfb", linewidths=1, zorder=3,
               label="measured A(k) (size = paper-years)")
    xs = np.linspace(0, kk.max(), 200)
    ax.plot(xs + 1, c * (xs + k0) ** alpha, color=TEXT2, linewidth=1.5, label=f"fit c (k + {k0:.1f})^{alpha:.2f}")
    ax.plot(xs + 1, ak[1] * (xs + k0) / (1 + k0), color=MUTED, linestyle=(0, (3, 3)), linewidth=1.2, label="linear (alpha = 1), same k0")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("k + 1 (citations received before year T, + 1)")
    ax.set_ylabel("A(k): new citations in year T")
    ax.set_title("Preferential attachment: cited papers attract more citations")
    ax.legend(loc="upper left", fontsize=8)
    save(fig, "preferential_attachment.png")

    # ------------------------------------------------ field mixing
    fe = [(meta[u]["field"], meta[v]["field"], is_self[(u, v)]) for u, v in G.edges if meta[u]["field"] and meta[v]["field"]]
    papers_f = C.Counter(meta[n]["field"] for n in G if meta[n]["field"])
    tot = sum(papers_f.values())
    mrows = []
    for f, cnt in papers_f.most_common():
        out_f = [b for a, b, _ in fe if a == f]
        if len(out_f) < 100:
            continue
        others = C.Counter(b for b in out_f if b != f)
        mrows.append({"field": f, "papers": cnt, "citations_given": len(out_f),
                      "share_to_same_field": round(sum(b == f for b in out_f) / len(out_f), 3),
                      "expected_share_if_random": round(cnt / tot, 3),
                      "most_cited_other_field": others.most_common(1)[0][0] if others else ""})
    write_csv("citation_field_mixing.csv", mrows)
    Gf = nx.DiGraph()
    Gf.add_nodes_from((n, {"field": meta[n]["field"]}) for n in G if meta[n]["field"])
    Gf.add_edges_from((u, v) for u, v in G.edges if u in Gf and v in Gf)
    Hf = Gf.edge_subgraph([e for e in Gf.edges if not is_self[e]])
    same = lambda es: round(np.mean([a == b for a, b, *_ in es]), 4)
    pa_rows += [("field assortativity (all edges)", round(nx.attribute_assortativity_coefficient(Gf, "field"), 3)),
                ("field assortativity (no self-citations)", round(nx.attribute_assortativity_coefficient(Hf, "field"), 3)),
                ("same-field share (all edges)", same(fe)), ("same-field share (no self-citations)", same([x for x in fe if not x[2]]))]
    write_csv("citation_dynamics_summary.csv", [{"metric": k, "value": v} for k, v in pa_rows])

    for r in srows + arows + frows:
        print(r)
    for k, v in pa_rows:
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

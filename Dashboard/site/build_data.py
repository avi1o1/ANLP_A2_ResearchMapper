"""Build data.js for the static dashboard (index.html) from the computed statistics.
Reads Analysis/results/*.csv (small) and, for the two network panels and paper titles, Enrichment/out/
(citation_network.csv, authorship_network.csv, group3_data.csv). Graph layouts are precomputed here with networkx so
the browser only draws. Output: data.js (window.DASH = {...}), loaded by index.html. No network access, no API key.
usage: python Dashboard/site/build_data.py   (re-run after Analysis/scripts/run_all.sh)"""
import os, re, csv, json, math, urllib.parse, collections as C
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


ROSTERS = os.path.join(REPO, "WebScrape", "rosters")
SUPPLEMENT = os.path.join(REPO, "Enrichment", "cache")
LINK_STATUS = os.path.join(HERE, "link_status.json")   # optional, written by check_links.py
ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


def clean_url(u):
    """http(s) URL with spaces and other unsafe characters percent-encoded; anything else -> None."""
    u = (u or "").strip()
    if not re.match(r"https?://[\w-]+(\.[\w-]+)+(/|$|:|\?)", u, re.I):   # rejects "http://Nil", "To be updated", ...
        return None
    u = u.replace("://www.facweb.iitkgp.ac.in", "://facweb.iitkgp.ac.in")   # dead www. alias of KGP's faculty web server
    return urllib.parse.quote(u, safe=":/?&=#%+@,;~!$'()*[]")


def faculty_links(drop_dead=True):
    """roster_id -> {profile, scholar, home, dblp, scopus, irins, orcid: [...]}, taken only from what the institute
    pages list (WebScrape/rosters) plus the ORCID-verified additions (Enrichment/cache/roster_supplement_*.json).
    Nothing is searched for or guessed. Links that check_links.py found dead (404/410/no such host) are dropped."""
    dead = set()
    if drop_dead and os.path.exists(LINK_STATUS):
        with open(LINK_STATUS, encoding="utf-8") as fh:
            dead = {u for u, s in json.load(fh).items() if s in (404, 410, "dns")}
    links = {}
    for inst in ("iit_kharagpur", "iit_roorkee"):
        for k, r in enumerate(rd(f"{inst}_faculty.csv", ROSTERS)):
            L = {"profile": clean_url(r["profile_url"]), "scholar": clean_url(r["google_scholar"]),
                 "home": clean_url(r["homepage"]), "dblp": clean_url(r["dblp"]), "irins": clean_url(r["irins"]),
                 "scopus": f"https://www.scopus.com/authid/detail.uri?authorId={r['scopus_id'].strip()}"
                           if r["scopus_id"].strip().isdigit() else None,
                 "orcid": ORCID_RE.findall(r["orcid"] or "")}
            links[f"{inst}:{k}"] = L
        sfn = os.path.join(SUPPLEMENT, f"roster_supplement_{inst}.json")
        if os.path.exists(sfn):
            with open(sfn, encoding="utf-8") as fh:
                for s in json.load(fh):
                    rid = s["roster_id"] if s.get("kind") == "alt_orcid" else f"{inst}:orcid:{s['orcid']}"
                    L = links.setdefault(rid, {"orcid": []})
                    if s["orcid"] not in L["orcid"]:
                        L["orcid"].append(s["orcid"])
    for L in links.values():
        L["orcid"] = [f"https://orcid.org/{o}" for o in L["orcid"]]
        for k in list(L):
            if not L[k] or (isinstance(L[k], str) and L[k] in dead):
                del L[k]
    return links


def main():
    D = {"generated": "October 2026", "insts": INSTS}

    # ---------------- overview numbers
    trend = by_inst(rd("trend.csv"))
    quart = {r["institution"]: r for r in rd("quartiles.csv")}
    core = {r["institution"]: r for r in rd("core_ranks.csv")}
    fac = rd("faculty.csv")
    cent = {r["roster_id"]: r for r in rd("faculty_centrality.csv")}
    flow = {r["institution"]: r for r in rd("citation_flow_summary.csv")}
    hsum = rd("h_index_summary.csv")
    hchk = {r["institution"]: r for r in rd("h_index_check_summary.csv")}
    hyr = by_inst(rd("h_index_by_year.csv"))
    D["h_summary"] = {i: {r["metric"]: {k: num(r[k]) for k in ("n", "mean", "sd", "q1", "median", "q3", "p90", "max")}
                          for r in hsum if r["institution"] == i and r["department"] == "All departments"} for i in INSTS}
    D["h_check"] = {i: {k: num(v) for k, v in hchk[i].items() if k != "institution"} for i in INSTS}
    D["h_by_year"] = {i: {k: [num(r[k]) for r in hyr[i]] for k in ("mean_h", "median_h", "p90_h", "institute_h_index")}
                      for i in INSTS}
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
    D["top_journals"] = {i: [{"journal": r["journal"], "papers": int(r["papers"]), "q": r["most_common_quartile"],
                              "if": num(r["if_openalex"])} for r in rows] for i, rows in by_inst(rd("top_journals.csv")).items()}
    imp = by_inst(rd("important_journals.csv"))
    ys = [str(y) for y in range(2016, 2027)]
    D["important"] = {i: [{"group": r["group"], "total": int(r["total"]), "years": [int(r[y]) for y in ys]} for r in imp[i]]
                      for i in INSTS}
    ipp = C.defaultdict(list)
    for r in rd("important_journal_papers.csv"):
        if len([x for x in ipp[(r["institution"], r["group"])]]) < 6:
            ipp[(r["institution"], r["group"])].append({"title": r["title"], "journal": r["journal"], "year": int(r["year"]),
                                                        "cites": num(r["citations"], int), "doi": r["doi"], "faculty": r["faculty"]})
    D["important_papers"] = {f"{i}|{g}": v for (i, g), v in ipp.items()}
    ifr = rd("impact_factor.csv")
    D["impact"] = {i: {"all": next({k: r[k] for k in r} for r in ifr if r["institution"] == i and r["scope"] == "all years" and not r["department"]),
                       "over5": [float(r["share_if_over_5"] or 0) for y in ys for r in ifr if r["institution"] == i and r["scope"] == y and not r["department"]],
                       "over10": [float(r["share_if_over_10"] or 0) for y in ys for r in ifr if r["institution"] == i and r["scope"] == y and not r["department"]]}
                   for i in INSTS}
    lc = rd("large_collaborations.csv")
    D["large"] = {i: next({k: r[k] for k in r} for r in lc if r["institution"] == i and r["scope"] == "all years") for i in INSTS}
    cs = rd("core_summary.csv")
    D["core_years"] = {i: {k: [int(r[k]) for y in ys for r in cs if r["institution"] == i and r["scope"] == y and not r["department"]]
                           for k in ("A*", "A", "B", "C")} for i in INSTS}
    D["core_venues"] = {i: [{"conf": r["conference"], "rank": r["core_rank"], "papers": int(r["papers"])} for r in rows]
                        for i, rows in by_inst(rd("core_top_venues.csv")).items()}
    sub = rd("research_subfields.csv")
    D["subfields"] = {i: {} for i in INSTS}
    for r in sub:
        L = D["subfields"][r["institution"]].setdefault(r["field"], [])
        if len(L) < 8:
            L.append({"sub": r["subfield"], "papers": int(r["papers"]), "share": float(r["share_of_field"])})
    env = rd("env_science_breakdown.csv")
    D["env"] = {i: {b: [{"name": r["name"], "papers": int(r["papers"]), "share": float(r["share_of_env_papers"])}
                        for r in env if r["institution"] == i and r["by"] == b][:6] for b in ("subfield", "department", "topic")}
                for i in INSTS}
    areas = by_inst(rd("research_areas.csv"))
    D["areas"] = {i: [{"field": r["field"], "share": float(r["share"]), "papers": int(r["papers"])} for r in areas[i]] for i in INSTS}

    # ---------------- people
    D["faculty"] = []
    links = faculty_links()
    for r in fac:
        c = cent.get(r["roster_id"], {})
        D["faculty"].append({"id": r["roster_id"], "name": r["faculty"], "inst": r["institution"], "dept": r["department"],
                             "papers": int(r["papers"]), "cites": int(r["citations"]), "h": int(r["h_index"]),
                             "q1": int(r["q1_papers"]), "i10": int(r["i10_index"]), "oa_h": num(r["oa_h_index_all_career"], int),
                             "journal": r["top_journal"], "from": int(r["first_year"]),
                             "to": int(r["last_year"]), "coauthors": num(c.get("faculty_coauthors"), int),
                             "betw": num(c.get("betweenness")), "community": num(c.get("community"), int),
                             "links": links.get(r["roster_id"], {})})
    have = C.Counter(k for f in D["faculty"] for k in f["links"])
    print("faculty links:", dict(have), "| none:", sum(1 for f in D["faculty"] if not f["links"]))
    D["departments"] = [{"inst": r["institution"], "dept": r["department"], "faculty": int(r["faculty_with_papers"]),
                         "papers": int(r["papers"]), "cites": int(r["citations"]),
                         "q1": num(r["q1_fraction_of_ranked"]), "median_h": float(r["median_h_index"]), "max_h": int(r["max_h_index"]),
                         "mean_h": num(r["mean_h_index"]), "sd_h": num(r["sd_h_index"])}
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

    # ---------------- papers with more than 10 authors (stats_journals.py, stats_large_collab.py)
    lc = {r["institution"]: r for r in rd("large_collaborations.csv") if r["scope"] == "all years"}
    by = lambda name: by_inst(rd(name))
    venue = by("large_by_venue.csv")
    D["teams"] = {i: {
        "papers": int(lc[i]["more_than_10_authors"]), "share": float(lc[i]["share"]), "cite_share": float(lc[i]["share_of_all_citations"]),
        "n100": int(lc[i]["with_100_or_more"]),
        "sens": [{"m": r["metric"], "all": num(r["all_papers"]), "wo": num(r["without_large"]), "pct": num(r["change_pct"])} for r in by("large_sensitivity.csv")[i]],
        "prem": {"years": [int(r["year"]) for r in by("large_premium.csv")[i] if r["year"].isdigit()],
                 "ratio": [float(r["ratio"]) for r in by("large_premium.csv")[i] if r["year"].isdigit()],
                 "overall": next(float(r["ratio"]) for r in by("large_premium.csv")[i] if not r["year"].isdigit())},
        "dept": [{"name": r["department"], "n": int(r["large_papers"]), "share": float(r["share_of_institute_large"]),
                  "of_dept": float(r["share_of_department"])} for r in by("large_by_department.csv")[i][:8]],
        "field": [{"name": r["field"], "n": int(r["large_papers"]), "share": float(r["share_of_large"])} for r in by("large_by_field.csv")[i][:6]],
        "venues": [{"name": r["label"], "n": int(r["large_papers"]), "rank": r["rank"]} for r in venue[i] if r["kind"] == "venue"][:6],
        "profile": {f'{r["kind"]}|{r["label"]}': [num(r["share_large"]), num(r["share_other"])] for r in venue[i] if r["kind"] != "venue"},
        "bands": [{"band": r["authors"], "n": int(r["papers"]), "median": num(r["median_citations"])} for r in by("large_size_bands.csv")[i]],
        "faculty": [{"name": r["faculty"], "dept": r["department"], "n": int(r["large_papers"]), "h": int(r["h_index"]),
                     "h_wo": int(r["h_without_large"])} for r in by("large_faculty_impact.csv")[i][:10]]} for i in INSTS}

    # ---------------- beyond the brief: self-citation, corrected PageRank, dynamics (stats_*_dynamics.py)
    kv = lambda name: {r["metric"]: r["value"] if num(r["value"]) is None else num(r["value"]) for r in rd(name)}
    D["selfcite"] = {r["scope"]: {"share": float(r["self_share"]), "edges": int(r["citation_edges"]), "non_self": int(r["non_self_edges"])}
                     for r in rd("self_citation_summary.csv")}
    sy = C.defaultdict(list)
    for r in rd("self_citation_yearly.csv"):
        sy[r["scope"]].append(num(r["self_share"]))
    D["selfcite_yearly"] = dict(sy)
    D["pr_variants"] = C.defaultdict(list)
    for r in rd("pagerank_variants_top10.csv"):
        D["pr_variants"][r["variant"]].append({"title": r["title"], "year": int(r["year"]), "doi": r["doi"], "insts": r["institutions"],
                                               "indeg": int(r["internal_in_degree"]), "nonself": int(r["non_self_in_degree"]),
                                               "cites": num(r["global_citations"], int)})
    D["pr_agree"] = {r["variant"]: {"cv": float(r["age_bias_cv_top1pct"]), "overlap": int(r["top100_overlap_with_all"])}
                     for r in rd("pagerank_variant_agreement.csv")}
    D["age_bias"] = [{"ranking": r["ranking"], "cv": float(r["cv_of_shares"]), "shares": [float(r[str(y)]) for y in range(2016, 2026)]}
                     for r in rd("pagerank_age_bias.csv")]
    pa = rd("preferential_attachment.csv")
    D["pa"] = {"k": [int(r["k_citations_before_year"]) for r in pa], "A": [float(r["attachment_rate_A_k"]) for r in pa],
               "n": [int(r["paper_years"]) for r in pa], **kv("citation_dynamics_summary.csv")}
    D["fits"] = [{k: r[k] for k in ("quantity", "alpha", "x_min", "papers_in_tail", "R_vs_lognormal", "p_vs_lognormal", "verdict")}
                 for r in rd("distribution_fits.csv")]
    D["structure"] = kv("authorship_structure.csv")
    D["leiden"] = [{k: num(v) if k != "algorithm" else v for k, v in r.items()} for r in rd("leiden_comparison.csv")]
    D["growth"] = [{k: num(v) for k, v in r.items()} for r in rd("network_growth.csv")]
    D["robust"] = [{k: num(v) for k, v in r.items()} for r in rd("robustness.csv")]
    D["sir"] = [{k: num(v) for k, v in r.items()} for r in rd("sir_outbreaks.csv")]
    D["spreader_rank"] = [{"c": r["centrality"], "rho": float(r["spearman_rho_with_outbreak"]), "top": float(r["top5pct_overlap_with_best_spreaders"])}
                          for r in rd("spreader_ranking.csv")]
    D["top_spreaders"] = [{"name": r["faculty"], "inst": r["institution"], "dept": r["department"], "share": float(r["expected_outbreak_share"]),
                           "deg": int(r["degree"]), "core": int(r["k_core"])} for r in rd("top_spreaders.csv")[:10]]
    D["cent_impact"] = [{k: num(v) if k not in ("centrality", "impact") else v for k, v in r.items()} for r in rd("centrality_vs_impact.csv")]
    D["tie_types"] = [{"type": r["tie_type"], "n": int(r["pair_paper_rows"]), "share": float(r["share"])} for r in rd("coauthor_tie_types.csv")]

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
    titles, nauth = {}, {}
    rid = {(r["institution"], r["faculty"], r["department"]): r["roster_id"] for r in fac}
    plist, pidx, fpapers = [], {}, C.defaultdict(list)       # per-faculty paper lists -> papers.js (loaded on demand)
    venues, types = {}, {}                                  # stored once; papers refer to them by index
    for r in rd("group3_data.csv", OUT):
        for k in (r["openalex_id"], (r["doi"] or "").lower()):
            if k and k not in titles:
                titles[k] = (r["title"], r["journal_name"])
        if r["doi"]:
            nauth[r["doi"].lower()] = num(r["n_authors"], int)
        key = (r["doi"] or "").lower() or r["record_id"]
        if key not in pidx:
            pidx[key] = len(plist)
            plist.append([r["title"], num(r["year"], int), venues.setdefault(r["journal_name"], len(venues)),
                          num(r["citations"], int), (r["doi"] or "").replace("https://doi.org/", ""),
                          num(r["n_authors"], int), types.setdefault(r["type"], len(types))])
        f = rid.get((r["institution"], r["author"], r["department"]))
        if f and pidx[key] not in fpapers[f]:
            fpapers[f].append(pidx[key])
    for rows in D["most_cited"].values():
        for p in rows:
            p["na"] = nauth.get((p["doi"] or "").lower())
    for f in fpapers:
        fpapers[f].sort(key=lambda k: -(plist[k][3] or 0))
    pjs = "window.PAPERS = " + json.dumps({"p": plist, "f": fpapers, "v": list(venues), "t": list(types)}, ensure_ascii=False, separators=(",", ":")) + ";\n"
    open(os.path.join(HERE, "papers.js"), "w", encoding="utf8").write(pjs)
    print(f"papers.js {len(pjs) / 1e6:.2f} MB, {len(plist)} papers, {len(fpapers)} faculty")
    yfn = os.path.join(RES, "faculty_by_year.csv")
    if os.path.exists(yfn):
        D["fac_years"] = {i: {"listed": [int(r["faculty_listed"]) for r in rows], "snaps": [int(r["snapshots_used"]) for r in rows]}
                          for i, rows in by_inst(rd("faculty_by_year.csv")).items()}
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

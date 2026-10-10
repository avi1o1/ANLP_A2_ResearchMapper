"""Connectivity map (brief section 7b): partner institutions, co-authorship strength, cross-cluster links, and
Jaccard similarity of research topics.
Partners and counts come from out/indian_connections.csv and results/citation_flow_partners.csv (stats_citation.py).
  cluster        the course PPT's institution clusters (Old & large IITs, Newer IITs, IIITs, NITs, Central
                 Universities, IISc/TIFR/IISERs, Premier science institutes, CSIR labs, DAE institutes), matched by
                 institution name; anything else = 'Not a course cluster'. Our cluster: Old & large IITs.
  cross_cluster  partner's cluster differs from ours
  Jaccard        topic profile of an institution = its top-N OpenAlex subfields by number of 2016-2026 works, in
                 the same field scope as our dataset (Enrichment/scripts/scope.py SCOPE_MODE: 'all' = every
                 domain; 'sci_eng' = Physical + Life Sciences only); one OpenAlex group_by request per institution
                 (1 credit), the same method for our two IITs and for every partner. J = |A n B| / |A u B|. N = 20 reported; 10 and 30 in the CSV.
                 Partners: the top TOP_PARTNERS per institute by shared papers.
Online: needs OpenAlex (set OPENALEX_API_KEY or OPENALEX_KEY_FILE); results cached per scope in cache/topic_profiles_<SCOPE_MODE>.json.
Outputs (results/): partners.csv, cluster_summary.csv, jaccard_topics.csv
Figures: top_partners.png, jaccard_vs_shared.png
usage: python stats_connectivity.py"""
import os, re, json, collections as C
from common import INSTS, DATA, RES, CACHE, read_csv, write_csv, style, save, COLOR, TEXT2, MUTED, plt, short_name
from scope import SCOPE_MODE, OPENALEX_DOMAIN_IDS                  # Enrichment/scripts/scope.py

PROFILE_CACHE = os.path.join(CACHE, f"topic_profiles_{SCOPE_MODE}.json")

TOP_PARTNERS = 25
NS = (10, 20, 30)
OURS = {"IIT Kharagpur": "I145894827", "IIT Roorkee": "I154851008"}
CLUSTERS = [  # (cluster, name pattern) - course PPT slides 3-9
    ("Old & large IITs", r"Indian Institute of Technology (Bombay|Madras|Delhi|Kanpur|Kharagpur|Roorkee|Guwahati|Hyderabad)\b"),
    ("Newer IITs", r"Indian Institute of Technology (Gandhinagar|Jodhpur|Patna|\(BHU\)|BHU|Indore|Mandi|Bhubaneswar|Tirupati|"
                   r"Jammu|Goa|Palakkad|Dharwad|Bhilai)"),
    ("IIITs", r"Information Technology|\bIIIT"),
    ("NITs", r"National Institute of Technology|Maulana Azad National Institute"),
    ("IISc / TIFR / IISERs", r"Indian Institute of Science\b|Tata Institute of Fundamental|Science Education and Research"),
    ("Premier science institutes", r"Indian Statistical Institute|Institute of Mathematical Sciences|Chennai Mathematical|"
                                   r"Harish-Chandra|National Centre for Biological|S\. ?N\. Bose|Bose Institute|Saha Institute"),
    ("CSIR labs", r"\bCSIR\b|Council of Scientific|National Chemical Laboratory|Indian Institute of Chemical Technology|"
                  r"Central Electrochemical|Central Food Technological|National Institute for Interdisciplinary Science|"
                  r"National Metallurgical|National Physical Laboratory|Central Scientific Instruments|Central Glass|"
                  r"Central Mechanical Engineering|Central Road Research|Central Institute of Mining|Central Building Research|"
                  r"Central Electronics Engineering|Structural Engineering Research|Advanced Materials and Processes|"
                  r"Central Drug Research|Centre for Cellular and Molecular|Institute of Genomics|Institute of Microbial Technology"),
    ("DAE institutes", r"Bhabha Atomic|Indira Gandhi Centre for Atomic|Raja Ramanna|National Institute of Science Education"),
    ("Central Universities", r"Jawaharlal Nehru University|University of Hyderabad|University of Delhi|Banaras Hindu|"
                             r"Jadavpur|Jamia Millia"),
]


def cluster(name):
    for c, pat in CLUSTERS:
        if re.search(pat, name or ""):
            return c
    return "Not a course cluster"


def topic_profile(oa_id, cache):
    if oa_id in cache:
        return cache[oa_id]
    from oa import get                                            # Enrichment/scripts/oa.py
    dom = OPENALEX_DOMAIN_IDS[SCOPE_MODE]
    j = get("/works", {"filter": f"authorships.institutions.lineage:{oa_id},publication_year:2016-2026"
                                 + (f",primary_topic.domain.id:{dom}" if dom else ""), "group_by": "primary_topic.subfield.id"})
    prof = [[g["key_display_name"], g["count"]] for g in j["group_by"] if g["key"] and g["key"] != "unknown"]
    cache[oa_id] = prof
    json.dump(cache, open(PROFILE_CACHE, "w", encoding="utf8"), indent=0)
    return prof


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def main():
    style()
    conns = read_csv(os.path.join(DATA, "indian_connections.csv"))
    flows = {(r["institution"], r["partner"]): r for r in read_csv(os.path.join(RES, "citation_flow_partners.csv"))}
    cache = json.load(open(PROFILE_CACHE, encoding="utf8")) if os.path.exists(PROFILE_CACHE) else {}

    prow = []
    for r in conns:
        f = flows.get((r["your_inst"], r["partner_inst"]), {})
        cl = cluster(r["partner_inst"])
        prow.append({"institution": r["your_inst"], "partner": r["partner_inst"], "partner_openalex": r["partner_openalex"],
                     "shared_papers": int(r["shared_papers"]), "citations_of_shared_papers": int(r["total_citations"]),
                     "citations_from_partner": int(f.get("citations_from_partner") or 0),
                     "citations_to_partner": int(f.get("citations_to_partner") or 0),
                     "cluster": cl, "cross_cluster": cl != "Old & large IITs"})
    prow.sort(key=lambda x: (x["institution"], -x["shared_papers"]))
    rank = C.Counter()
    for p in prow:
        rank[p["institution"]] += 1
        p["rank_by_shared_papers"] = rank[p["institution"]]

    # Jaccard topic similarity
    profiles = {name: topic_profile(oid, cache) for name, oid in OURS.items()}
    jrows = []
    for name in INSTS.values():
        top = [p for p in prow if p["institution"] == name and p["shared_papers"] > 0][:TOP_PARTNERS]
        for other in INSTS.values():
            if other != name and not any(p["partner_openalex"] == OURS[other] for p in top):
                top.append({"partner": "Indian Institute of Technology " + other.split()[-1], "partner_openalex": OURS[other],
                            "shared_papers": next((p["shared_papers"] for p in prow if p["institution"] == name and p["partner_openalex"] == OURS[other]), 0),
                            "cluster": "Old & large IITs"})
        for p in top:
            prof = topic_profile(p["partner_openalex"], cache)
            row = {"institution": name, "partner": p["partner"], "shared_papers": p["shared_papers"], "cluster": p["cluster"],
                   "partner_works_in_scope": sum(c for _, c in prof)}
            for n in NS:
                a = {s for s, _ in profiles[name][:n]}
                b = {s for s, _ in prof[:n]}
                row[f"jaccard_top{n}"] = round(jaccard(a, b), 3)
            row["shared_subfields_top20"] = "; ".join(sorted({s for s, _ in profiles[name][:20]} & {s for s, _ in prof[:20]}))
            jrows.append(row)
    write_csv("jaccard_topics.csv", jrows)
    jac = {(r["institution"], r["partner"]): r["jaccard_top20"] for r in jrows}
    for p in prow:
        p["jaccard_top20"] = jac.get((p["institution"], p["partner"]), "")
    write_csv("partners.csv", prow, ["institution", "rank_by_shared_papers", "partner", "shared_papers", "citations_of_shared_papers",
                                     "citations_from_partner", "citations_to_partner", "cluster", "cross_cluster",
                                     "jaccard_top20", "partner_openalex"])
    crow = []
    for name in INSTS.values():
        by = C.defaultdict(lambda: C.Counter())
        for p in prow:
            if p["institution"] == name:
                b = by[p["cluster"]]
                b["partners"] += 1; b["shared_papers"] += p["shared_papers"]
                b["citations_from_partner"] += p["citations_from_partner"]; b["citations_to_partner"] += p["citations_to_partner"]
        for cl, b in sorted(by.items(), key=lambda x: -x[1]["shared_papers"]):
            crow.append({"institution": name, "cluster": cl, "cross_cluster": cl != "Old & large IITs", **b})
    write_csv("cluster_summary.csv", crow, ["institution", "cluster", "cross_cluster", "partners", "shared_papers",
                                            "citations_from_partner", "citations_to_partner"])

    # figures
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, name in zip(axes, INSTS.values()):
        top = [p for p in prow if p["institution"] == name][:12]
        ax.barh(range(len(top)), [p["shared_papers"] for p in top], color=COLOR[name], height=0.6)
        ax.set_yticks(range(len(top)), [short_name(p["partner"]) + ("" if p["cross_cluster"] else "  ·") for p in top], fontsize=8)
        ax.invert_yaxis()
        ax.grid(axis="y", visible=False)
        for i, p in enumerate(top):
            ax.text(p["shared_papers"], i, f" {p['shared_papers']}", va="center", fontsize=8, color=TEXT2)
        ax.set_title(f"{name}: co-authored papers per partner", fontsize=10)
        ax.set_xlabel("shared papers (· = same cluster: old & large IITs)")
        ax.margins(x=0.12)
    fig.suptitle("Top 12 Indian partner institutions by co-authored papers", x=0.01, y=1.03, ha="left", fontweight="bold", fontsize=12)
    fig.tight_layout()
    save(fig, "top_partners.png")

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    for name in INSTS.values():
        rs = [r for r in jrows if r["institution"] == name]
        ax.scatter([r["shared_papers"] for r in rs], [r["jaccard_top20"] for r in rs], color=COLOR[name], s=34,
                   edgecolors="#fcfcfb", linewidths=1.5, label=name, zorder=3)
        picks = []
        for r in sorted(rs, key=lambda r: -r["shared_papers"])[:2] + sorted(rs, key=lambda r: r["jaccard_top20"])[:2]:
            if r not in picks:
                picks.append(r)
        for k, r in enumerate(picks):
            ax.annotate(short_name(r["partner"], 32), (r["shared_papers"], r["jaccard_top20"]),
                        xytext=(6, 6 if (k + (name == "IIT Roorkee")) % 2 == 0 else -11), textcoords="offset points",
                        fontsize=7.5, color=TEXT2)
    ax.set_xlabel("shared papers")
    ax.set_ylabel("Jaccard similarity of top-20 research subfields")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper right")
    ax.set_title("Do we collaborate most with institutions that research the same things?")
    save(fig, "jaccard_vs_shared.png")

    for name in INSTS.values():
        rs = sorted([r for r in jrows if r["institution"] == name], key=lambda r: -r["jaccard_top20"])
        print(name, "most similar:", [(short_name(r["partner"], 24), r["jaccard_top20"]) for r in rs[:3]],
              "| least:", [(short_name(r["partner"], 24), r["jaccard_top20"]) for r in rs[-3:]])


if __name__ == "__main__":
    main()

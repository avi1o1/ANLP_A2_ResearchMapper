"""Journal and venue statistics: important journal groups, impact factor bands, large collaborations, CORE conferences.
Needs fetch_openalex_extra.py (sources, paper -> source) and results/faculty.csv (departments).
Outputs (results/):
  important_journals.csv        papers per group, institute and year. Groups: APS (all American Physical Society
                                journals), PRL (Physical Review Letters, also inside APS), SPIE journals, SPIE conference
                                proceedings, Nature journals (titles 'Nature ...' published by Nature Portfolio / Springer
                                Nature), JACS
  important_journal_papers.csv  the papers themselves with their faculty
  impact_factor.csv             per institute (and per year, and per department): journal papers with a known IF,
                                mean / median IF, papers in journals with IF > 5 and IF > 10
  large_collaborations.csv      papers with more than 10 authors: count, share, citations, per institute and year
  large_collaboration_papers.csv  the 30 most-cited of them per institute
  core_summary.csv              conference papers by CORE rank, per institute and year, and per department
  core_top_venues.csv           top 10 CORE-ranked conferences per institute by papers
IF (OpenAlex) = the journal's OpenAlex 2-year mean citedness: citations in the last year to its papers of the two
years before, divided by the number of those papers. Same formula as Clarivate's Journal Impact Factor but on
OpenAlex data and the current value (not the value in the year of publication); it is usually higher than the JIF.
Author counts come from OpenAlex, which lists at most 100 authors: 100 means 100 or more.
usage: python stats_journals.py"""
import os, collections as C
import numpy as np
from common import (INSTS, YEARS, RES, load_records, paper_key, cites, read_csv, write_csv, impact_factor, source_of,
                    n_authors, style, save, COLOR, plt)

LARGE = 10                    # 'more than 10 authors'
NATURE_PUBLISHERS = ("Nature Portfolio", "Springer Nature", "Springer Science+Business Media")


def groups_of(r):
    s = source_of(r) or {}
    pub, venue = s.get("publisher") or "", str(r["venue"])
    g = []
    if r["type"] == "journal":
        if pub == "American Physical Society":
            g.append("APS (all Physical Review journals)")
        if venue == "Physical Review Letters":
            g.append("PRL")
        if pub == "SPIE":
            g.append("SPIE journals")
        if (venue == "Nature" or venue.startswith("Nature ")) and pub.startswith(NATURE_PUBLISHERS):
            g.append("Nature journals")
        if venue == "Journal of the American Chemical Society":
            g.append("JACS")
    elif pub == "SPIE":
        g.append("SPIE proceedings")
    return g


GROUPS = ["APS (all Physical Review journals)", "PRL", "SPIE journals", "SPIE proceedings", "Nature journals", "JACS"]


def main():
    style()
    recs = {name: load_records(inst) for inst, name in INSTS.items()}
    dept = {(f["institution"], f["roster_id"]): f["department"] for f in read_csv(os.path.join(RES, "faculty.csv"))}

    # ------------------------------------------------ important journals
    irows, plist = [], []
    for name, rs in recs.items():
        cnt = C.Counter()
        for r in rs:
            for g in groups_of(r):
                cnt[(g, r["year"])] += 1
                plist.append({"institution": name, "group": g, "year": r["year"], "journal": r["venue"],
                              "title": r["title"], "citations": cites(r), "doi": r["doi"],
                              "faculty": "; ".join(f["name"] for f in r["faculty"])})
        for g in GROUPS:
            row = {"institution": name, "group": g, "total": sum(v for (gg, _), v in cnt.items() if gg == g)}
            row.update({str(y): cnt[(g, y)] for y in YEARS})
            irows.append(row)
    plist.sort(key=lambda x: (x["institution"], GROUPS.index(x["group"]), -(x["citations"] or 0)))
    write_csv("important_journals.csv", irows)
    write_csv("important_journal_papers.csv", plist)

    # ------------------------------------------------ impact factor bands
    frows = []
    def band(rs, **key):
        j = [r for r in rs if r["type"] == "journal"]
        ifs = [impact_factor(r) for r in j]
        k = [x for x in ifs if x is not None]
        if not j:
            return
        frows.append(dict(key, journal_papers=len(j), with_if=len(k),
                          mean_if=round(float(np.mean(k)), 2) if k else "", median_if=round(float(np.median(k)), 2) if k else "",
                          if_over_5=sum(x > 5 for x in k), if_over_10=sum(x > 10 for x in k),
                          share_if_over_5=round(sum(x > 5 for x in k) / len(k), 4) if k else "",
                          share_if_over_10=round(sum(x > 10 for x in k) / len(k), 4) if k else ""))
    for name, rs in recs.items():
        band(rs, institution=name, scope="all years", department="")
        for y in YEARS:
            band([r for r in rs if r["year"] == y], institution=name, scope=str(y), department="")
        by_d = C.defaultdict(dict)
        for r in rs:
            for f in r["faculty"]:
                by_d[dept.get((name, f["roster_id"]), f["department"])][paper_key(r)] = r
        for d, ps in sorted(by_d.items(), key=lambda x: -len(x[1])):
            band(list(ps.values()), institution=name, scope="all years", department=d)
    write_csv("impact_factor.csv", frows)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = np.arange(len(YEARS))
    for k, name in enumerate(recs):
        yr = {fr["scope"]: fr for fr in frows if fr["institution"] == name and fr["department"] == "" and fr["scope"] != "all years"}
        ax.bar(x + (k - 0.5) * 0.38, [yr[str(y)]["share_if_over_5"] * 100 for y in YEARS], width=0.36, color=COLOR[name], label=name)
    ax.set_xticks(x, YEARS)
    ax.set_ylabel("% of journal papers")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    ax.set_title("Journal papers in journals with IF (OpenAlex) above 5")
    save(fig, "impact_factor_over5.png")

    # ------------------------------------------------ large collaborations
    lrows, lpapers = [], []
    for name, rs in recs.items():
        for scope, sub in [("all years", rs)] + [(str(y), [r for r in rs if r["year"] == y]) for y in YEARS]:
            big = [r for r in sub if (n_authors(r) or 0) > LARGE]
            known = [r for r in sub if n_authors(r)]
            lrows.append({"institution": name, "scope": scope, "papers": len(sub), "papers_author_count_known": len(known),
                          "more_than_10_authors": len(big), "share": round(len(big) / len(known), 4) if known else "",
                          "with_100_or_more": sum(1 for r in big if n_authors(r) >= 100),
                          "citations_of_large": sum(cites(r) or 0 for r in big),
                          "share_of_all_citations": round(sum(cites(r) or 0 for r in big) / max(1, sum(cites(r) or 0 for r in sub)), 4)})
        top = sorted((r for r in rs if (n_authors(r) or 0) > LARGE), key=lambda r: -(cites(r) or 0))[:30]
        lpapers += [{"institution": name, "title": r["title"], "year": r["year"], "journal": r["venue"],
                     "authors": "100+" if n_authors(r) >= 100 else n_authors(r), "citations": cites(r), "doi": r["doi"]}
                    for r in top]
    write_csv("large_collaborations.csv", lrows)
    write_csv("large_collaboration_papers.csv", lpapers)

    # ------------------------------------------------ CORE
    crows, vrows = [], []
    ranks = ["A*", "A", "B", "C"]
    for name, rs in recs.items():
        conf = [r for r in rs if r["type"] == "conference"]
        for scope, sub in [("all years", conf)] + [(str(y), [r for r in conf if r["year"] == y]) for y in YEARS]:
            c = C.Counter((r.get("core") or {}).get("core_rank") for r in sub)
            crows.append({"institution": name, "scope": scope, "department": "", "conference_papers": len(sub),
                          **{k: c[k] for k in ranks}, "ranked": sum(c[k] for k in ranks),
                          "ranked_share": round(sum(c[k] for k in ranks) / len(sub), 4) if sub else ""})
        by_d = C.defaultdict(dict)
        for r in conf:
            for f in r["faculty"]:
                by_d[dept.get((name, f["roster_id"]), f["department"])][paper_key(r)] = r
        for d, ps in sorted(by_d.items(), key=lambda x: -len(x[1])):
            c = C.Counter((r.get("core") or {}).get("core_rank") for r in ps.values())
            if sum(c[k] for k in ranks):
                crows.append({"institution": name, "scope": "all years", "department": d, "conference_papers": len(ps),
                              **{k: c[k] for k in ranks}, "ranked": sum(c[k] for k in ranks),
                              "ranked_share": round(sum(c[k] for k in ranks) / len(ps), 4)})
        v = C.Counter(((r["core"]["core_title"], r["core"]["core_rank"]) for r in conf if (r.get("core") or {}).get("core_rank")))
        for k, ((title, rank), n) in enumerate(v.most_common(10), 1):
            vrows.append({"institution": name, "rank_by_papers": k, "conference": title, "core_rank": rank, "papers": n})
    write_csv("core_summary.csv", crows)
    write_csv("core_top_venues.csv", vrows)

    for r in irows:
        print(r["institution"], r["group"], r["total"])
    for fr in frows:
        if fr["scope"] == "all years" and not fr["department"]:
            print(fr)
    for lr in lrows:
        if lr["scope"] == "all years":
            print(lr)


if __name__ == "__main__":
    main()

"""Institution-, department- and faculty-level statistics (brief section 8 and the dashboard panels).
Per institute, papers = that institute's records in the analysis set (a joint Kharagpur-Roorkee paper counts for both).
Outputs (results/):
  trend.csv              papers per year and type, 2016-2026 (2026 partial: collected October 2026)
  quartiles.csv          journal papers by Scimago quartile; Q1 fraction of ranked journal papers and of all journal papers
  core_ranks.csv         conference papers by CORE rank
  top_journals.csv       top 5 journals per institute by paper count
  most_cited.csv         top 10 most-cited papers per institute (+ 'Both' = the two institutes together)
  research_areas.csv     share of papers per OpenAlex field (primary topic), per institute
  faculty.csv            per faculty member: papers, citations, h-index, top journal, Q1 papers, years active
  departments.csv        per department: faculty, papers (distinct), citations, Q1 fraction, median / max h-index
Figures (figures/): trend.png, quartiles.png, h_index_hist.png, research_areas.png
h-index = Hirsch index over the faculty member's papers in this dataset (2016-2026 window, citations at collection
date) - lower than a career h-index; papers with an unknown citation count are skipped.
usage: python stats_bibliometric.py"""
import collections as C
import numpy as np
from common import (INSTS, YEARS, PARTIAL_YEAR, load_records, paper_key, cites, write_csv, h_index, style, save,
                    COLOR, ORDINAL, TEXT2, MUTED, plt)

TYPES = ["journal", "conference", "book-chapter", "preprint"]


def main():
    style()
    recs = {name: load_records(inst) for inst, name in INSTS.items()}

    # ------------------------------------------------ trend
    rows = []
    for name, rs in recs.items():
        by = C.Counter((r["year"], r["type"] if r["type"] in TYPES else "other") for r in rs)
        for y in YEARS:
            row = {"institution": name, "year": y, "total": sum(v for (yy, _), v in by.items() if yy == y)}
            row.update({t: by[(y, t)] for t in TYPES + ["other"]})
            row["partial_year"] = y == PARTIAL_YEAR
            rows.append(row)
    write_csv("trend.csv", rows)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for name in recs:
        ys = [r["total"] for r in rows if r["institution"] == name]
        ax.plot(YEARS[:-1], ys[:-1], color=COLOR[name], marker="o", markersize=4)
        ax.plot(YEARS[-2:], ys[-2:], color=COLOR[name], linestyle=(0, (3, 3)), marker="o", markersize=4)
        ax.annotate(f"{name}  {ys[-2]:,}", (YEARS[-2], ys[-2]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=TEXT2)
    ax.set_title("Papers per year, 2016-2026")
    ax.set_ylabel("papers (IIT affiliation confirmed)")
    ax.set_xticks(YEARS)
    ax.set_ylim(0, None)
    ax.text(YEARS[-1], ax.get_ylim()[1] * 0.04, "2026 partial\n(to Oct)", ha="center", fontsize=8, color=MUTED)
    ax.margins(x=0.08)
    save(fig, "trend.png")

    # ------------------------------------------------ quartiles & CORE
    qrows, crows = [], []
    for name, rs in recs.items():
        j = [r for r in rs if r["type"] == "journal"]
        q = C.Counter((r.get("quartile") or {}).get("quartile") for r in j)
        ranked = sum(q[k] for k in ("Q1", "Q2", "Q3", "Q4"))
        qrows.append({"institution": name, "journal_papers": len(j), "Q1": q["Q1"], "Q2": q["Q2"], "Q3": q["Q3"],
                      "Q4": q["Q4"], "not_in_scimago": q[None], "ranked_share": round(ranked / len(j), 4),
                      "q1_fraction_of_ranked": round(q["Q1"] / ranked, 4),
                      "q1_fraction_of_all_journal": round(q["Q1"] / len(j), 4)})
        conf = [r for r in rs if r["type"] == "conference"]
        cr = C.Counter((r.get("core") or {}).get("core_rank") for r in conf)
        crows.append({"institution": name, "conference_papers": len(conf), "A*": cr["A*"], "A": cr["A"], "B": cr["B"],
                      "C": cr["C"], "not_core_ranked": cr[None]})
    write_csv("quartiles.csv", qrows)
    write_csv("core_ranks.csv", crows)
    fig, ax = plt.subplots(figsize=(8, 2.6))
    for i, qr in enumerate(qrows):
        left = 0
        ranked = qr["Q1"] + qr["Q2"] + qr["Q3"] + qr["Q4"]
        for k, col in zip(("Q1", "Q2", "Q3", "Q4"), ORDINAL):
            w = qr[k] / ranked * 100
            ax.barh(i, w - 0.3, left=left + 0.15, color=col, height=0.55)
            if w > 6:
                ax.text(left + w / 2, i, f"{k} {w:.0f}%", ha="center", va="center", fontsize=8,
                        color="white" if k in ("Q1", "Q2") else "#0b0b0b")
            left += w
        ax.text(100.8, i, f"Q4 {qr['Q4'] / ranked * 100:.1f}%", va="center", fontsize=8, color=TEXT2)
    ax.set_yticks(range(len(qrows)), [qr["institution"] for qr in qrows])
    ax.invert_yaxis()
    ax.set_xlim(0, 109)
    ax.set_xticks(range(0, 101, 20))
    ax.set_xlabel("% of journal papers with a Scimago quartile")
    ax.grid(axis="y", visible=False)
    ax.set_title("Journal quartile mix (Scimago SJR, publication year)")
    save(fig, "quartiles.png")

    # ------------------------------------------------ top journals, most cited
    trows, mrows = [], []
    for name, rs in recs.items():
        cnt = C.Counter(r["venue"] for r in rs if r["type"] == "journal" and not str(r["venue"]).startswith("TODO"))
        for rank, (v, n) in enumerate(cnt.most_common(5), 1):
            qs = C.Counter((r.get("quartile") or {}).get("quartile") for r in rs if r["venue"] == v)
            trows.append({"institution": name, "rank": rank, "journal": v, "papers": n,
                          "most_common_quartile": qs.most_common(1)[0][0] or ""})
    both = {}
    for name, rs in recs.items():
        for r in rs:
            both.setdefault(paper_key(r), (r, set()))[1].add(name)
    for name, pool in list(recs.items()) + [("Both", [v[0] for v in both.values()])]:
        top = sorted((r for r in pool if cites(r) is not None), key=lambda r: -cites(r))[:10]
        for rank, r in enumerate(top, 1):
            mrows.append({"scope": name, "rank": rank, "title": r["title"], "journal": r["venue"], "year": r["year"],
                          "citations": cites(r), "doi": r["doi"],
                          "institutions": ";".join(sorted(both[paper_key(r)][1]))})
    write_csv("top_journals.csv", trows)
    write_csv("most_cited.csv", mrows)

    # ------------------------------------------------ research areas
    arows = []
    for name, rs in recs.items():
        f = C.Counter((r.get("research_area") or {}).get("field") or "Unknown" for r in rs)
        for field, n in f.most_common():
            arows.append({"institution": name, "field": field, "papers": n, "share": round(n / len(rs), 4)})
    write_csv("research_areas.csv", arows)
    fields = [f for f, _ in C.Counter({a["field"]: 0 for a in arows}).items()]
    tot = C.Counter()
    for a in arows:
        tot[a["field"]] += a["share"]
    fields = [f for f, _ in tot.most_common(12) if f != "Unknown"]
    fig, ax = plt.subplots(figsize=(8, 5.2))
    yy = np.arange(len(fields))
    for k, name in enumerate(recs):
        share = {a["field"]: a["share"] for a in arows if a["institution"] == name}
        vals = [share.get(f, 0) * 100 for f in fields]
        ax.barh(yy + (k - 0.5) * 0.38, vals, height=0.34, color=COLOR[name], label=name)
    ax.set_yticks(yy, fields)
    ax.invert_yaxis()
    ax.set_xlabel("% of the institute's papers (OpenAlex primary-topic field)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    ax.set_title("Research areas: top 12 fields")
    save(fig, "research_areas.png")

    # ------------------------------------------------ faculty & departments
    frows = []
    fac_papers = C.defaultdict(dict)        # (inst, roster_id) -> {paper_key: record}
    fac_info = {}
    for name, rs in recs.items():
        for r in rs:
            for f in r["faculty"]:
                fac_papers[(name, f["roster_id"])][paper_key(r)] = r
                fac_info[(name, f["roster_id"])] = f
    for key, ps in fac_papers.items():
        name, rid = key
        f = fac_info[key]
        cs = [cites(r) for r in ps.values()]
        jv = C.Counter(r["venue"] for r in ps.values() if r["type"] == "journal" and not str(r["venue"]).startswith("TODO"))
        frows.append({"institution": name, "faculty": f["name"], "department": f["department"], "roster_id": rid,
                      "person_source": "roster" if f.get("person_source", "roster") == "roster" else "ORCID record",
                      "papers": len(ps), "citations": sum(c for c in cs if c is not None),
                      "papers_unknown_citations": sum(1 for c in cs if c is None), "h_index": h_index(cs),
                      "q1_papers": sum(1 for r in ps.values() if (r.get("quartile") or {}).get("quartile") == "Q1"),
                      "top_journal": jv.most_common(1)[0][0] if jv else "",
                      "first_year": min(r["year"] for r in ps.values()), "last_year": max(r["year"] for r in ps.values())})
    frows.sort(key=lambda x: (x["institution"], -x["h_index"], -x["citations"]))
    write_csv("faculty.csv", frows)
    drows = []
    by_dept = C.defaultdict(list)
    for fr in frows:
        by_dept[(fr["institution"], fr["department"])].append(fr)
    for (name, dept), fl in by_dept.items():
        ps = {}
        for fr in fl:
            ps.update(fac_papers[(name, fr["roster_id"])])
        j = [r for r in ps.values() if r["type"] == "journal"]
        ranked = [r for r in j if r.get("quartile")]
        hs = sorted(fr["h_index"] for fr in fl)
        drows.append({"institution": name, "department": dept, "faculty_with_papers": len(fl), "papers": len(ps),
                      "citations": sum(cites(r) or 0 for r in ps.values()),
                      "q1_fraction_of_ranked": round(sum(r["quartile"]["quartile"] == "Q1" for r in ranked) / len(ranked), 4) if ranked else "",
                      "median_h_index": float(np.median(hs)), "max_h_index": hs[-1]})
    drows.sort(key=lambda x: (x["institution"], -x["papers"]))
    write_csv("departments.csv", drows)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    bins = np.arange(0, max(fr["h_index"] for fr in frows) + 3, 2)
    for ax, name in zip(axes, recs):
        hs = [fr["h_index"] for fr in frows if fr["institution"] == name]
        ax.hist(hs, bins=bins, color=COLOR[name], rwidth=0.88)
        ax.set_title(f"{name}  (n={len(hs)}, median {np.median(hs):.0f})", fontsize=10)
        ax.set_xlabel("h-index (papers 2016-2026)")
    axes[0].set_ylabel("faculty")
    fig.suptitle("Faculty h-index distribution", x=0.01, y=1.04, ha="left", fontweight="bold", fontsize=12)
    save(fig, "h_index_hist.png")

    for q in qrows:
        print(f"{q['institution']}: journal papers {q['journal_papers']}, Q1 of ranked {q['q1_fraction_of_ranked']:.1%}, "
              f"ranked {q['ranked_share']:.1%}")
    for name in recs:
        hs = [fr["h_index"] for fr in frows if fr["institution"] == name]
        print(f"{name}: faculty {len(hs)}, median h {np.median(hs):.0f}, max h {max(hs)}")


if __name__ == "__main__":
    main()

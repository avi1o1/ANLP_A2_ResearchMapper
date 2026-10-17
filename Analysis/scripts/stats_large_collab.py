"""Papers with more than 10 authors ('large collaborations'): how much they move the headline numbers, and where they are.
Large = more than LARGE authors (OpenAlex author list, else the scraped one; common.n_authors), as in stats_journals.py.
  sensitivity      each headline number computed on all analysis-set papers and again without the large ones:
                   papers, citations, citations per paper, Q1 share of ranked journal papers, papers with >= 100
                   citations, large papers among the 10 most cited, faculty h-index (median / mean / max, computed as in
                   stats_bibliometric.py), the institute h-index, and how many faculty lose h-index points
  citation premium median citations of large vs other papers of the same institute and publication year, pooled
                   over 2016-2024 (2025-26 too young)
  where            department (via the faculty linked to the paper; a paper counts once per department), OpenAlex
                   field, venue and venue type, Scimago quartile / CORE rank, team-size band, and whether a co-author
                   is at a foreign institution (OpenAlex institution country other than IN)
  faculty          the faculty whose h-index drops most without the large papers
Outputs (results/): large_sensitivity.csv, large_premium.csv, large_by_department.csv, large_by_field.csv,
  large_by_venue.csv, large_size_bands.csv, large_faculty_impact.csv
Figure: large_collab_effect.png
usage: python stats_large_collab.py"""
import statistics as st, collections as C
import numpy as np
from common import INSTS, load_records, paper_key, cites, n_authors, h_index, write_csv, style, save, COLOR, TEXT2, plt

LARGE = 10
BANDS = [("11-20", 11, 20), ("21-50", 21, 50), ("51-99", 51, 99), ("100+", 100, 10 ** 6)]


def is_large(r):
    return (n_authors(r) or 0) > LARGE


def headline(rs):
    """Headline numbers of a set of papers (one institute)."""
    cs = [cites(r) for r in rs if cites(r) is not None]
    ranked = [r for r in rs if r["type"] == "journal" and (r.get("quartile") or {}).get("quartile")]
    fac = C.defaultdict(dict)
    for r in rs:
        for f in r["faculty"]:
            fac[f["roster_id"]][paper_key(r)] = cites(r)
    hs = {rid: h_index(list(ps.values())) for rid, ps in fac.items()}
    top10 = sorted(rs, key=lambda r: -(cites(r) or 0))[:10]
    return {"papers": len(rs), "citations": sum(cs), "citations per paper": round(sum(cs) / len(cs), 2),
            "median citations per paper": st.median(cs),
            "Q1 share of ranked journal papers": round(sum(r["quartile"]["quartile"] == "Q1" for r in ranked) / len(ranked), 4),
            "papers with >= 100 citations": sum(1 for c in cs if c >= 100),
            "large papers among the 10 most cited": sum(1 for r in top10 if is_large(r)),
            "faculty with papers": len(hs), "median faculty h-index": float(np.median(list(hs.values()))),
            "mean faculty h-index": round(float(np.mean(list(hs.values()))), 2), "max faculty h-index": max(hs.values()),
            "institute h-index": h_index(cs)}, hs


def main():
    style()
    srows, prem, drows, frows, vrows, brows, facrows = [], [], [], [], [], [], []
    for inst, name in INSTS.items():
        rs = load_records(inst)
        big = [r for r in rs if is_large(r)]
        rest = [r for r in rs if not is_large(r)]

        # ---------------- sensitivity
        a, h_all = headline(rs)
        b, h_rest = headline(rest)
        for k in a:
            row = {"institution": name, "metric": k, "all_papers": a[k], "without_large": b[k]}
            if isinstance(a[k], (int, float)) and a[k]:
                row["change"] = round(b[k] - a[k], 4)
                row["change_pct"] = round(100 * (b[k] - a[k]) / a[k], 2)
            srows.append(row)
        drop = {rid: h_all[rid] - h_rest.get(rid, 0) for rid in h_all}
        hit = [d for d in drop.values() if d > 0]
        srows += [{"institution": name, "metric": "faculty whose h-index drops", "all_papers": "", "without_large": len(hit),
                   "change": "", "change_pct": round(100 * len(hit) / len(h_all), 2)},
                  {"institution": name, "metric": "faculty who lose all their papers", "all_papers": "",
                   "without_large": sum(1 for rid in h_all if rid not in h_rest), "change": "", "change_pct": ""}]

        # ---------------- citation premium: same institute, same year
        ratios = []
        for y in range(2016, 2025):
            cb = [cites(r) for r in big if r["year"] == y and cites(r) is not None]
            co = [cites(r) for r in rest if r["year"] == y and cites(r) is not None]
            if cb and co:
                prem.append({"institution": name, "year": y, "large_papers": len(cb), "median_citations_large": st.median(cb),
                             "median_citations_other": st.median(co), "ratio": round(st.median(cb) / max(st.median(co), 1), 2)})
                ratios.append(st.median(cb) / max(st.median(co), 1))
        prem.append({"institution": name, "year": "2016-2024 (median of yearly ratios)", "large_papers": "", "median_citations_large": "",
                     "median_citations_other": "", "ratio": round(st.median(ratios), 2)})

        # ---------------- where: departments
        dept_all, dept_big = C.Counter(), C.Counter()
        for r in rs:
            for d in {f["department"] for f in r["faculty"]}:
                dept_all[d] += 1
                dept_big[d] += is_large(r)
        for d, nb in dept_big.most_common():
            if nb:
                drows.append({"institution": name, "department": d, "large_papers": nb, "department_papers": dept_all[d],
                              "share_of_department": round(nb / dept_all[d], 4), "share_of_institute_large": round(nb / len(big), 4)})

        # ---------------- fields
        fa, fb = C.Counter(), C.Counter()
        for r in rs:
            f = (r.get("research_area") or {}).get("field") or "Unknown"
            fa[f] += 1
            fb[f] += is_large(r)
        for f, nb in fb.most_common():
            if nb:
                frows.append({"institution": name, "field": f, "large_papers": nb, "share_of_large": round(nb / len(big), 4),
                              "share_of_field_papers": round(nb / fa[f], 4)})

        # ---------------- venues, types, quartiles
        vc = C.Counter(r["venue"] for r in big if not str(r["venue"]).startswith("TODO"))
        for v, n in vc.most_common(10):
            q = C.Counter((r.get("quartile") or {}).get("quartile") or (r.get("core") or {}).get("core_rank") or "" for r in big if r["venue"] == v)
            vrows.append({"institution": name, "kind": "venue", "label": v, "large_papers": n, "rank": q.most_common(1)[0][0]})
        for label, sub in (("type", lambda r: r["type"]),
                           ("quartile", lambda r: (r.get("quartile") or {}).get("quartile") or "unranked" if r["type"] == "journal" else None)):
            cb, co = C.Counter(map(sub, big)), C.Counter(map(sub, rest))
            for k in sorted(set(cb) | set(co), key=str):
                if k is not None:
                    vrows.append({"institution": name, "kind": label, "label": k, "large_papers": cb[k],
                                  "share_large": round(cb[k] / sum(v for x, v in cb.items() if x is not None), 4),
                                  "share_other": round(co[k] / sum(v for x, v in co.items() if x is not None), 4)})
        foreign = lambda r: any(i.get("country") not in ("IN", None) for i in (r.get("coauthor_institutions") or []))
        for lab, sub in (("large", big), ("other", rest)):
            vrows.append({"institution": name, "kind": "foreign co-author", "label": lab, "large_papers": sum(map(foreign, sub)),
                          "share_large": round(sum(map(foreign, sub)) / len(sub), 4)})

        # ---------------- team size bands
        for band, lo, hi in BANDS:
            sub = [r for r in big if lo <= n_authors(r) <= hi]
            cs = [cites(r) for r in sub if cites(r) is not None]
            brows.append({"institution": name, "authors": band, "papers": len(sub), "citations": sum(cs),
                          "median_citations": st.median(cs) if cs else "", "share_of_large": round(len(sub) / len(big), 4)})

        # ---------------- faculty most affected
        info = {f["roster_id"]: f for r in rs for f in r["faculty"]}
        nbig = C.Counter(f["roster_id"] for r in big for f in r["faculty"])
        for rid in sorted(drop, key=lambda x: (-drop[x], -nbig[x]))[:15]:
            facrows.append({"institution": name, "faculty": info[rid]["name"], "department": info[rid]["department"],
                            "large_papers": nbig[rid], "h_index": h_all[rid], "h_without_large": h_rest.get(rid, 0), "drop": drop[rid]})

    write_csv("large_sensitivity.csv", srows, ["institution", "metric", "all_papers", "without_large", "change", "change_pct"])
    write_csv("large_premium.csv", prem)
    write_csv("large_by_department.csv", drows)
    write_csv("large_by_field.csv", frows)
    write_csv("large_by_venue.csv", vrows, ["institution", "kind", "label", "large_papers", "rank", "share_large", "share_other"])
    write_csv("large_size_bands.csv", brows)
    write_csv("large_faculty_impact.csv", facrows)
    # ---------------- figure: what changes without them, and the citation premium per year
    show = [("citations", "citations"), ("papers with >= 100 citations", "papers with 100+ citations"), ("institute h-index", "institute h-index"),
            ("citations per paper", "citations per paper"), ("max faculty h-index", "highest faculty h-index"),
            ("median faculty h-index", "median faculty h-index"), ("Q1 share of ranked journal papers", "Q1 share of journal papers")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    for k, name in enumerate(INSTS.values()):
        vals = [next(r["change_pct"] for r in srows if r["institution"] == name and r["metric"] == m) for m, _ in show]
        ax.barh(np.arange(len(show)) + (k - 0.5) * 0.36, vals, height=0.34, color=COLOR[name], label=name)
    ax.set_yticks(range(len(show)), [lab for _, lab in show], fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color=TEXT2, linewidth=0.8)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("% change without papers of more than 10 authors")
    ax.set_title("What changes without them", fontsize=10)
    ax.legend(loc="lower left", fontsize=8)
    ax = axes[1]
    for k, name in enumerate(INSTS.values()):
        rows = [r for r in prem if r["institution"] == name and isinstance(r["year"], int)]
        ax.bar(np.array([r["year"] for r in rows]) + (k - 0.5) * 0.38, [r["ratio"] for r in rows], width=0.36, color=COLOR[name], label=name)
    ax.axhline(1, color=TEXT2, linewidth=0.8, linestyle=(0, (3, 3)))
    ax.set_xticks(range(2016, 2025))
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("median citations: big-team / other papers")
    ax.set_title("Citation premium against papers of the same year", fontsize=10)
    fig.tight_layout()
    save(fig, "large_collab_effect.png")

    for r in srows:
        print(r)
    for r in prem:
        if not isinstance(r["year"], int):
            print(r)


if __name__ == "__main__":
    main()

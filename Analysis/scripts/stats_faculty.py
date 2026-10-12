"""Faculty h-index and i10-index statistics, a check of why our h-index is lower than Google Scholar's, and the h-index
at the end of each year. Runs after stats_bibliometric.py (reads results/faculty.csv) and fetch_openalex_extra.py.
Outputs (results/):
  h_index_summary.csv   count, mean, SD, min, quartiles, 90th percentile, max of h and i10, per institute and department
  h_index_check.csv     per faculty member: h with our citation counts, h of the same papers with OpenAlex counts, and
                        the OpenAlex all-career h of their author profile
  h_index_check_summary.csv  medians of the three, and how many faculty sit below their career h
  h_index_by_year.csv   per institute and year: faculty h-index (mean, median, 90th pct) using papers published up to
                        that year and citations received up to that year (OpenAlex counts_by_year); also the
                        institute's own h-index over all its papers
Figures (figures/): h_index_by_year.png, h_index_check.png
Definitions: h = h papers with >= h citations each; i10 = papers with >= 10 citations. Both are over the person's
papers in this dataset (2016-2026, field scope, IIT affiliation confirmed) unless the column says 'all career'.
usage: python stats_faculty.py"""
import os, collections as C
import numpy as np
from common import (INSTS, YEARS, RES, load_records, paper_key, cites, read_csv, write_csv, h_index, i10_index, oa_extra,
                    style, save, COLOR, MUTED, plt)


def summary(vals):
    v = np.array([x for x in vals if x is not None], dtype=float)
    if not len(v):
        return {}
    return {"n": len(v), "mean": round(v.mean(), 2), "sd": round(v.std(ddof=1), 2) if len(v) > 1 else "",
            "min": int(v.min()), "q1": float(np.percentile(v, 25)), "median": float(np.median(v)),
            "q3": float(np.percentile(v, 75)), "p90": float(np.percentile(v, 90)), "max": int(v.max())}


def num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def main():
    style()
    fac = read_csv(os.path.join(RES, "faculty.csv"))
    recs = {name: load_records(inst) for inst, name in INSTS.items()}
    cby = oa_extra()["counts_by_year"]
    papers = C.defaultdict(dict)                          # (inst, roster_id) -> {paper_key: record}
    for name, rs in recs.items():
        for r in rs:
            for f in r["faculty"]:
                papers[(name, f["roster_id"])][paper_key(r)] = r

    # ------------------------------------------------ summary of h and i10
    rows = []
    groups = [(n, "All departments", [f for f in fac if f["institution"] == n]) for n in recs]
    by_dept = C.defaultdict(list)
    for f in fac:
        by_dept[(f["institution"], f["department"])].append(f)
    groups += sorted(((n, d, fl) for (n, d), fl in by_dept.items()), key=lambda g: (g[0], -len(g[2])))
    for name, dept, fl in groups:
        for metric, col in (("h-index", "h_index"), ("i10-index", "i10_index"),
                            ("h-index, OpenAlex all career", "oa_h_index_all_career"),
                            ("i10-index, OpenAlex all career", "oa_i10_all_career")):
            s = summary(num(f[col]) for f in fl)
            if s:
                rows.append({"institution": name, "department": dept, "metric": metric, **s})
    write_csv("h_index_summary.csv", rows)

    # ------------------------------------------------ why is h low: same papers, OpenAlex counts, career profile
    crow = []
    for f in fac:
        ps = papers[(f["institution"], f["roster_id"])].values()
        oa_counts = [None if cby.get(r.get("openalex_id") or "") is None else sum(cby[r["openalex_id"]].values())
                     for r in ps]                     # None = OpenAlex has no record of the work: left out
        crow.append({"institution": f["institution"], "faculty": f["faculty"], "department": f["department"],
                     "papers": f["papers"], "h_our_counts": num(f["h_index"]), "h_openalex_counts": h_index(oa_counts),
                     "h_openalex_all_career": num(f["oa_h_index_all_career"]),
                     "openalex_works_all_career": num(f["oa_works_all_career"]), "oa_author_id": f["oa_author_id"]})
    write_csv("h_index_check.csv", crow)
    srows = []
    for name in recs:
        cr = [c for c in crow if c["institution"] == name and c["h_openalex_all_career"] is not None]
        a = np.array([c["h_our_counts"] for c in cr]); b = np.array([c["h_openalex_counts"] for c in cr])
        c_ = np.array([c["h_openalex_all_career"] for c in cr])
        srows.append({"institution": name, "faculty_compared": len(cr),
                      "median_h_our_counts": float(np.median(a)), "median_h_openalex_counts_same_papers": float(np.median(b)),
                      "median_h_openalex_all_career": float(np.median(c_)),
                      "mean_h_our_counts": round(a.mean(), 2), "mean_h_openalex_all_career": round(c_.mean(), 2),
                      "share_below_career_h": round(float(np.mean(a < c_)), 3),
                      "median_ratio_ours_to_career": round(float(np.median(a[c_ > 0] / c_[c_ > 0])), 3)})
    write_csv("h_index_check_summary.csv", srows)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
    for ax, name in zip(axes, recs):
        cr = [c for c in crow if c["institution"] == name and c["h_openalex_all_career"] is not None]
        x = [c["h_openalex_all_career"] for c in cr]; y = [c["h_our_counts"] for c in cr]
        ax.scatter(x, y, s=9, color=COLOR[name], alpha=0.45, linewidths=0)
        m = max(max(x), max(y)) + 2
        ax.plot([0, m], [0, m], color=MUTED, linewidth=1, linestyle="--")
        ax.set_title(name, fontsize=10)
        ax.set_xlabel("h-index, OpenAlex all career")
    axes[0].set_ylabel("h-index, our data (2016-2026)")
    fig.suptitle("Our h-index against the OpenAlex all-career h-index (dashed: equal)", x=0.01, y=1.03, ha="left",
                 fontweight="bold", fontsize=12)
    save(fig, "h_index_check.png")

    # ------------------------------------------------ h-index at the end of each year
    yrows = []
    for name, rs in recs.items():
        fl = [f for f in fac if f["institution"] == name]
        for y in YEARS:
            def cum(r):
                c = cby.get(r.get("openalex_id") or "")
                return None if c is None else sum(v for k, v in c.items() if int(k) <= y)
            hs = []
            for f in fl:
                ps = [r for r in papers[(name, f["roster_id"])].values() if r["year"] <= y]
                if ps:
                    hs.append(h_index(cum(r) for r in ps))
            inst_h = h_index(cum(r) for r in rs if r["year"] <= y)
            yrows.append({"institution": name, "year": y, "faculty_with_papers": len(hs),
                          "mean_h": round(float(np.mean(hs)), 2), "median_h": float(np.median(hs)),
                          "p90_h": float(np.percentile(hs, 90)), "max_h": max(hs), "institute_h_index": inst_h,
                          "partial_year": y == YEARS[-1]})
    write_csv("h_index_by_year.csv", yrows)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8))
    x = np.arange(len(YEARS))
    for k, name in enumerate(recs):
        yr = [r for r in yrows if r["institution"] == name]
        xs = x + (k - 0.5) * 0.38
        axes[0].bar(xs, [r["mean_h"] for r in yr], width=0.36, color=COLOR[name], label=name)
        axes[1].bar(xs, [r["institute_h_index"] for r in yr], width=0.36, color=COLOR[name], label=name)
    for ax, t in zip(axes, ("Mean faculty h-index at year end", "Institute h-index at year end")):
        ax.set_xticks(x, [str(y)[2:] for y in YEARS])
        ax.set_title(t, fontsize=10)
        ax.grid(axis="x", visible=False)
    axes[0].legend(loc="upper left")
    fig.suptitle("h-index over the years (papers and citations up to each year; 2026 to October)", x=0.01, y=1.04,
                 ha="left", fontweight="bold", fontsize=12)
    save(fig, "h_index_by_year.png")

    for s in srows:
        print(s)
    for r in yrows:
        if r["year"] in (2016, 2020, 2025):
            print(r["institution"], r["year"], "mean h", r["mean_h"], "median", r["median_h"], "institute h", r["institute_h_index"])


if __name__ == "__main__":
    main()

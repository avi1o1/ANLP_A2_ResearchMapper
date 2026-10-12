"""Faculty per year from the archived institute websites (WebScrape/scripts/wayback_rosters.py), and what it tells us
about our faculty-paper links. Only departments in field scope are counted (Enrichment/scripts/scope.py).
Outputs (results/):
  faculty_by_year.csv       per institute and year: faculty named on the archived pages, snapshots used, papers that
                            year and papers per listed faculty member
  faculty_by_year_dept.csv  the same count per department (departments with >= 5 people listed in some year)
  roster_link_check.csv     faculty-paper links in our data where the person was NOT named on the institute's archived
                            pages in the paper's year, although pages of that year exist. These are flagged, not
                            removed: a page can be missing from the archive, and a paper is often written before or
                            after a person is listed (students, joining year, publication delay)
Figure (figures/): faculty_by_year.png
usage: python stats_rosters.py"""
import os, csv, collections as C
import numpy as np
from common import INSTS, YEARS, RES, A2, load_records, read_csv, write_csv, style, save, COLOR, plt
from scope import FACULTY_DEPT_OUT

YEARLY = os.path.join(A2, "WebScrape", "rosters", "yearly")


def main():
    style()
    rows, drows, lrows, have = [], [], [], {}
    for inst, name in INSTS.items():
        fn = os.path.join(YEARLY, f"{inst}_faculty_by_year.csv")
        if not os.path.exists(fn):
            print("no yearly roster for", inst, "- run WebScrape/scripts/wayback_rosters.py", inst)
            continue
        ros = [r for r in read_csv(fn) if r["department"] not in FACULTY_DEPT_OUT]
        cov = {int(c["year"]): int(c["snapshots_used"]) for c in read_csv(os.path.join(YEARLY, f"{inst}_coverage.csv"))}
        have[name] = {r["roster_id"]: r for r in ros}
        recs = load_records(inst)
        per_year = C.Counter(r["year"] for r in recs)
        for y in YEARS:
            listed = sum(1 for r in ros if r[str(y)] == "1")
            rows.append({"institution": name, "year": y, "snapshots_used": cov.get(y, 0), "faculty_listed": listed,
                         "papers": per_year[y], "papers_per_listed_faculty": round(per_year[y] / listed, 2) if listed else ""})
        by_d = C.defaultdict(C.Counter)
        for r in ros:
            for y in YEARS:
                if r[str(y)] == "1":
                    by_d[r["department"]][y] += 1
        for d, cnt in sorted(by_d.items(), key=lambda x: -max(x[1].values())):
            if max(cnt.values()) >= 5:
                drows.append({"institution": name, "department": d, **{str(y): cnt[y] for y in YEARS}})
        flags = C.Counter()
        for r in recs:
            for f in r["faculty"]:
                p = have[name].get(f["roster_id"])
                if p is None or p[str(r["year"])] == "":
                    flags["not checkable"] += 1
                elif p[str(r["year"])] == "1":
                    flags["listed that year"] += 1
                elif any(p[str(y)] == "1" for y in YEARS):
                    flags["listed in other years only"] += 1
                else:
                    flags["never listed 2016-2026"] += 1
        tot = sum(flags.values())
        for k, v in flags.most_common():
            lrows.append({"institution": name, "faculty_paper_links": k, "count": v, "share": round(v / tot, 4)})
    if not rows:
        return
    write_csv("faculty_by_year.csv", rows)
    write_csv("faculty_by_year_dept.csv", drows)
    write_csv("roster_link_check.csv", lrows)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = np.arange(len(YEARS))
    names = [n for n in INSTS.values() if n in have]
    for k, name in enumerate(names):
        yr = [r for r in rows if r["institution"] == name]
        ax.bar(x + (k - (len(names) - 1) / 2) * 0.38, [r["faculty_listed"] for r in yr], width=0.36, color=COLOR[name], label=name)
    ax.set_xticks(x, YEARS)
    ax.set_ylabel("faculty named on archived pages")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left")
    ax.set_title("Faculty listed on the institute websites, by year (Wayback Machine)")
    save(fig, "faculty_by_year.png")
    for r in rows:
        print(r)
    for r in lrows:
        print(r)


if __name__ == "__main__":
    main()

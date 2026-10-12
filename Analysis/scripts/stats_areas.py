"""What is inside each research area. OpenAlex classifies every paper by its primary topic into a hierarchy:
domain (4) > field (26) > subfield (~250) > topic (~4,500). The 'research areas' chart shows fields; this script
lists the subfields inside each field, and explains the large Environmental Science share.
Needs results/faculty.csv (departments).
Outputs (results/):
  research_subfields.csv     per institute, field and subfield: papers, share of the field, share of the institute
  env_science_breakdown.csv  Environmental Science papers per institute: by subfield, by department of their faculty,
                             and the 10 most common topics
Figure (figures/): env_science_subfields.png
usage: python stats_areas.py"""
import os, collections as C
import numpy as np
from common import INSTS, RES, load_records, paper_key, read_csv, write_csv, style, save, COLOR, plt

ENV = "Environmental Science"


def main():
    style()
    recs = {name: load_records(inst) for inst, name in INSTS.items()}
    dept = {(f["institution"], f["roster_id"]): f["department"] for f in read_csv(os.path.join(RES, "faculty.csv"))}

    rows = []
    for name, rs in recs.items():
        ra = [(r.get("research_area") or {}) for r in rs]
        fields = C.Counter(a.get("field") or "Unknown" for a in ra)
        sub = C.Counter((a.get("field") or "Unknown", a.get("subfield") or "Unknown") for a in ra)
        for (f, s), n in sorted(sub.items(), key=lambda x: (-fields[x[0][0]], -x[1])):
            rows.append({"institution": name, "field": f, "field_papers": fields[f], "subfield": s, "papers": n,
                         "share_of_field": round(n / fields[f], 4), "share_of_institute": round(n / len(rs), 4)})
    write_csv("research_subfields.csv", rows)

    erows = []
    for name, rs in recs.items():
        env = [r for r in rs if (r.get("research_area") or {}).get("field") == ENV]
        for kind, cnt in (("subfield", C.Counter(r["research_area"]["subfield"] for r in env)),
                          ("topic", C.Counter(r["research_area"]["topic"] for r in env))):
            for k, n in cnt.most_common(None if kind == "subfield" else 10):
                erows.append({"institution": name, "by": kind, "name": k, "papers": n, "share_of_env_papers": round(n / len(env), 4)})
        d = C.defaultdict(set)
        for r in env:
            for f in r["faculty"]:
                d[dept.get((name, f["roster_id"]), f["department"])].add(paper_key(r))
            if not r["faculty"]:
                d["(no faculty identified)"].add(paper_key(r))
        for k, ps in sorted(d.items(), key=lambda x: -len(x[1]))[:12]:
            erows.append({"institution": name, "by": "department", "name": k, "papers": len(ps),
                          "share_of_env_papers": round(len(ps) / len(env), 4)})
        erows.append({"institution": name, "by": "total", "name": ENV, "papers": len(env),
                      "share_of_env_papers": round(len(env) / len(rs), 4)})     # here: share of all papers
    write_csv("env_science_breakdown.csv", erows)

    subs = [s for s, _ in C.Counter({e["name"]: 0 for e in erows if e["by"] == "subfield"}).items()]
    tot = C.Counter()
    for e in erows:
        if e["by"] == "subfield":
            tot[e["name"]] += e["papers"]
    subs = [s for s, _ in tot.most_common(8)]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    yy = np.arange(len(subs))
    for k, name in enumerate(recs):
        v = {e["name"]: e["share_of_env_papers"] * 100 for e in erows if e["institution"] == name and e["by"] == "subfield"}
        ax.barh(yy + (k - 0.5) * 0.38, [v.get(s, 0) for s in subs], height=0.34, color=COLOR[name], label=name)
    ax.set_yticks(yy, subs)
    ax.invert_yaxis()
    ax.set_xlabel("% of the institute's Environmental Science papers")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    ax.set_title("What 'Environmental Science' contains (OpenAlex subfields)")
    save(fig, "env_science_subfields.png")

    for e in erows:
        if e["by"] in ("total", "subfield", "department") and e["papers"] >= 100:
            print(e)


if __name__ == "__main__":
    main()

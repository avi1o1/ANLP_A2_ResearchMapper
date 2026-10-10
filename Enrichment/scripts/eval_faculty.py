"""Quality of the faculty links (no network access).
 1. Coverage: confirmed, in-scope papers with >= 1 faculty link; people with >= 1 paper.
 2. Golden sets (golden/golden_<inst>.csv, built by hand from faculty pages etc.): is the labelled IIT author
    among our links? ('not matched' is often a vague label or another co-author linked instead - inspect examples.)
 3. ORCID consistency: non-ORCID links where an author entry with a fitting name carries an ORCID that is not the
    linked person's (should be 0 after the paper-level veto).
 4. Department consistency: non-ORCID links where the author's own affiliation text names a department of this IIT
    and none of the named departments is the linked person's (examples printed for inspection).
usage: python eval_faculty.py <inst_key> [...]"""
import os, sys, csv, json, collections as C
from oa import OUT, REPO, norm_doi
from faculty import load_roster, compatible, named_depts

GOLD = os.path.join(REPO, "WebScrape", "golden")
COL = {"iit_kharagpur": "iitkgp_author", "iit_roorkee": "iitr_author"}

for inst in sys.argv[1:]:
    people = load_roster(inst)
    pid = {}
    for p in people:
        pid.setdefault(p["rid"], p)
    by_orcid = {o: p for p in people for o in p["orcids"]}
    depts = sorted({p["department"] for p in people if p["source"] == "roster"})
    recs, use, nf, conflict, how = {}, 0, 0, C.Counter(), C.Counter()
    dept_bad, dept_ex = C.Counter(), []
    for line in open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8"):
        s = line.strip().rstrip(",")
        if not s.startswith('{"title"'):
            continue
        r = json.loads(s)
        d = norm_doi(r["doi"])
        if d:
            recs[d] = r
        if r["affiliation_status"] == "verified" and r["sci_eng_scope"]["in_scope"] is True:
            use += 1
            nf += not r["faculty"]
        auth = (r["authors"] if isinstance(r["authors"], list) else []) + (r.get("authors_openalex") or [])
        for f in r["faculty"]:
            how[f["match"]] += 1
            if f["match"] == "orcid":
                continue
            p = pid[f["roster_id"]]
            os_ = {a.get("orcid") for a in auth if a.get("orcid") and compatible(a.get("name") or "", p["name"])}
            if os_ and not (os_ & p["orcids"]) and (p["orcids"] or any(o in by_orcid for o in os_)):
                conflict["links with a conflicting ORCID"] += 1
            affs = [x for a in auth if a.get("institute_author") is True and compatible(a.get("name") or "", p["name"])
                    for x in (a.get("affiliations") or [])]
            named = named_depts(affs, depts)
            if named:
                dept_bad["checked"] += 1
                if p["department"] not in named:
                    dept_bad[f["match"]] += 1
                    if len(dept_ex) < 8:
                        dept_ex.append((f["name"], p["department"], f["match"], sorted(named)))
    g, ex = C.Counter(), []
    for row in csv.DictReader(open(os.path.join(GOLD, f"golden_{inst}.csv"), encoding="utf8")):
        r = recs.get(norm_doi(row["doi"]))
        if not r:
            continue
        gold = [x.strip() for x in row[COL[inst]].split(";") if x.strip()]
        ours = r.get("faculty") or []
        if not ours:
            g["no faculty linked"] += 1
        elif any(compatible(gn, o["name"]) or compatible(o["name"], gn) for o in ours for gn in gold):
            g["labelled author linked"] += 1
        else:
            g["labelled author not linked"] += 1
            if len(ex) < 6:
                ex.append((gold, [o["name"] + " / " + o["match"] for o in ours], r["title"][:50]))
    print(f"===== {inst}")
    print(f"  confirmed in-scope papers with faculty: {use - nf}/{use} ({1 - nf / use:.1%})")
    print(f"  people with >= 1 paper: {len({f['roster_id'] for r in recs.values() for f in r['faculty']})} of {len(pid)}")
    print(f"  links by rule: {dict(how.most_common())}")
    print(f"  golden set: {dict(g)}")
    for e in ex:
        print("    not linked e.g.", e)
    print(f"  ORCID consistency: {dict(conflict) or 'no conflicting links'}")
    print(f"  department consistency (non-ORCID links whose author names a department): {dict(dept_bad)}")
    for e in dept_ex:
        print("    contradiction e.g.", e)

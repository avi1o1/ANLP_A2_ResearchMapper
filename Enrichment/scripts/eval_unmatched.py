"""Why do confirmed, in-scope papers have no faculty link? For each such paper, classify its IIT-affiliated authors:
  no_candidate     no roster person has a compatible name (student, staff, or someone not on the roster)
  ambiguous        2+ roster people have compatible names
  out_of_tenure    exactly one candidate, but the paper year is outside their tenure window
  initials_common  exactly one candidate, initials-only name with a common family name (rule refuses)
  orcid_conflict   exactly one candidate, but the paper carries a different person's ORCID for that name
  duplicate_name   exactly one candidate whose roster name belongs to 2+ people
and count papers with no IIT-affiliated author flagged at all.
usage: python eval_unmatched.py <inst_key> [...]"""
import sys, json, collections as C
from oa import OUT
from faculty import load_roster, compatible, split, initials_only, in_tenure, conflicts, tokens

for inst in sys.argv[1:]:
    people = load_roster(inst)
    by_orcid = {p["orcid"]: p for p in people if p["orcid"]}
    by_surname = C.defaultdict(list)
    for p in people:
        t = tokens(p["name"])
        for x in {t[0], t[-1]} if t else ():
            by_surname[x].append(p)
    paper_reason = C.Counter()
    author_reason = C.Counter()
    examples = C.defaultdict(list)
    n = 0
    for line in open(f"{OUT}/{inst}_enriched.json", encoding="utf8"):
        s = line.strip().rstrip(",")
        if not s.startswith('{"title"'):
            continue
        r = json.loads(s)
        if r["affiliation_status"] != "verified" or r["sci_eng_scope"]["in_scope"] is not True or r["faculty"]:
            continue
        n += 1
        auth = [(a.get("name") or "", a.get("orcid"), a.get("institute_author"))
                for a in (r["authors"] if isinstance(r["authors"], list) else []) + (r.get("authors_openalex") or [])]
        iit = {a[0]: a for a in auth if a[2] is True}
        if not iit:
            paper_reason["no IIT-affiliated author flagged"] += 1
            continue
        reasons = set()
        for name, (nm, orcid, _) in iit.items():
            sname, _ = split(nm)
            cands = {p["rid"]: p for p in by_surname.get(sname, []) if compatible(nm, p["name"])}
            if not cands:
                why = "no_candidate"
            elif len(cands) > 1:
                why = "ambiguous"
            else:
                p = next(iter(cands.values()))
                if p["dup_name"]:
                    why = "duplicate_name"
                elif not (isinstance(r["year"], int) and in_tenure(p, r["year"])):
                    why = "out_of_tenure"
                elif conflicts(p, auth, by_orcid):
                    why = "orcid_conflict"
                elif len(by_surname.get(sname, [])) >= 3 and initials_only(nm):
                    why = "initials_common"
                else:
                    why = "other"
            author_reason[why] += 1
            reasons.add(why)
            if len(examples[why]) < 4:
                examples[why].append((nm, [p["name"] + " / " + p["department"] for p in cands.values()][:3], r["year"]))
        paper_reason["best: " + sorted(reasons, key=["ambiguous", "initials_common", "out_of_tenure", "orcid_conflict",
                                                     "duplicate_name", "other", "no_candidate"].index)[0]] += 1
    print(f"===== {inst}: {n} confirmed in-scope papers without faculty")
    print("  papers by most promising reason:", dict(paper_reason.most_common()))
    print("  IIT-affiliated author names by reason:", dict(author_reason.most_common()))
    for k, v in examples.items():
        print("   ", k, v)

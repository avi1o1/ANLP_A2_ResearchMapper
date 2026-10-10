"""Link each paper to the faculty who wrote it (precision first; unmatched is preferred to a wrong match).
People = the roster (rosters/<inst>_faculty.csv) + ORCID-verified additions (cache/roster_supplement_<inst>.json,
written by roster_supplement.py: extra ORCID iDs of roster people, and faculty missing from the roster).
A person P is linked to paper R only if R's year lies in P's tenure window (when known) AND one of:
  orcid            an author of R (Crossref or OpenAlex list) carries one of P's ORCID iDs
  pipeline_tag     R was found through P by the original pipeline ('<name> [roster:<dept>]' in found_via_person)
                   and an author of R fits P
  name             an IIT-affiliated author of R fits P and fits nobody else
  name+department  an IIT-affiliated author of R has a name compatible with several people (or an initials-only
                   common family name), and the department named in THAT author's affiliation text on R matches
                   exactly one of them
  openalex_author  (second pass) an IIT-affiliated author of R whose OpenAlex author id was linked, in pass 1, to
                   exactly one person P, and who fits P
'Fits' (fits()): compatible name, no conflicting ORCID on any author entry of R (conflicts()), and - except for the
department rule - a name compatible with no other person of this IIT. For a family name carried by >= 3 people the
paper must show at least as many given names as the roster entry.
Department veto (dept_conflict(), all rules except 'orcid'): the author's own affiliation text on R names a roster
department of this IIT that is not P's.
Roster names carried by 2+ different people are matched only by ORCID or by the department rule.
Tenure window: [joining_year - 1, end + lag]; end = 2026 for current staff, else the '(YYYY-YYYY)' range in the
designation (ORCID employment years for additions); lag = 1 (Kharagpur), 4 (Roorkee: former-faculty end years are
lower bounds, PROCESS.md section 13).
Name compatibility (compatible()): same family name, given names agree position by position (equal, or one is the
other's initial); the roster name is also tried with its first token as the family name (Indian name order).
Initials-only forms are not used by the plain name rule for family names carried by >= 3 people of this IIT.
usage: python faculty.py <inst_key> [...]   -> adds record["faculty"] in out/<inst>_enriched.json"""
import os, re, sys, csv, json, unicodedata, collections as C
from oa import OUT, CACHE, REPO

ROSTERS = os.path.join(REPO, "WebScrape", "rosters")
LAG = {"iit_kharagpur": 1, "iit_roorkee": 4}
TITLES = {"dr", "prof", "professor", "mr", "mrs", "ms", "sri", "shri", "smt"}


# ---------------------------------------------------------------- names
def tokens(name):
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[\(\[].*", "", n)
    if "," in n:                                     # "Surname, Given"
        last, first = n.split(",", 1)
        n = first + " " + last
    return [x for x in re.split(r"[^a-z]+", n.replace(".", " ")) if x and x not in TITLES]


def split(name):
    t = tokens(name)
    return (t[-1], t[:-1]) if t else (None, [])


def _consistent(g1, g2):
    """Given names agree position by position: equal, or one is the other's initial. Extra trailing names are allowed."""
    if not g1 or not g2:
        return False
    return all(a == b or (len(a) == 1 and b[0] == a) or (len(b) == 1 and a[0] == b) for a, b in zip(g1, g2))


def compatible(paper_name, roster_name):
    """Same person by name? Tries the roster name as written and with its first token as the family name
    (Indian names are often written family-name-first: 'Kusam Sudhakar Reddy' = 'Sudhakar Reddy Kusam',
    'P. Gopinath' = 'Gopinath Packirisamy')."""
    s1, g1 = split(paper_name)
    t2 = tokens(roster_name)
    if not s1 or len(t2) < 2:
        return False
    for s2, g2 in ((t2[-1], t2[:-1]), (t2[0], t2[1:])):
        if s1 == s2 and _consistent(g1, g2):
            return True
    return False


def initials_only(name):
    return all(len(g) == 1 for g in split(name)[1])


# ---------------------------------------------------------------- departments
DEPT_STOP = {"of", "and", "the", "department", "dept", "school", "centre", "center", "for", "in", "unit"}


def _dept_tokens(s):
    s = (s or "").lower().replace("&", " and ").replace("engg", "engineering")
    s = re.sub(r"engineeringineering", "engineering", s)
    return {w.rstrip("s") for w in re.findall(r"[a-z]+", s) if w not in DEPT_STOP}


def dept_in(dept, affs):
    """Does the affiliation text name this roster department? All of the department's content words appear in
    one affiliation string, or the department's acronym in parentheses (e.g. 'CORAL') appears as a word."""
    core = _dept_tokens(re.sub(r"\(.*?\)", " ", dept))
    acr = [a.lower() for a in re.findall(r"\(([A-Z][A-Za-z\-]{2,})\)", dept)]
    for a in affs or []:
        if not isinstance(a, str):
            continue                          # some sources deliver empty affiliation entries
        at = _dept_tokens(a)
        if core and core <= at:
            return True
        if any(x in re.findall(r"[a-z\-]+", a.lower()) for x in acr):
            return True
    return False


def named_depts(affs, all_depts):
    """Departments of this IIT named in the affiliation text, keeping only the most specific ones: if both
    'Electrical Engineering' and 'Electronics and Electrical Communication Engg.' match, only the latter counts."""
    hits = [d for d in all_depts if dept_in(d, affs)]
    tk = {d: _dept_tokens(re.sub(r"\(.*?\)", " ", d)) for d in hits}
    return {d for d in hits if not any(e != d and tk[d] < tk[e] for e in hits)}


# ---------------------------------------------------------------- people
def load_roster(inst, supplement=True):
    ros = list(csv.DictReader(open(os.path.join(ROSTERS, f"{inst}_faculty.csv"), encoding="utf8")))
    people = []
    for i, r in enumerate(ros):
        start = int(r["joining_year"]) - 1 if r["joining_year"].strip().isdigit() else None
        m = re.search(r"\((\d{4})\s*-\s*(\d{4})\)", r["designation"] or "")
        if r["status"] == "former":
            end = int(m.group(2)) + LAG[inst] if m else None
            if m and start is None:
                start = int(m.group(1)) - 1
        else:
            end = 2026
        o = (r["orcid"] or "").strip().replace("https://orcid.org/", "") or None
        people.append({"rid": f"{inst}:{i}", "name": r["name"], "department": r["department"], "status": r["status"],
                       "orcid": o, "orcids": {o} if o else set(), "start": start, "end": end, "source": "roster"})
    # roster entries sharing an ORCID are one person listed in two units (Roorkee: 'Amit Agarwal' Civil Engg. =
    # 'Amit Agrawal' Mehta Family School, ORCID 0000-0002-3352-0227): one identity, first listing's department.
    first = {}
    for p in people:
        if p["orcid"] in first:
            q = first[p["orcid"]]
            q["also_listed_as"] = q.get("also_listed_as", []) + [f'{p["name"]} ({p["department"]})']
            p["rid"], p["department"], p["display"] = q["rid"], q["department"], q["name"]
        elif p["orcid"]:
            first[p["orcid"]] = p
    sfn = os.path.join(CACHE, f"roster_supplement_{inst}.json")
    if supplement and os.path.exists(sfn):
        pid = {p["rid"]: p for p in people}
        depts = sorted({p["department"] for p in people})
        acr = C.defaultdict(list)            # 'ECE' -> Electronics and Communication Engineering (initials of content words)
        for d in depts:
            acr["".join(w[0] for w in re.findall(r"[a-z]+", re.sub(r"\(.*?\)", " ", d.lower().replace("engg", "engineering")))
                        if w not in DEPT_STOP).upper()].append(d)
        for s in json.load(open(sfn, encoding="utf8")):
            if s["kind"] == "alt_orcid":
                for p in people:
                    if p["rid"] == s["roster_id"]:
                        p["orcids"].add(s["orcid"])
            elif s["kind"] == "new_person":
                hits = sorted(named_depts([s["department"]], depts)) if s.get("department") else []
                if not hits and s.get("department") and len(acr.get(s["department"].strip().upper(), [])) == 1:
                    hits = acr[s["department"].strip().upper()]
                dept = hits[0] if len(hits) == 1 else (s.get("department") or "unknown")
                # two ORCID iDs with the same name and department = one person (duplicate ORCID registration)
                same = [q for q in people if q["source"].startswith("orcid:") and q["department"] == dept
                        and " ".join(tokens(q["name"])) == " ".join(tokens(s["name"]))]
                if same:
                    same[0]["orcids"].add(s["orcid"])
                    same[0]["source"] += " + https://orcid.org/" + s["orcid"]
                    continue
                people.append({"rid": f"{inst}:orcid:{s['orcid']}", "name": s["name"],
                               "department": dept,
                               "status": "from ORCID employment record", "orcid": s["orcid"], "orcids": {s["orcid"]},
                               "start": s["start"] - 1 if s.get("start") else None,
                               "end": s["end"] + LAG[inst] if s.get("end") else 2026, "source": "orcid:" + s["url"]})
    norm = C.Counter(" ".join(tokens(p["name"])) for p in people if "display" not in p)
    for p in people:
        p["dup_name"] = norm[" ".join(tokens(p["name"]))] > 1
    return people


def in_tenure(p, year):
    return (p["start"] is None or year >= p["start"]) and (p["end"] is None or year <= p["end"])


def fits(name, orcid, p, by_orcid, by_surname, unique=True):
    """Author (name, orcid) on a paper can be person p: compatible name, no conflicting ORCID, and (if unique) the
    name fits no other person of this IIT (one of p's own ORCID iDs overrides the uniqueness test)."""
    if not compatible(name, p["name"]):
        return False
    if orcid:
        if orcid in p["orcids"]:
            return True
        if p["orcids"] or orcid in by_orcid:
            return False                      # the author is somebody else (different ORCID)
    s, given = split(name)
    # common family name (>= 3 people of this IIT): the paper must show at least as many given names as the roster
    # entry, so 'Piyush Kumar' cannot stand in for 'P. C. Ashwin Kumar' nor 'Shubham Jain' for 'S. S. Jain'
    if len(by_surname.get(s, [])) >= 3 and len(given) < len(tokens(p["name"])) - 1:
        return False
    if not unique:
        return True
    return not any(q["rid"] != p["rid"] and compatible(name, q["name"]) for q in by_surname.get(s, []))


def conflicts(p, authors, by_orcid):
    """Paper-level ORCID veto: an author entry with a name compatible with p carries an ORCID that is not p's
    (Crossref and OpenAlex list the same people twice, so all entries are checked together)."""
    os_ = {a[1] for a in authors if a[1] and compatible(a[0], p["name"])}
    if os_ & p["orcids"]:
        return False
    return any(p["orcids"] or (o in by_orcid and by_orcid[o]["rid"] != p["rid"]) for o in os_)


def dept_conflict(p, authors):
    """Department veto: the IIT-affiliated author entries whose names fit p name, in their own affiliation text, one
    or more roster departments of this IIT, none of which is p's (e.g. a Chemistry 'V. K. Gupta' paper is not by the
    Civil Engineering V. K. Gupta). Only roster department names are used, so renamed or unlisted units never veto."""
    if p["department"] not in ALL_DEPTS:
        return False
    affs = [x for a in authors if a[2] is True and compatible(a[0], p["name"]) for x in a[3]]
    named = named_depts(affs, ALL_DEPTS)
    return bool(named) and p["department"] not in named


def author_tuples(r):
    return [(a.get("name") or "", a.get("orcid"), a.get("institute_author"), a.get("affiliations") or [])
            for a in (r["authors"] if isinstance(r["authors"], list) else []) + (r.get("authors_openalex") or [])]


def match_record(r, by_orcid, by_tag, by_surname):
    year = r["year"] if isinstance(r["year"], int) else None
    authors = author_tuples(r)
    found = {}

    def ok(p):
        return year and in_tenure(p, year) and not conflicts(p, authors, by_orcid) and not dept_conflict(p, authors)

    for name, orcid, _, _ in authors:
        p = by_orcid.get(orcid) if orcid else None
        if p and year and in_tenure(p, year):
            found.setdefault(p["rid"], (p, "orcid"))
    for tag in r.get("found_via_person") or []:
        m = re.match(r"(.+?)\s*\[roster:(.+)\]$", tag)
        if not m:
            continue
        p = by_tag.get((" ".join(tokens(m.group(1))), m.group(2)))
        if p and not p["dup_name"] and ok(p) and any(fits(a[0], a[1], p, by_orcid, by_surname) for a in authors):
            found.setdefault(p["rid"], (p, "pipeline_tag"))
    for name, orcid, inst_aff, affs in authors:
        if inst_aff is not True:
            continue
        s, _ = split(name)
        pool = {q["rid"]: q for q in by_surname.get(s, []) if fits(name, orcid, q, by_orcid, by_surname, unique=False)}
        cands = [q for q in pool.values() if fits(name, orcid, q, by_orcid, by_surname)]
        if len(cands) == 1 and not cands[0]["dup_name"] and ok(cands[0]) and \
                not (len(by_surname.get(s, [])) >= 3 and initials_only(name)):
            found.setdefault(cands[0]["rid"], (cands[0], "name"))
            continue
        # department rule: the author's own affiliation text names the department of exactly one candidate
        if pool and affs:
            named = named_depts(affs, ALL_DEPTS)
            byd = [q for q in pool.values() if q["department"] in named]
            if len({q["rid"] for q in byd}) == 1 and ok(byd[0]):
                found.setdefault(byd[0]["rid"], (byd[0], "name+department"))
    return [{"name": p.get("display", p["name"]), "department": p["department"], "roster_id": p["rid"], "match": how,
             "person_source": p["source"]} for p, how in found.values()]


ALL_DEPTS = []      # departments of the institute being processed (set in run())


def run(inst):
    people = load_roster(inst)
    ALL_DEPTS[:] = sorted({p["department"] for p in people if p["source"] == "roster"})
    pid = {}
    for p in people:
        pid.setdefault(p["rid"], p)          # first listing = canonical identity
    by_orcid = {o: p for p in people for o in p["orcids"]}
    by_tag = {(" ".join(tokens(p["name"])), p["department"]): p for p in people if p["source"] == "roster"}
    by_surname = C.defaultdict(list)          # family-name candidates: last token, or first token (name order varies)
    for p in people:
        t = tokens(p["name"])
        for x in {t[0], t[-1]} if t else ():
            by_surname[x].append(p)
    fn = os.path.join(OUT, inst + "_enriched.json")
    lines = open(fn, encoding="utf8").read().split("\n")
    recs = {}
    for k, line in enumerate(lines):
        s = line.strip()
        if s.startswith('{"title"'):
            recs[k] = (json.loads(s.rstrip(",")), s.endswith(","))
    # pass 1
    oa_to_people = C.defaultdict(set)      # OpenAlex author id -> people it was reliably linked to
    for r, _ in recs.values():
        r["faculty"] = match_record(r, by_orcid, by_tag, by_surname)
        for f in r["faculty"]:
            for a in r.get("authors_openalex") or []:
                if a.get("openalex_author") and fits(a["name"], a.get("orcid"), pid[f["roster_id"]], by_orcid, by_surname):
                    oa_to_people[a["openalex_author"]].add(f["roster_id"])
    # pass 2: openalex_author
    for r, _ in recs.values():
        have = {f["roster_id"] for f in r["faculty"]}
        year = r["year"] if isinstance(r["year"], int) else None
        tuples = author_tuples(r)
        for a in r.get("authors_openalex") or []:
            ps = oa_to_people.get(a.get("openalex_author"))
            if a.get("institute_author") is not True or not ps or len(ps) != 1:
                continue
            p = pid[next(iter(ps))]
            if p["rid"] in have or p["dup_name"] or not fits(a["name"], a.get("orcid"), p, by_orcid, by_surname) \
                    or not (year and in_tenure(p, year)) or conflicts(p, tuples, by_orcid) or dept_conflict(p, tuples):
                continue
            r["faculty"].append({"name": p.get("display", p["name"]), "department": p["department"], "roster_id": p["rid"],
                                 "match": "openalex_author", "person_source": p["source"]})
            have.add(p["rid"])
    stats = C.Counter()
    for k, (r, comma) in recs.items():
        stats["papers_with_faculty" if r["faculty"] else "papers_without_faculty"] += 1
        for f in r["faculty"]:
            stats["link_" + f["match"]] += 1
            stats["link_to_orcid_addition"] += f["person_source"] != "roster"
        lines[k] = json.dumps(r, ensure_ascii=False) + ("," if comma else "")
    open(fn, "w", encoding="utf8").write("\n".join(lines))
    print(inst, dict(sorted(stats.items())), "| people with >=1 paper:",
          len({f["roster_id"] for r, _ in recs.values() for f in r["faculty"]}), "of", len(pid))


if __name__ == "__main__":
    for i in sys.argv[1:]:
        run(i)

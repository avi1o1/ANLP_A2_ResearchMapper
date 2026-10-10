"""Online roster check (ORCID public registry, pub.orcid.org; no key needed) for authors the roster misses.
Candidates, from confirmed papers after faculty.py has run:
  alt_orcid   an IIT-affiliated author whose name fits exactly one roster person P but who carries an ORCID that
              is not P's (and not any other roster person's)  -> is it P under a second ORCID iD?
  new_person  an IIT-affiliated author with an ORCID and no compatible roster person, on >= MIN_PAPERS confirmed papers
              -> a faculty member missing from the roster (typically a former faculty member)?
An ORCID is accepted only if its public record has an EMPLOYMENT entry at this IIT whose role title is a faculty
role (professor / faculty / lecturer; not visiting, adjunct, fellowships such as INSPIRE / Ramanujan, students,
postdocs, research or project staff). For alt_orcid the ORCID record's name must be compatible with P and every
department stated in those jobs must match P's roster department. The employment years become the tenure.
Records are cached in cache/orcid/<orcid>.json; accepted entries go to cache/roster_supplement_<inst>.json with
the evidence (organisation, department, role, years, record URL). faculty.py reads that file.
usage: python roster_supplement.py <inst_key> [...]   (re-run faculty.py afterwards; rebuild.sh does both)"""
import os, re, sys, json, time, collections as C
from concurrent.futures import ThreadPoolExecutor
import requests
from oa import OUT, CACHE
from faculty import load_roster, compatible, split, tokens, dept_in

MIN_PAPERS = 3
ORG = {"iit_kharagpur": re.compile(r"kharagpur", re.I), "iit_roorkee": re.compile(r"roorkee", re.I)}
FACULTY_ROLE = re.compile(r"professor|faculty|lecturer|\bhead\b|\bdean\b", re.I)
NOT_FACULTY = re.compile(r"inspire|ramanujan|fellow|visiting|adjunct|guest|emerit|student|scholar|ph\.?\s*d|post[- ]?doc|research (associate|fellow|"
                         r"assistant|scientist)|project|intern|\bjrf\b|\bsrf\b|teaching assistant|honorary", re.I)
ODIR = os.path.join(CACHE, "orcid")
os.makedirs(ODIR, exist_ok=True)
S = requests.Session()
S.headers.update({"Accept": "application/json", "User-Agent": "DPCN course project (research script)"})


def orcid_record(o):
    fn = os.path.join(ODIR, o + ".json")
    if os.path.exists(fn):
        try:
            return json.load(open(fn, encoding="utf8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass                              # half-written by an interrupted run: fetch again
    rec = None
    for attempt in range(5):
        try:
            r = S.get(f"https://pub.orcid.org/v3.0/{o}/record", timeout=60)
            if r.status_code == 200:
                rec = r.json(); break
            if r.status_code in (404, 410):
                rec = {}; break
        except requests.RequestException:
            pass
        time.sleep(2 + 3 * attempt)
    if rec is None:
        return None                       # transient failure: not cached, retried next run
    json.dump(rec, open(fn, "w", encoding="utf8"))
    time.sleep(0.3)                       # 6 workers x ~2 req/s stays under ORCID's public limit (24 req/s)
    return rec


def record_name(rec):
    n = ((rec.get("person") or {}).get("name") or {})
    given = ((n.get("given-names") or {}).get("value") or "").strip()
    family = ((n.get("family-name") or {}).get("value") or "").strip()
    return (given + " " + family).strip()


def faculty_jobs(rec, inst):
    out = []
    groups = ((rec.get("activities-summary") or {}).get("employments") or {}).get("affiliation-group") or []
    for g in groups:
        for s in g.get("summaries") or []:
            e = s.get("employment-summary") or {}
            org = (e.get("organization") or {}).get("name") or ""
            role = e.get("role-title") or ""
            if not ORG[inst].search(org) or not FACULTY_ROLE.search(role) or NOT_FACULTY.search(role):
                continue
            yr = lambda d: int(((d or {}).get("year") or {}).get("value")) if ((d or {}).get("year") or {}).get("value") else None
            out.append({"organization": org, "department": e.get("department-name"), "role": role,
                        "start": yr(e.get("start-date")), "end": yr(e.get("end-date"))})
    return out


for inst in sys.argv[1:]:
    people = load_roster(inst, supplement=False)        # the original roster only
    by_orcid = {o: p for p in people for o in p["orcids"]}
    by_surname = C.defaultdict(list)
    for p in people:
        t = tokens(p["name"])
        for x in {t[0], t[-1]} if t else ():
            by_surname[x].append(p)
    alt = C.defaultdict(lambda: {"papers": 0, "names": C.Counter(), "rid": None})
    new = C.defaultdict(lambda: {"papers": 0, "names": C.Counter()})
    for line in open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8"):
        s = line.strip().rstrip(",")
        if not s.startswith('{"title"'):
            continue
        r = json.loads(s)
        if r["affiliation_status"] != "verified":
            continue
        for a in (r["authors"] if isinstance(r["authors"], list) else []) + (r.get("authors_openalex") or []):
            o, nm = a.get("orcid"), a.get("name") or ""
            if not o or a.get("institute_author") is not True or o in by_orcid:
                continue
            cands = {p["rid"]: p for p in by_surname.get(split(nm)[0], []) if compatible(nm, p["name"])}
            if len(cands) == 1:
                alt[o]["papers"] += 1; alt[o]["names"][nm] += 1; alt[o]["rid"] = next(iter(cands))
            elif not cands:
                new[o]["papers"] += 1; new[o]["names"][nm] += 1
    todo = list(alt) + [o for o, v in new.items() if v["papers"] >= MIN_PAPERS]
    print(f"{inst}: ORCID records to check: {len(alt)} alt_orcid + {sum(1 for v in new.values() if v['papers'] >= MIN_PAPERS)} new_person", flush=True)
    pid = {p["rid"]: p for p in people}
    with ThreadPoolExecutor(6) as ex:
        records = dict(zip(todo, ex.map(orcid_record, todo)))
    accepted, failed = [], 0
    for k, o in enumerate(todo):
        rec = records[o]
        if rec is None:
            failed += 1; continue
        jobs = faculty_jobs(rec, inst) if rec else []
        if not jobs:
            continue
        name = record_name(rec)
        ev = {"orcid": o, "orcid_name": name, "jobs": jobs, "url": f"https://orcid.org/{o}"}
        if o in alt:
            p = pid[alt[o]["rid"]]
            # the ORCID job's department must not contradict the roster department (e.g. roster 'S. S. Jain' is not
            # ORCID 'Siddharth Jain, Mechanical Engineering'): every stated department has to match it
            depts = [j["department"] for j in jobs if j["department"]]
            if name and compatible(name, p["name"]) and all(dept_in(p["department"], [d]) for d in depts):
                accepted.append(dict(ev, kind="alt_orcid", roster_id=p["rid"], roster_name=p["name"], papers=alt[o]["papers"]))
        else:
            accepted.append(dict(ev, kind="new_person", name=name or new[o]["names"].most_common(1)[0][0],
                                 department=next((j["department"] for j in jobs if j["department"]), None),
                                 start=min((j["start"] for j in jobs if j["start"]), default=None),
                                 end=None if any(j["end"] is None for j in jobs) else max(j["end"] for j in jobs),
                                 papers=new[o]["papers"]))
        if k % 100 == 0:
            print(f"  {inst} {k}/{len(todo)} accepted={len(accepted)}", flush=True)
    json.dump(accepted, open(os.path.join(CACHE, f"roster_supplement_{inst}.json"), "w", encoding="utf8"), indent=1, ensure_ascii=False)
    print(f"{inst}: accepted {C.Counter(a['kind'] for a in accepted)}; ORCID lookups failed (retry later): {failed}", flush=True)

"""Channel B3/B4/B5: faculty-roster-driven person channels.

For every person in WebScrape/rosters/<inst>_faculty.csv:
  B3 Crossref author search (`query.author=<name>`, 2016-2026, top 1000 by relevance) with
     author disambiguation against the person's *seed profile* = affiliation-verified records
     (current WebScrape/<inst>.json) in which an author name-matches the person:
       - candidate author has ORCID: accept iff ORCID belongs to the person (roster or seed ORCIDs);
         reject if the person's ORCID is known and differs.
       - candidate author has deposited affiliation: accept iff it classifies as this IIT.
       - otherwise accept iff >=2 shared co-authors with the seed profile, or 1 shared co-author
         and a shared venue.
       - year >= joining_year (roster) if known, else >= first seed year - 1.
  B4 ORCID works of roster ORCID iDs (works with year >= joining year / first seed year - 1)
  B5 DBLP publications of roster DBLP pids (same year rule)
Raw -> WebScrape/raw/roster/<inst>.jsonl.gz ; consumed by build_candidates.py.

usage: python3 roster_channels.py <inst_key>
"""
import os, re, sys, csv, json, time, unicodedata, collections, threading, queue
import xml.etree.ElementTree as ET
from common import get, RAW, OUT, LOGS, MAILTO, norm_doi, write_jsonl_gz, YEAR_MIN, YEAR_MAX
from affil import classify, IIT as IIT_RX, OTHER_IIT_CITY


def bare_iit(s):
    return bool(IIT_RX.search(s)) and not OTHER_IIT_CITY.search(s)

inst = sys.argv[1]
AMB_T = float(os.environ.get("AMB_T", "2.0"))  # ambiguity threshold (name hits vs. expected own output)
ARXIV = "--arxiv-only" in sys.argv          # B6 runs as a separate, single-threaded, gentle pass
ONLY_ARXIV = ARXIV
LOOSE = "--loose" in sys.argv   # loose pass: profiles also include the person's own previously accepted papers
                                # (snowball). Results feed ONLY the unconfirmed-candidates file.
TITLES = re.compile(r"^(prof\.?|professor|dr\.?|mr\.?|ms\.?|mrs\.?|shri|smt\.?)\s+", re.I)


def asc(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def split_name(n):
    n = asc(n)
    while TITLES.match(n):
        n = TITLES.sub("", n)
    toks = [t for t in re.split(r"[\s.\-]+", n) if t]
    return (toks[:-1], toks[-1]) if len(toks) > 1 else ([], toks[0] if toks else "")


COMMON_SURNAMES = set()  # filled after the verified pool is loaded (data-driven)


def name_match(given_tokens, family, cr_given, cr_family):
    cf = asc(cr_family).replace("-", " ").split()
    cg = [t for t in re.split(r"[\s.\-]+", asc(cr_given)) if t]
    if not cf:
        return False
    if family != cf[-1]:
        # tolerate swapped order (given/family reversed in metadata)
        if not (given_tokens and cg and cf[-1] == given_tokens[0] and family in cg):
            return False
        return True
    if not given_tokens or not cg:
        return False
    a, b = given_tokens[0], cg[0]
    if a[0] != b[0]:
        return False
    # initial-only forms ("N. Kumar") are not accepted for common surnames: audit showed they
    # merge many different people (students, namesakes) into one roster person
    if (len(a) == 1 or len(b) == 1) and family in COMMON_SURNAMES:
        return False
    if len(a) > 1 and len(b) > 1 and not (a.startswith(b) or b.startswith(a)):
        return False
    return True


def gkey(given, family):
    """Co-author identity key. Uses the FULL first given name when available (precision audit showed
    surname+initial keys collide heavily for common surnames such as Das/Ghosh/Mukherjee)."""
    toks = [t for t in re.split(r"[\s.\-]+", asc(given)) if t]
    first = toks[0] if toks else ""
    return f"{asc(family).strip()}_{first if len(first) > 1 else first[:1] + '.'}"


def ckey(au):
    return gkey(au.get("given", ""), au.get("family", ""))


roster = list(csv.DictReader(open(os.path.join(OUT, "rosters", f"{inst}_faculty.csv"))))
cur = json.load(open(os.path.join(OUT, inst + ".json")))["records"]
verified = [r for r in cur if r["affiliation_status"] == "verified" and isinstance(r["authors"], list)]
# snowball (one iteration): a person's own roster-accepted papers from the previous round extend their profile
OWN = collections.defaultdict(list)
for r in cur:
    if isinstance(r["authors"], list) and r["affiliation_status"] != "verified":
        for fp in r.get("found_via_person", []):
            if "[roster:" in fp:
                OWN[fp].append(r)
print(inst, "roster", len(roster), "verified seeds pool", len(verified), flush=True)
# common surnames: family names carried by >= 8 distinct full first names in the verified pool
_fn = collections.defaultdict(set)
for _r in verified:
    for _a in _r["authors"]:
        if _a.get("name") and " " in _a["name"]:
            _g, _f = _a["name"].rsplit(" ", 1)
            _t = [t for t in re.split(r"[\s.\-]+", asc(_g)) if t]
            if _t and len(_t[0]) > 1:
                _fn[asc(_f)].add(_t[0])
COMMON_SURNAMES.update(f for f, gs in _fn.items() if len(gs) >= 8)
print("common surnames:", len(COMMON_SURNAMES), sorted(COMMON_SURNAMES)[:40], flush=True)
# surname index of verified records (speed: avoids scanning all records per person)
BY_FAM = collections.defaultdict(list)
for _r in verified:
    for _a in _r["authors"]:
        _f = asc(_a["name"].rsplit(" ", 1)[-1]) if _a.get("name") else ""
        if _f and (not BY_FAM[_f] or BY_FAM[_f][-1] is not _r):
            BY_FAM[_f].append(_r)

out, log = [], []
arxiv_lock = threading.Lock(); last_arxiv = 0.0
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
lock = threading.Lock()


def jy(p):
    try:
        return int(str(p.get("joining_year") or "")[:4])
    except ValueError:
        return None


def process(p):
    gt, fam = split_name(p["name"])
    if not fam:
        return
    pool = BY_FAM.get(fam, []) + ([r for g in gt[:1] for r in BY_FAM.get(g, [])])  # also swapped order
    person = f"{p['name']} [roster:{p.get('department', '')}]"
    # seeds = affiliation-VERIFIED records only (the round-3 "snowball" from own roster-accepted papers was
    # removed in round 6: it fed namesake errors back into profiles, e.g. 325 -> 424 seeds for one person)
    seeds = (OWN.get(person, []) if LOOSE else []) + [r for r in pool if any(name_match(gt, fam, *(a["name"].rsplit(" ", 1) if " " in a["name"] else ("", a["name"]))) for a in r["authors"])]
    co, venues, orcids, years = collections.Counter(), set(), set(), []
    for r in seeds:
        years.append(r["year"])
        if isinstance(r["venue"], str):
            venues.add(asc(r["venue"]))
        for a in r["authors"]:
            g, f = (a["name"].rsplit(" ", 1) if " " in a["name"] else ("", a["name"]))
            if name_match(gt, fam, g, f):
                if a.get("orcid"):
                    orcids.add(a["orcid"][-19:])
            else:
                co[gkey(g, f)] += 1
    if p.get("orcid"):
        orcids.add(p["orcid"].strip()[-19:])
    start = jy(p) or ((min(years) - 1) if years else None)
    mrange = re.search(r"\((\d{4})\s*-\s*(\d{4})\)", p.get("designation") or "")
    # +1 year publication lag; IIT Roorkee former-faculty end years are lower bounds (archive gaps, see
    # rosters/iit_roorkee_roster_notes.md) -> +4 there
    end = int(mrange.group(2)) + (4 if inst == "iit_roorkee" else 1) if (mrange and p.get("status") == "former") else 9999
    stat = {"name": p["name"], "dept": p.get("department"), "seeds": len(seeds), "orcids": sorted(orcids), "start": start, "end": end if end != 9999 else None,
            "cr_accepted": 0, "orcid_works": 0, "dblp_works": 0}
    person = f"{p['name']} [roster:{p.get('department', '')}]"
    rows = []
    # ---- B3 Crossref author search
    if not ONLY_ARXIV and (start is not None or orcids):
        try:
            items = get("https://api.crossref.org/works", params={"query.author": " ".join(gt + [fam]), "filter": "from-pub-date:2016-01-01,until-pub-date:2026-12-31",
                        "rows": 1000, "select": "DOI,author,title,issued,container-title,type", "mailto": MAILTO}, timeout=300).json()["message"]["items"]
        except Exception as e:
            items = []; stat["error"] = str(e)
        # name ambiguity: Crossref works carrying this exact name vs. the person's expected output
        # (verified seeds / 0.35, since ~35 % of an IIT author's papers carry deposited affiliations)
        name_hits = sum(1 for it in items if any(name_match(gt, fam, a.get("given", ""), a.get("family", "")) for a in it.get("author", [])))
        amb = name_hits / (len(seeds) / 0.35 + 5)
        stat["name_hits"] = name_hits; stat["amb"] = round(amb, 2)
        strict = amb > AMB_T
        for it in items:
            y = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
            if not y or not (YEAR_MIN <= y <= YEAR_MAX) or y > end:
                continue
            auths = it.get("author", [])
            hits = [a for a in auths if name_match(gt, fam, a.get("given", ""), a.get("family", ""))]
            if not hits:
                continue
            a = hits[0]; why = None
            if a.get("ORCID"):
                o = a["ORCID"][-19:]
                if o in orcids:
                    why = "orcid"
                # an ORCID mismatch is NOT a hard reject: people hold duplicate iDs and roster iDs can be
                # name-matched; such candidates must pass the co-author/venue test below instead
            if not why and a.get("affiliation"):
                s = " | ".join(x.get("name", "") for x in a["affiliation"])
                if classify(inst, s) == "iit":
                    why = "affiliation"
                elif not bare_iit(s):
                    continue  # a concrete other institution -> not this person-at-this-IIT
                # bare "Indian Institute of Technology" without city -> ambiguous, fall through
            if not why:
                if start is None or y < start:
                    continue
                shared = sum(1 for b in auths if b is not a and ckey(b) in co)
                vmatch = asc((it.get("container-title") or [""])[0]) in venues
                cg = [t for t in re.split(r"[\s.\-]+", asc(a.get("given", ""))) if t]
                fullname = bool(gt and cg and len(gt[0]) > 2 and cg[0] == gt[0])  # first name spelled out & identical
                if strict:
                    if shared >= 2 and vmatch:
                        why = f"coauthors={shared},venue={vmatch},ambiguous_name"
                elif shared >= 2 or (shared >= 1 and vmatch):
                    why = f"coauthors={shared},venue={vmatch}"
                # (round-2 "fullname" relaxation removed: 0/3 precision in audit)
            if why:
                rows.append({"doi": norm_doi(it["DOI"]), "title": (it.get("title") or [None])[0], "year": y,
                             "channel": "roster_crossref_author_loose" if LOOSE else "roster_crossref_author",
                             "why": why, "person": person})
                stat["cr_accepted"] += 1
    # ---- B4 ORCID works for roster ORCID
    if p.get("orcid") and not ONLY_ARXIV and not LOOSE:
        try:
            r = get(f"https://pub.orcid.org/v3.0/{p['orcid'].strip()[-19:]}/works", headers={"Accept": "application/json"})
            for g in (r.json().get("group") or []) if r.status_code == 200 else []:
                s = g["work-summary"][0]
                try:
                    y = int(s["publication-date"]["year"]["value"])
                except Exception:
                    continue
                if not (YEAR_MIN <= y <= YEAR_MAX) or (start and y < start) or y > end:
                    continue
                ext = {x["external-id-type"]: x["external-id-value"] for x in (g.get("external-ids") or {}).get("external-id", [])}
                rows.append({"doi": norm_doi(ext.get("doi")), "title": ((s.get("title") or {}).get("title") or {}).get("value"), "year": y,
                             "channel": "roster_orcid", "person": person, "orcid_type": s.get("type"),
                             "journal": (s.get("journal-title") or {}).get("value"), "arxiv": ext.get("arxiv")})
                stat["orcid_works"] += 1
        except Exception as e:
            stat["orcid_error"] = str(e)
    # ---- B5 DBLP pid
    pid = (p.get("dblp") or "").strip()
    m = re.search(r"pid/([\w/\-]+?)(\.html)?$", pid)
    if m and not ONLY_ARXIV and not LOOSE:
        try:
            pq = f"""PREFIX dblp: <https://dblp.org/rdf/schema#> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?pub ?title ?year ?doi ?venue ?type WHERE {{ ?pub dblp:authoredBy <https://dblp.org/pid/{m.group(1)}> ; dblp:title ?title ;
            dblp:yearOfPublication ?year ; rdf:type ?type . OPTIONAL {{ ?pub dblp:doi ?doi }} OPTIONAL {{ ?pub dblp:publishedIn ?venue }}
            FILTER(?type != dblp:Publication) }}"""
            r = get("https://sparql.dblp.org/sparql", params={"query": pq}, headers={"Accept": "text/csv"}, timeout=300)
            for x in csv.DictReader(r.text.splitlines()):
                y = int(x["year"][:4])
                if not (YEAR_MIN <= y <= YEAR_MAX) or (start and y < start) or y > end:
                    continue
                rows.append({"doi": norm_doi((x.get("doi") or "").replace("https://doi.org/", "")), "title": x["title"], "year": y,
                             "channel": "roster_dblp", "person": person, "dblp_venue": x.get("venue"), "dblp_type": x["type"].split("#")[-1]})
                stat["dblp_works"] += 1
        except Exception as e:
            stat["dblp_error"] = str(e)
    # ---- B6 arXiv full-name search (arXiv asks for <=1 request / 3 s -> global pacing lock)
    if ARXIV and gt and len(gt[0]) > 1 and start is not None:
        global last_arxiv
        try:
            with arxiv_lock:
                wait = 5.0 - (time.time() - last_arxiv)
                if wait > 0:
                    time.sleep(wait)
                r = get("https://export.arxiv.org/api/query", params={"search_query": f'au:"{" ".join(gt + [fam])}"', "max_results": 300}, timeout=120)
                last_arxiv = time.time()
            for e in ET.fromstring(r.text).findall("a:entry", NS):
                y = int(e.find("a:published", NS).text[:4])
                if not (YEAR_MIN <= y <= YEAR_MAX) or y < start or y > end:
                    continue
                auths = e.findall("a:author", NS)
                names = [a.find("a:name", NS).text for a in auths]
                me = [a for a in auths if name_match(gt, fam, *(a.find("a:name", NS).text.rsplit(" ", 1) if " " in a.find("a:name", NS).text else ("", a.find("a:name", NS).text)))]
                if not me:
                    continue
                affs = " | ".join(x.text or "" for x in me[0].findall("arxiv:affiliation", NS))
                why = "affiliation" if affs and classify(inst, affs) == "iit" else None
                if not why:
                    shared = sum(1 for n in names if " " in n and gkey(n.rsplit(" ", 1)[0], n.rsplit(" ", 1)[1]) in co)
                    if shared >= 1:
                        why = f"coauthors={shared}"
                if why:
                    aid = e.find("a:id", NS).text.rsplit("/abs/", 1)[-1]
                    aid = re.sub(r"v\d+$", "", aid)
                    jd = e.find("arxiv:doi", NS)
                    rows.append({"doi": norm_doi(jd.text) if jd is not None else "10.48550/arxiv." + aid.lower(), "title": " ".join(e.find("a:title", NS).text.split()),
                                 "year": y, "channel": "roster_arxiv", "why": why, "person": person, "arxiv": aid})
                    stat["arxiv_works"] = stat.get("arxiv_works", 0) + 1
        except Exception as ex:
            stat["arxiv_error"] = str(ex)[:100]
    with lock:
        out.extend(rows); log.append(stat)
        if len(log) % 50 == 0:
            print(inst, len(log), "/", len(roster), "rows", len(out), flush=True)


q = queue.Queue(); [q.put(p) for p in roster]


def w():
    while True:
        try:
            p = q.get_nowait()
        except queue.Empty:
            return
        process(p)


ts = [threading.Thread(target=w) for _ in range(1 if ONLY_ARXIV else 6)]
[t.start() for t in ts]; [t.join() for t in ts]
os.makedirs(os.path.join(RAW, "roster"), exist_ok=True)
suffix = "_arxiv" if ONLY_ARXIV else "_loose" if LOOSE else ""
write_jsonl_gz(os.path.join(RAW, "roster", f"{inst}{suffix}.jsonl.gz"), out)
with open(os.path.join(LOGS, f"roster_channels_{inst}{suffix}.tsv"), "w") as f:
    w_ = csv.DictWriter(f, fieldnames=["name", "dept", "seeds", "name_hits", "amb", "orcids", "start", "end", "cr_accepted", "orcid_works", "dblp_works", "arxiv_works", "error", "orcid_error", "dblp_error", "arxiv_error"], delimiter="\t")
    w_.writeheader(); [w_.writerow(s) for s in log]
print("done", len(out))

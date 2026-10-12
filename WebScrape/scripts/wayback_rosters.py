"""Faculty lists per year (2016-2026) from old versions of the institute websites (Internet Archive Wayback Machine).
For every department faculty-list page we take one archived snapshot per year (the one nearest 1 July) and record
which roster people are named on it. Pages are not parsed layout by layout (the sites were redesigned several times):
a person counts as listed in year Y if their name appears in the text of any of their institute's snapshots of year Y.

Pages used
  IIT Kharagpur  www.iitkgp.ac.in/department/<CODE> (one page per department; codes from the roster profile URLs)
  IIT Roorkee    old site (to ~2021): www.iitr.ac.in/departments/<CODE>/pages/People+Faculty.html,
                 .../People+Faculty_List.html, .../people/faculty/<CODE>.htm (found with the Wayback CDX index)
                 new site (2022-): the department faculty pages in the roster's source_url column
Name match (normalised with Enrichment/scripts/faculty.py tokens): surname next to the given names in either order;
given names may be initials ("P. P. Chakrabarti"). An initials-only match is not accepted for surnames shared by 3 or
more roster people (e.g. Kumar, Singh), to avoid crediting the wrong person.
Output: rosters/yearly/<inst>_faculty_by_year.csv (roster_id, name, department, one column per year: 1 named on a
snapshot of that year, 0 not named, blank = no snapshot of the institute's pages that year). A 0 is weak evidence: the
person's department page may simply be missing from the archive that year (see the coverage file)
and rosters/yearly/<inst>_coverage.csv (pages and snapshots per year). Snapshots are cached in raw/wayback/<inst>/.
Online, polite (one request every 3 seconds; the archive throttles faster clients), resumable; a full run takes hours. usage: python wayback_rosters.py iit_kharagpur iit_roorkee"""
import os, re, sys, csv, html, json, time, hashlib, threading, collections as C
import concurrent.futures as cf
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(WEB), "Enrichment", "scripts"))
from faculty import tokens, _consistent                                                      # noqa: E402

YEARS = list(range(2016, 2027))
RAW = os.path.join(WEB, "raw", "wayback")
OUTD = os.path.join(WEB, "rosters", "yearly")
CDX = "https://web.archive.org/cdx/search/cdx"
S = requests.Session()
S.headers["User-Agent"] = "DPCN-course-project (IIIT Hyderabad) yearly faculty lists"
_last = [0.0]
_lock = threading.Lock()
GAP = 3.0                    # seconds between requests: the archive answers 503 when asked faster


def get(url, params=None, tries=6, timeout=120):
    for k in range(tries):
        with _lock:
            wait = GAP - (time.time() - _last[0])
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        try:
            r = S.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(5 * (k + 1))
    return None


def cached_json(name, fn):
    path = os.path.join(RAW, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    v = fn()
    if v is not None:
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(v, fh)
        os.replace(path + ".tmp", path)
    return v


def roster(inst):
    with open(os.path.join(WEB, "rosters", f"{inst}_faculty.csv"), encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def pages(inst, ros):
    """Faculty-list page URLs (without scheme) for one institute."""
    if inst == "iit_kharagpur":
        codes = sorted({m.group(1) for r in ros for m in [re.search(r"/department/([A-Z]{2,3})/", r["profile_url"])] if m})
        return [f"www.iitkgp.ac.in/department/{c}" for c in codes]
    def listing():
        n = int((get(CDX, {"url": "www.iitr.ac.in/departments/", "matchType": "prefix", "showNumPages": "true"}) or
                 type("x", (), {"text": "0"})).text.strip() or 0)
        out = []
        for p in range(n):
            r = get(CDX, {"url": "www.iitr.ac.in/departments/", "matchType": "prefix", "fl": "original",
                          "collapse": "urlkey", "page": p}, timeout=300)
            out += r.text.split() if r else []
        return out
    old = cached_json(f"{inst}_cdx_listing.json", listing) or []
    pat = re.compile(r"/departments/([A-Z]{2,3})/(pages/People[+\-]Faculty(_List)?\.html|people/faculty/\1\.htm)$")
    urls = sorted({re.sub(r"^https?://|:80", "", u) for u in old if pat.search(u)})
    new = sorted({u.strip() for r in ros for u in r["source_url"].split(" ; ") if "web.archive.org" not in u
                  and u.strip().startswith("http")})
    return urls + [re.sub(r"^https?://", "", u.split(" [")[0]) for u in new]


def snapshots(url):
    """year -> timestamp of the 200-status snapshot nearest 1 July of that year."""
    def q():
        r = get(CDX, {"url": url, "fl": "timestamp", "filter": "statuscode:200", "collapse": "timestamp:8",
                      "from": "2016", "to": "2026"})
        return r.text.split() if r else []
    ts = cached_json("cdx_" + hashlib.md5(url.encode()).hexdigest()[:16] + ".json", q) or []
    best = {}
    for t in ts:
        y = int(t[:4])
        d = abs(int(t[4:8]) - 701)
        if y in YEARS and (y not in best or d < best[y][0]):
            best[y] = (d, t)
    return {y: t for y, (d, t) in best.items()}


def page_tokens(url, ts):
    fn = os.path.join(RAW, hashlib.md5(url.encode()).hexdigest()[:16] + f"_{ts}.txt")
    if not os.path.exists(fn):
        r = get(requests.utils.requote_uri(f"https://web.archive.org/web/{ts}id_/http://{url}"))
        if r is None or not re.search(r"(?i)</html\s*>", r.text[-4000:]):      # missing or cut off: try again next run
            return None
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", r.text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        with open(fn, "w", encoding="utf-8") as fh:
            fh.write(" ".join(w for w in re.split(r"[^a-z]+", text.lower().replace(".", " ")) if w))
    with open(fn, encoding="utf-8") as fh:
        return fh.read().split()


def listed(person, toks, index, common):
    t = tokens(person)
    if len(t) < 2:
        return False
    for sur, given in ((t[-1], t[:-1]), (t[0], t[1:])):
        for i in index.get(sur, ()):
            for g in (toks[max(0, i - len(given)):i], toks[i + 1:i + 1 + len(given)]):
                if len(g) == len(given) and _consistent(g, given):
                    full = any(len(a) > 1 and a == b for a, b in zip(g, given))
                    if full or sur not in common:
                        return True
    return False


def run(inst):
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUTD, exist_ok=True)
    ros = roster(inst)
    urls = pages(inst, ros)
    print(inst, len(urls), "faculty-list pages")
    snaps = {u: snapshots(u) for u in urls}
    with cf.ThreadPoolExecutor(1) as ex:                    # download every needed snapshot (cached, resumable)
        list(ex.map(lambda ut: page_tokens(*ut), [(u, t) for u in urls for t in snaps[u].values()]))
    by_year = C.defaultdict(list)                          # year -> token lists of all snapshots that year
    cov = []
    for y in YEARS:
        got = 0
        for u in urls:
            if y in snaps[u]:
                toks = page_tokens(u, snaps[u][y])
                if toks:
                    by_year[y].append(toks)
                    got += 1
        cov.append({"year": y, "pages": len(urls), "snapshots_used": got})
        print(f"  {y}: {got} snapshots")
    surnames = C.Counter(tokens(r["name"])[-1] for r in ros if tokens(r["name"]))
    common = {s for s, n in surnames.items() if n >= 3}
    idx = {y: [(toks, C.defaultdict(list)) for toks in lst] for y, lst in by_year.items()}
    for y in idx:
        for toks, ix in idx[y]:
            for i, w in enumerate(toks):
                ix[w].append(i)
    rows = []
    for k, r in enumerate(ros):
        row = {"roster_id": f"{inst}:{k}", "name": r["name"], "department": r["department"], "status": r["status"]}
        for y in YEARS:
            row[str(y)] = "" if not idx.get(y) else int(any(listed(r["name"], toks, ix, common) for toks, ix in idx[y]))
        rows.append(row)
    for name, data in ((f"{inst}_faculty_by_year.csv", rows), (f"{inst}_coverage.csv", cov)):
        with open(os.path.join(OUTD, name), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)
    print(inst, "listed per year:", {y: sum(1 for r in rows if r[str(y)] == 1) for y in YEARS})


if __name__ == "__main__":
    for inst in sys.argv[1:]:
        run(inst)

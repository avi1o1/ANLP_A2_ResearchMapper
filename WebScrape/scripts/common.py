"""Shared helpers for the publication scrape (HTTP session with retry/back-off, paths)."""
import gzip, json, os, time, random
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = ROOT  # WebScrape/: datasets, rosters/, golden/; run-time raw/ and logs/ are created here
RAW = os.path.join(OUT, "raw")
LOGS = os.path.join(OUT, "logs")
MAILTO = "aviral.gupta@research.iiit.ac.in"  # Crossref "polite pool" etiquette
UA = f"DPCN-ResearchMapper/1.0 (mailto:{MAILTO})"
YEAR_MIN, YEAR_MAX = 2016, 2026
os.makedirs(RAW, exist_ok=True)   # run-time caches (git-ignored)
os.makedirs(LOGS, exist_ok=True)  # run-time logs (git-ignored)

INSTITUTES = {
    "iit_ropar": {"name": "Indian Institute of Technology Ropar", "ror": "https://ror.org/02qkhhn56"},
    "iit_kharagpur": {"name": "Indian Institute of Technology Kharagpur", "ror": "https://ror.org/03w5sq511"},
    "iit_roorkee": {"name": "Indian Institute of Technology Roorkee", "ror": "https://ror.org/00582g326"},
}

_session = requests.Session()
_session.headers["User-Agent"] = UA


def get(url, params=None, tries=8, timeout=120, **kw):
    """GET with exponential back-off on 429/5xx/network errors. Returns Response or raises."""
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
            wait = float(r.headers.get("Retry-After", 0) or 0) or min(120, 2 ** i + random.random())
        except requests.RequestException:
            wait = min(120, 2 ** i + random.random())
        time.sleep(wait)
    raise RuntimeError(f"GET failed after {tries} tries: {url} {params}")


def post(url, json_body=None, params=None, tries=8, timeout=120, **kw):
    for i in range(tries):
        try:
            r = _session.post(url, json=json_body, params=params, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            wait = float(r.headers.get("Retry-After", 0) or 0) or min(120, 2 ** i + random.random())
        except requests.RequestException:
            wait = min(120, 2 ** i + random.random())
        time.sleep(wait)
    raise RuntimeError(f"POST failed after {tries} tries: {url}")


def write_jsonl_gz(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl_gz(path):
    """Yield JSON rows; stops quietly at a truncated/partially-written tail (shards may be appended
    to by a concurrent run). Use check_shards.py to verify caches are fully readable."""
    import zlib
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    return
    except (EOFError, zlib.error, OSError):
        return


DOI_RX = __import__("re").compile(r"10\.\d{4,9}/[^\s\"<>]+", __import__("re").I)


def norm_doi(d):
    """Extract and lowercase the DOI from strings such as 'doi 10.1/x', 'https://doi.org/10.1/x',
    'doi.org/10.1/x'. Returns None if no DOI pattern is present (e.g. '1-25', 'volumes/112/07')."""
    if not d:
        return None
    m = DOI_RX.search(d.strip())
    if not m:
        return None
    d = m.group(0).lower().rstrip(".,;)")
    # URL-style suffixes copied from publisher pages are not part of the DOI (e.g. IOP ".../meta")
    return __import__("re").sub(r"/(meta|full|abstract|pdf|epdf|fulltext|full/html|html)$", "", d)

"""Shared paths and OpenAlex helpers: key loading, a polite GET with retries, and credit logging.
API key: only needed by the online steps. Give it as the environment variable OPENALEX_API_KEY, or put it in a file
and set OPENALEX_KEY_FILE to that file's path. Never commit a key (.gitignore blocks .openalex_key* and .env)."""
import os, time, json, requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                        # Enrichment/
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "WebScrape")              # input: the scraped datasets (iit_<inst>.json)
CACHE = os.path.join(ROOT, "cache")
OUT = os.path.join(ROOT, "out")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

BASE = "https://api.openalex.org"
_key = []


def api_key():
    """The OpenAlex key, read on first use (offline steps never need it)."""
    if not _key:
        k = os.environ.get("OPENALEX_API_KEY")
        if not k:
            fn = os.environ.get("OPENALEX_KEY_FILE") or os.path.join(ROOT, ".openalex_key")
            if not os.path.exists(fn):
                raise SystemExit("OpenAlex key missing: set OPENALEX_API_KEY or OPENALEX_KEY_FILE (see oa.py)")
            k = open(fn).read().strip()
        _key.append(k)
    return _key[0]
INST = {
    "iit_kharagpur": {"oa": "I145894827", "ror": "https://ror.org/03w5sq511", "name": "IIT Kharagpur"},
    "iit_roorkee": {"oa": "I154851008", "ror": "https://ror.org/00582g326", "name": "IIT Roorkee"},
}

S = requests.Session()
_last = [0.0]
credits = {"used": 0, "remaining": None}


def get(path, params=None, tries=8):
    """GET an OpenAlex endpoint; returns parsed JSON, or None for a 404."""
    params = dict(params or {}, api_key=api_key())
    for attempt in range(tries):
        wait = 0.12 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = S.get(BASE + path, params=params, timeout=90)
        except requests.RequestException:
            time.sleep(2 + 3 * attempt)
            continue
        if r.headers.get("X-RateLimit-Remaining"):
            credits["remaining"] = int(r.headers["X-RateLimit-Remaining"])
        if r.status_code == 200:
            credits["used"] += 1
            return r.json()
        if r.status_code == 404:
            credits["used"] += 1
            return None
        if r.status_code == 429:
            if credits["remaining"] is not None and credits["remaining"] <= 0:
                raise SystemExit("OpenAlex daily credit budget exhausted - resume after reset")
            time.sleep(5 + 10 * attempt)
            continue
        time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"OpenAlex request failed after {tries} tries: {path} {params.get('filter', '')[:120]}")


def norm_doi(d):
    if not isinstance(d, str):
        return None
    d = d.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d if d.startswith("10.") else None


def load_records(inst):
    return json.load(open(os.path.join(DATA, inst + ".json"), encoding="utf8"))["records"]


def read_jsonl(fn):
    out = []
    if os.path.exists(fn):
        with open(fn, encoding="utf8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # tolerate a truncated last line after an interruption
    return out


SELECT = ("id,doi,title,publication_year,type,primary_location,authorships,referenced_works,"
          "referenced_works_count,cited_by_count,primary_topic,topics,ids")

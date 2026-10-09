"""Channel A1: Crossref affiliation-token harvest.

For each search token we page through `query.affiliation=<token>` (cursor paging) restricted to
publication dates 2016-01-01..2026-12-31 and store every returned record verbatim in
WebScrape/raw/crossref_aff/<token>.jsonl.gz. Relevance filtering happens later (classify step),
so this stage is deliberately over-inclusive.

usage: python3 crossref_aff.py <token> [--light]
  --light : only fetch DOI/author/title/type/issued (used for very broad sweeps like "West Bengal")
"""
import os, sys, json, gzip
from common import get, RAW, MAILTO, LOGS

token = sys.argv[1]
light = "--light" in sys.argv
outdir = os.path.join(RAW, "crossref_aff")
os.makedirs(outdir, exist_ok=True)
fn = os.path.join(outdir, token.replace(" ", "_") + (".light" if light else "") + ".jsonl.gz")
params = {"query.affiliation": token, "filter": "from-pub-date:2016-01-01,until-pub-date:2026-12-31",
          "rows": 1000 if light else 500, "cursor": "*", "mailto": MAILTO}
if light:
    params["select"] = "DOI,author,title,type,issued"
n = 0
with gzip.open(fn + ".part", "wt", encoding="utf-8") as f:
    while True:
        m = get("https://api.crossref.org/works", params=params, timeout=300).json()["message"]
        items = m["items"]
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
        n += len(items)
        print(f"[{token}] {n}/{m['total-results']}", flush=True)
        if not items or len(items) < params["rows"]:
            break
        params["cursor"] = m["next-cursor"]
os.replace(fn + ".part", fn)
with open(os.path.join(LOGS, "crossref_aff_runs.tsv"), "a") as lg:
    lg.write(f"{token}\t{'light' if light else 'full'}\t{n}\t{m['total-results']}\n")

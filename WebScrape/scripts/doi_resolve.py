"""Step M2: find DOIs for DOI-less candidates via Crossref bibliographic search.
Accept only if the normalized title matches exactly and |year diff| <= 1.
Writes WebScrape/raw/doi_resolved_<inst>.tsv (key, doi) which build_candidates.py applies.

usage: python3 doi_resolve.py <inst_key>
"""
import os, re, sys, unicodedata, threading, queue, html
from common import read_jsonl_gz, get, RAW, MAILTO, norm_doi

inst = sys.argv[1]


def tk(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


outfn = os.path.join(RAW, f"doi_resolved_{inst}.tsv")
done = set()
if os.path.exists(outfn):
    done = {l.split("\t")[0] for l in open(outfn)}
todo = [c for c in read_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz")) if not c["doi"] and c["title"] and c["key"] not in done]
print("to resolve", len(todo), flush=True)
q = queue.Queue(); [q.put(c) for c in todo]
lock = threading.Lock(); out = open(outfn, "a"); n = [0, 0]


def w():
    while True:
        try:
            c = q.get_nowait()
        except queue.Empty:
            return
        doi = ""
        try:
            items = get("https://api.crossref.org/works", params={"query.bibliographic": c["title"], "rows": 5, "mailto": MAILTO,
                                                                    "select": "DOI,title,issued,type"}).json()["message"]["items"]
            for it in items:
                y = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
                if tk((it.get("title") or [""])[0]) == tk(c["title"]) and y and abs(y - c["year"]) <= 1:
                    doi = norm_doi(it["DOI"]); break
        except Exception as e:
            doi = ""
        with lock:
            out.write(f"{c['key']}\t{doi}\n"); out.flush()
            n[0] += 1; n[1] += bool(doi)
            if n[0] % 100 == 0:
                print(n, flush=True)


ts = [threading.Thread(target=w) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
print("resolved", n)

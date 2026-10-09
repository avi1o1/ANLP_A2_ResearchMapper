"""Enrichment E3: OpenCitations Index v2 fallback for DOIs whose reference list is not in Crossref
(and citation count as a cross-check). Cache: WebScrape/raw/opencitations/oc.jsonl

usage: python3 opencitations.py <inst_key>   (processes records of WebScrape/<inst>.json with references == TODO and a DOI)
"""
import os, sys, json, gzip, glob, re, threading, queue
from common import get, RAW, OUT, read_jsonl_gz, norm_doi

inst = sys.argv[1]
D = os.path.join(RAW, "opencitations"); os.makedirs(D, exist_ok=True)
FN = os.path.join(D, "oc.jsonl")  # plain JSONL (append-safe if interrupted)
have = set()
if os.path.exists(FN):
    for _l in open(FN):
        try:
            have.add(json.loads(_l)["doi"])
        except Exception:
            pass
recs = json.load(open(os.path.join(OUT, inst + ".json")))["records"]
todo = sorted({norm_doi(r["doi"]) for r in recs if r["doi"] != "TODO" and r["references"] == "TODO"} - have)
print("opencitations todo", len(todo), flush=True)
q = queue.Queue(); [q.put(x) for x in todo]
lock = threading.Lock(); f = open(FN, "a")
DOI_RX = re.compile(r"doi:(\S+)")


def w():
    while True:
        try:
            d = q.get_nowait()
        except queue.Empty:
            return
        row = {"doi": d}
        try:
            r = get(f"https://api.opencitations.net/index/v2/references/doi:{d}", timeout=120)
            if r.status_code == 200:
                refs = set()
                for x in r.json():
                    m = DOI_RX.search(x.get("cited", ""))
                    if m:
                        refs.add(norm_doi(m.group(1)))
                row["references"] = sorted(refs) if refs else None
            r = get(f"https://api.opencitations.net/index/v2/citation-count/doi:{d}", timeout=120)
            if r.status_code == 200 and r.json():
                row["citation_count"] = int(r.json()[0]["count"])
        except Exception as e:
            row["error"] = str(e)
        with lock:
            f.write(json.dumps(row) + "\n"); f.flush()


ts = [threading.Thread(target=w) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
f.close(); print("done")

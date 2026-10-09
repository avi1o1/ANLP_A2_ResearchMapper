"""Enrichment E1: fetch full Crossref metadata for a list of DOIs (batched `filter=doi:a,doi:b,...`).
Cache: WebScrape/raw/crossref_full/records.jsonl.gz (append-only shards), resumable.

usage: python3 crossref_enrich.py <file_with_one_doi_per_line>
"""
import os, sys, json, gzip, glob, threading, queue
from common import get, RAW, MAILTO, norm_doi

D = os.path.join(RAW, "crossref_full"); os.makedirs(D, exist_ok=True)
have = set()
for fn in glob.glob(os.path.join(D, "*.jsonl.gz")):
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                r = json.loads(line)
                # skip only DOIs Crossref itself answered (found, or Crossref-missing). A DataCite "missing"
                # row must NOT block a Crossref retry (bug found in the confirmatory check: DOIs from a
                # failed Crossref batch were later marked missing by DataCite and never retried).
                if r.get("_src") == "datacite" and r.get("_missing"):
                    continue
                have.add(r["_q"])
    except EOFError:
        pass
todo = [d for d in (norm_doi(x) for x in open(sys.argv[1])) if d and d not in have and "," not in d]
todo = sorted(set(todo))
print("cached", len(have), "todo", len(todo), flush=True)
B = 40
q = queue.Queue()
for i in range(0, len(todo), B):
    q.put(todo[i:i + B])
lock = threading.Lock(); done = [0]


def worker(k):
    fn = os.path.join(D, f"shard_{os.getpid()}_{k}.jsonl.gz")
    with gzip.open(fn, "at") as f:
        while True:
            try:
                batch = q.get_nowait()
            except queue.Empty:
                return
            r = get("https://api.crossref.org/works",
                    params={"filter": ",".join("doi:" + d for d in batch), "rows": B, "mailto": MAILTO}, timeout=180)
            got = {}
            for it in r.json()["message"]["items"]:
                got[norm_doi(it["DOI"])] = it
            for d in batch:
                rec = got.get(d) or {"_missing": True}
                rec["_q"] = d
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            with lock:
                done[0] += len(batch)
                if done[0] % 2000 < B:
                    print("enriched", done[0], "/", len(todo), flush=True)


ts = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
print("finished", done[0])

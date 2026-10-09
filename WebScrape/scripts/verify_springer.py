"""Verification channel V1: Springer landing-page citation meta tags (per-author institutions).
Only for not-yet-verified records whose DOI belongs to Springer/Nature/BMC (prefixes 10.1007, 10.1186,
10.1038, 10.1140, 10.1134). Honest User-Agent, paths allowed by link.springer.com/robots.txt
(/10*), 3 workers, each <=1 request/second. No challenge is solved or bypassed: a challenge page is
recorded as 'blocked'. Cache: WebScrape/raw/landing/springer.jsonl  {doi, status, authors:[{name, institutions}]}

usage: python3 verify_springer.py <inst_key> [<inst_key> ...]
"""
import os, sys, json, gzip, re, time, html
import requests
from common import RAW, OUT, read_jsonl_gz, norm_doi, MAILTO

PFX = ("10.1007/", "10.1186/", "10.1038/", "10.1140/", "10.1134/")
D = os.path.join(RAW, "landing"); os.makedirs(D, exist_ok=True)
fn = os.path.join(D, "springer.jsonl")  # plain JSONL: append-safe if the process is interrupted
have = set()
if os.path.exists(fn):
    for _l in open(fn):
        try:
            have.add(json.loads(_l)["doi"])
        except Exception:
            pass
todo = []
for inst in sys.argv[1:]:
    for f in (inst + ".json", f"candidates_unconfirmed_{inst}.json"):
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            for r in json.load(open(p))["records"]:
                d = norm_doi(r["doi"]) if r["doi"] != "TODO" else None
                if d and d.startswith(PFX) and r["affiliation_status"] != "verified" and d not in have:
                    todo.append(d)
todo = sorted(set(todo))
print("springer todo", len(todo), flush=True)
S = requests.Session(); S.headers["User-Agent"] = f"DPCN-ResearchMapper/1.0 (academic bibliometrics; mailto:{MAILTO})"
META = re.compile(r'<meta name="(citation_author|citation_author_institution)" content="([^"]*)"')
import threading, queue
out = open(fn, "a"); lock = threading.Lock(); q = queue.Queue(); [q.put(d) for d in todo]; n = [0]


def worker():
    S = requests.Session(); S.headers["User-Agent"] = f"DPCN-ResearchMapper/1.0 (academic bibliometrics; mailto:{MAILTO})"
    while True:
        try:
            d = q.get_nowait()
        except queue.Empty:
            return
        row = {"doi": d}
        try:
            r = S.get(f"https://link.springer.com/{d}", timeout=60)
            if r.status_code == 200 and "citation_author" in r.text:
                authors = []
                for k, v in META.findall(r.text):
                    v = html.unescape(v)
                    if k == "citation_author":
                        authors.append({"name": v, "institutions": []})
                    elif authors:
                        authors[-1]["institutions"].append(v)
                row.update(status="ok", authors=authors)
            elif r.status_code == 200 and "Client Challenge" in r.text:
                row["status"] = "blocked"
            else:
                row["status"] = f"http_{r.status_code}"
        except Exception as e:
            row["status"] = "error:" + str(e)[:80]
        with lock:
            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush(); n[0] += 1
            if n[0] % 250 == 0:
                print(n[0], "/", len(todo), row["status"], flush=True)
        time.sleep(30 if row.get("status") == "blocked" else 1.0)  # politeness: <=1 req/s per worker, 3 workers


ts = [threading.Thread(target=worker) for _ in range(3)]
[t.start() for t in ts]; [t.join() for t in ts]
out.close(); print("done")

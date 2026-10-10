"""Stage A: fetch the OpenAlex work for every DOI in the dataset (100 DOIs per request).
Resumable: queried DOIs are logged in cache/a_queried_<inst>.txt, works in cache/a_works_<inst>.jsonl.
usage: python stage_a_fetch.py <inst_key> [...]"""
import os, sys, json, urllib.parse
from oa import get, norm_doi, load_records, read_jsonl, CACHE, credits, SELECT

for inst in sys.argv[1:]:
    dois = sorted({norm_doi(r["doi"]) for r in load_records(inst)} - {None})
    qfn = os.path.join(CACHE, f"a_queried_{inst}.txt")
    wfn = os.path.join(CACHE, f"a_works_{inst}.jsonl")
    done = set(open(qfn, encoding="utf8").read().split("\n")) if os.path.exists(qfn) else set()
    todo = [d for d in dois if d not in done]
    # characters that break OpenAlex filter syntax -> fetched one by one via the singleton endpoint
    batchable = [d for d in todo if not any(c in d for c in ",|+&")]
    single = [d for d in todo if d not in set(batchable)]
    print(f"{inst}: {len(dois)} DOIs, {len(todo)} to query ({len(single)} singly)", flush=True)
    wf = open(wfn, "a", encoding="utf8")
    qf = open(qfn, "a", encoding="utf8")
    for i in range(0, len(batchable), 100):
        b = batchable[i:i + 100]
        j = get("/works", {"filter": "doi:" + "|".join(b), "per-page": 100, "select": SELECT})
        for w in j["results"]:
            wf.write(json.dumps(w, ensure_ascii=False) + "\n")
        wf.flush()
        qf.write("\n".join(b) + "\n"); qf.flush()
        if (i // 100) % 25 == 0:
            print(f"  {inst} {i + len(b)}/{len(batchable)} credits_used={credits['used']} remaining={credits['remaining']}", flush=True)
    for d in single:
        w = get("/works/" + urllib.parse.quote("https://doi.org/" + d, safe=":/"), {"select": SELECT})
        if w:
            wf.write(json.dumps(w, ensure_ascii=False) + "\n")
        qf.write(d + "\n"); qf.flush()
    wf.close(); qf.close()
    got = {norm_doi(w.get("doi")) for w in read_jsonl(wfn)}
    print(f"{inst}: OpenAlex works found for {len(got & set(dois))}/{len(dois)} DOIs; credits_used={credits['used']} remaining={credits['remaining']}", flush=True)

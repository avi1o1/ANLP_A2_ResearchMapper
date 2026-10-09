"""Verification channel V2: Europe PMC lookup BY DOI (batched OR queries) for not-yet-verified records,
retrieving per-author affiliations (resultType=core). Cache: WebScrape/raw/landing/epmc_doi.jsonl.gz
{doi, authors:[{name, institutions}]} ; DOIs not in Europe PMC are recorded with status 'absent'.
usage: python3 verify_epmc.py <inst_key> [...]"""
import os, sys, json, gzip
from common import RAW, OUT, read_jsonl_gz, norm_doi, get

D = os.path.join(RAW, "landing"); os.makedirs(D, exist_ok=True)
fn = os.path.join(D, "epmc_doi.jsonl.gz")
have = {r["doi"] for r in read_jsonl_gz(fn)} if os.path.exists(fn) else set()
todo = set()
for inst in sys.argv[1:]:
    for f in (inst + ".json", f"candidates_unconfirmed_{inst}.json"):
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            for r in json.load(open(p))["records"]:
                d = norm_doi(r["doi"]) if r["doi"] != "TODO" else None
                if d and r["affiliation_status"] != "verified" and d not in have and not d.startswith("10.48550/") and '"' not in d:
                    todo.add(d)
todo = sorted(todo); print("epmc todo", len(todo), flush=True)
out = gzip.open(fn, "at")
B = 40
for i in range(0, len(todo), B):
    batch = todo[i:i + B]
    q = " OR ".join(f'DOI:"{d}"' for d in batch)
    try:
        res = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                  params={"query": q, "format": "json", "resultType": "core", "pageSize": 100}, timeout=120).json()
        found = {}
        for r in res.get("resultList", {}).get("result", []):
            d = norm_doi(r.get("doi"))
            if not d:
                continue
            au = [{"name": a.get("fullName"), "institutions": [x.get("affiliation", "") for x in
                   (a.get("authorAffiliationDetailsList") or {}).get("authorAffiliation", [])]}
                  for a in (r.get("authorList") or {}).get("author", [])]
            found[d] = au
        for d in batch:
            out.write(json.dumps({"doi": d, "status": "ok" if d in found else "absent", "authors": found.get(d, [])}) + "\n")
        out.flush()
    except Exception as e:
        print("batch error", e, flush=True)
    if (i // B) % 50 == 0:
        print(i, "/", len(todo), flush=True)
out.close(); print("done")

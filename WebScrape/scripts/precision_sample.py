"""Draw a seeded stratified random sample per affiliation tier for manual precision audit.
usage: python3 precision_sample.py <inst_key>  -> WebScrape/golden/precision_sample_<inst>.csv"""
import os, sys, csv, json, random
from common import OUT
inst = sys.argv[1]
recs = json.load(open(os.path.join(OUT, inst + ".json")))["records"]
tiers = {"verified": [], "likely": [], "possible": [], "ambiguous": []}
for r in recs:
    s = r["affiliation_status"]
    k = "verified" if s == "verified" else "likely" if "likely" in s else "possible" if "possible" in s else "ambiguous"
    tiers[k].append(r)
N = {"verified": 25, "likely": 40, "possible": 40, "ambiguous": 0}
rnd = random.Random(20261007)
rows = []
for k, lst in tiers.items():
    for r in rnd.sample(lst, min(N[k], len(lst))):
        rows.append({"tier": k, "record_id": r["record_id"], "doi": r["doi"], "year": r["year"], "title": r["title"], "venue": r["venue"],
                     "found_via_person": "; ".join(r["found_via_person"]), "evidence": ",".join(r["evidence"]),
                     "verdict": "", "evidence_url": "", "notes": ""})
fn = os.path.join(OUT, "golden", f"precision_sample_{inst}.csv")
with open(fn, "w") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(fn, {k: len(v) for k, v in tiers.items()})

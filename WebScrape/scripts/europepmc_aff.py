"""Channel A2: Europe PMC affiliation search (resultType=core: full author affiliations, DOI,
journal ISSN, citedByCount). Raw records -> WebScrape/raw/europepmc/<inst>.jsonl.gz

usage: python3 europepmc_aff.py <inst_key>
"""
import os, sys
from common import get, RAW, LOGS, write_jsonl_gz

QUERIES = {
    "iit_ropar": '(AFF:"Ropar" OR AFF:"Rupnagar" OR AFF:"Roopnagar" OR AFF:"140001") AND PUB_YEAR:[2016 TO 2026]',
    "iit_roorkee": '(AFF:"Roorkee" OR AFF:"247667" OR AFF:"Roorke" OR AFF:"Rorkee" OR AFF:"IIT Roorkee" OR AFF:"iitr.ac.in" OR (AFF:"Saharanpur" AND AFF:"Indian Institute of Technology")) AND PUB_YEAR:[2016 TO 2026]',
    "iit_kharagpur": '(AFF:"Kharagpur" OR AFF:"721302" OR AFF:"IIT KGP" OR AFF:"IITKGP" OR AFF:"Khargpur" '
                     'OR AFF:"Kharagapur" OR AFF:"Kharagur" OR AFF:"Kharapur" OR AFF:"Khragpur" OR AFF:"Karagpur") '
                     'AND PUB_YEAR:[2016 TO 2026]',
}
inst = sys.argv[1]
os.makedirs(os.path.join(RAW, "europepmc"), exist_ok=True)
params = {"query": QUERIES[inst], "format": "json", "resultType": "core", "pageSize": 1000, "cursorMark": "*"}
rows = []
while True:
    d = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params=params, timeout=300).json()
    res = d.get("resultList", {}).get("result", [])
    rows += res
    print(inst, len(rows), "/", d["hitCount"], flush=True)
    if not res or d.get("nextCursorMark") in (None, params["cursorMark"]):
        break
    params["cursorMark"] = d["nextCursorMark"]
write_jsonl_gz(os.path.join(RAW, "europepmc", inst + ".jsonl.gz"), rows)
with open(os.path.join(LOGS, "europepmc_runs.tsv"), "a") as lg:
    lg.write(f"{inst}\t{QUERIES[inst]}\t{len(rows)}\t{d['hitCount']}\n")

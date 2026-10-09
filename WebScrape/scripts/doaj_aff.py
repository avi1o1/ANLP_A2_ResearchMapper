"""Channel A3: DOAJ article search on author affiliation. Raw -> WebScrape/raw/doaj/<inst>.jsonl.gz
usage: python3 doaj_aff.py <inst_key>"""
import os, sys, urllib.parse
from common import get, RAW, LOGS, write_jsonl_gz

TERMS = {
    "iit_ropar": ["Ropar", "Rupnagar", "Roopnagar", "140001"],
    "iit_roorkee": ["Roorkee", "247667", "Roorke", "Rorkee", "Saharanpur", "247001"],
    "iit_kharagpur": ["Kharagpur", "721302", "IITKGP", "Khargpur", "Kharagapur", "Kharagur", "Kharapur", "Khragpur", "Karagpur"],
}
inst = sys.argv[1]
os.makedirs(os.path.join(RAW, "doaj"), exist_ok=True)
seen, rows = set(), []
for t in TERMS[inst]:
    # DOAJ caps deep paging at 10k; split by year to stay under it.
    for y in range(2016, 2027):
        q = f'bibjson.author.affiliation:"{t}" AND bibjson.year:{y}'
        page = 1
        while True:
            url = "https://doaj.org/api/search/articles/" + urllib.parse.quote(q)
            d = get(url, params={"page": page, "pageSize": 100}).json()
            res = d.get("results", [])
            for r in res:
                if r["id"] not in seen:
                    seen.add(r["id"]); r["_query"] = q; rows.append(r)
            if page * 100 >= d.get("total", 0) or not res:
                break
            page += 1
        print(inst, t, y, d.get("total"), "cum", len(rows), flush=True)
write_jsonl_gz(os.path.join(RAW, "doaj", inst + ".jsonl.gz"), rows)
with open(os.path.join(LOGS, "doaj_runs.tsv"), "a") as lg:
    lg.write(f"{inst}\t{TERMS[inst]}\t{len(rows)}\n")

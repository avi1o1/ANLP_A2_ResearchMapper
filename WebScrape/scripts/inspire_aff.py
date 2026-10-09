"""Channel A4: INSPIRE-HEP (high-energy/nuclear/astro physics) by normalised institution name.
Every INSPIRE author affiliation is curated, so a hit is affiliation evidence.
Raw -> WebScrape/raw/inspire/<inst>.jsonl.gz      usage: python3 inspire_aff.py <inst_key>"""
import os, sys
from common import get, RAW, LOGS, write_jsonl_gz
Q = {"iit_ropar": 'aff:"Indian Inst. Tech., Ropar"', "iit_kharagpur": 'aff:"Indian Inst. Tech., Kharagpur"',
     "iit_roorkee": 'aff:"IIT, Roorkee"'}
inst = sys.argv[1]; rows = []; page = 1
F = "titles,dois,arxiv_eprints,publication_info,authors.full_name,authors.affiliations,document_type,earliest_date,citation_count"
while True:
    d = get("https://inspirehep.net/api/literature", params={"q": Q[inst] + " and de > 2015", "size": 250, "page": page, "fields": F}).json()
    hits = d["hits"]["hits"]; rows += [h["metadata"] for h in hits]
    print(inst, len(rows), "/", d["hits"]["total"], flush=True)
    if len(rows) >= d["hits"]["total"] or not hits:
        break
    page += 1
os.makedirs(os.path.join(RAW, "inspire"), exist_ok=True)
write_jsonl_gz(os.path.join(RAW, "inspire", inst + ".jsonl.gz"), rows)
open(os.path.join(LOGS, "inspire_runs.tsv"), "a").write(f"{inst}\t{Q[inst]}\t{len(rows)}\n")

"""Channel B2: DBLP (CS) person channel via the public SPARQL endpoint (website is bot-walled).

Persons whose DBLP affiliation string matches the institute (word-boundary regex, IIT check),
plus all their publications 2016-2026 (title, year, venue, DOI, type).
DBLP affiliations are *current* (undated), so these works are candidates that must be
verified/flagged in the merge step. Raw -> WebScrape/raw/dblp/<inst>.jsonl.gz

usage: python3 dblp_people.py <inst_key>
"""
import os, re, sys, csv, io, json
from common import get, RAW, LOGS, write_jsonl_gz

CFG = {"iit_ropar": ("ropar|rupnagar", re.compile(r"\b(ropar|rupnagar|roopnagar)\b", re.I)),
       "iit_roorkee": ("roorkee|roorke|rorkee", re.compile(r"\b(roorkee|roorke|rorkee)\b", re.I)),
       "iit_kharagpur": ("kharagpur|kgp|kharagapur|khragpur", re.compile(r"\b(kharagpur|kharagapur|khragpur|kgp)\b", re.I))}
IIT = re.compile(r"\biit\b|indian institute of technology|iitkgp|iit-?kgp", re.I)
inst = sys.argv[1]; rx_s, rx = CFG[inst]
EP = "https://sparql.dblp.org/sparql"


def sparql(q):
    r = get(EP, params={"query": q}, headers={"Accept": "text/csv"}, timeout=300)
    return list(csv.DictReader(io.StringIO(r.text)))


PFX = "PREFIX dblp: <https://dblp.org/rdf/schema#>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
people = sparql(PFX + f"""SELECT ?p ?name ?aff WHERE {{ ?p a dblp:Person ; dblp:primaryCreatorName ?name ; dblp:affiliation ?aff .
  FILTER(REGEX(STR(?aff), "{rx_s}", "i")) }}""")
persons = {}
for r in people:
    if rx.search(r["aff"]) and IIT.search(r["aff"]):
        persons.setdefault(r["p"], {"pid": r["p"], "name": r["name"], "affs": []})["affs"].append(r["aff"])
print(inst, "persons", len(persons), flush=True)
rows = []
plist = list(persons)
for i in range(0, len(plist), 40):
    vals = " ".join(f"<{p}>" for p in plist[i:i + 40])
    res = sparql(PFX + f"""SELECT ?p ?pub ?title ?year ?doi ?venue ?type WHERE {{
      VALUES ?p {{ {vals} }} ?pub dblp:authoredBy ?p ; dblp:title ?title ; dblp:yearOfPublication ?year ; rdf:type ?type .
      FILTER(?year >= "2016"^^<http://www.w3.org/2001/XMLSchema#gYear> && ?year <= "2026"^^<http://www.w3.org/2001/XMLSchema#gYear>)
      OPTIONAL {{ ?pub dblp:doi ?doi }} OPTIONAL {{ ?pub dblp:publishedIn ?venue }}
      FILTER(?type != dblp:Publication) }}""")
    for r in res:
        r["person_name"] = persons[r["p"]]["name"]; r["person_affs"] = persons[r["p"]]["affs"]
        rows.append(r)
    print(inst, i + 40, "/", len(plist), "rows", len(rows), flush=True)
os.makedirs(os.path.join(RAW, "dblp"), exist_ok=True)
write_jsonl_gz(os.path.join(RAW, "dblp", inst + ".jsonl.gz"), rows)
write_jsonl_gz(os.path.join(RAW, "dblp", inst + "_persons.jsonl.gz"), persons.values())
with open(os.path.join(LOGS, "dblp_runs.tsv"), "a") as lg:
    lg.write(f"{inst}\tpersons={len(persons)}\tpub_rows={len(rows)}\n")

"""Check how far OpenAlex affiliation evidence can be trusted, before using it to change any record.
 1. Hand-labelled audit samples (golden/precision_audit_<inst>.csv, verdict yes/no/unknown) vs OpenAlex verdict.
 2. Records already verified from Crossref/Europe PMC text: how often does OpenAlex agree?
usage: python eval_affiliation.py <inst_key> [...]"""
import os, sys, csv, collections as C
from oa import load_records, read_jsonl, norm_doi, CACHE, INST, REPO
from oa_extract import facts

REPO_GOLDEN = os.path.join(REPO, "WebScrape", "golden")

for inst in sys.argv[1:]:
    works = {norm_doi(w.get("doi")): w for w in read_jsonl(os.path.join(CACHE, f"a_works_{inst}.jsonl"))}
    oa_id = INST[inst]["oa"]
    print(f"===== {inst}: {len(works)} OpenAlex works cached")
    tab = C.Counter()
    for row in csv.DictReader(open(os.path.join(REPO_GOLDEN, f"precision_audit_{inst}.csv"), encoding="utf8")):
        w = works.get(norm_doi(row["doi"]))
        v = facts(w, inst, oa_id)["affiliation_openalex"] if w else "not_in_openalex"
        tab[(row["tier"], row["verdict"], v)] += 1
    print("audit sample  (tier, hand verdict, OpenAlex verdict): count")
    for k in sorted(tab):
        print("  ", k, tab[k])
    ver = C.Counter()
    lik = C.Counter()
    for r in load_records(inst):
        w = works.get(norm_doi(r["doi"]))
        if not w:
            continue
        v = facts(w, inst, oa_id)["affiliation_openalex"]
        (ver if r["affiliation_status"] == "verified" else lik)[v] += 1
    print("already-verified records, OpenAlex verdict:", dict(ver))
    print("'likely' records, OpenAlex verdict:      ", dict(lik))

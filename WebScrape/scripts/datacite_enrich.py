"""Enrichment E2: DataCite metadata for DOIs Crossref does not know (arXiv 10.48550, Zenodo, LIPIcs...).
Records are converted to a Crossref-like shape so finalize.py can treat them uniformly.
Cache: WebScrape/raw/crossref_full/datacite.jsonl.gz (same cache dir, `_src: datacite`).

usage: python3 datacite_enrich.py <inst_key>
"""
import os, sys, json, gzip, glob, threading, queue
from common import get, RAW, read_jsonl_gz, norm_doi

inst = sys.argv[1]
D = os.path.join(RAW, "crossref_full")
have = set()
for fn in glob.glob(os.path.join(D, "*.jsonl.gz")):
    try:
        for r in read_jsonl_gz(fn):
            if not r.get("_missing"):
                have.add(r["_q"])
    except EOFError:
        pass
todo = sorted({c["doi"] for c in read_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz")) if c["doi"] and c["doi"] not in have})
print("datacite todo", len(todo), flush=True)
TYPES = {"Preprint": "posted-content", "Text": "posted-content", "Dataset": "dataset", "Software": "component",
         "ConferencePaper": "proceedings-article", "JournalArticle": "journal-article", "BookChapter": "book-chapter",
         "Book": "book", "Dissertation": "dissertation", "Report": "report", "Image": "component", "Collection": "component"}


def convert(d, doi):
    a = d["attributes"]
    authors = []
    for cr in a.get("creators", []):
        authors.append({"given": cr.get("givenName"), "family": cr.get("familyName"), "name": cr.get("name"),
                        "ORCID": next((n["nameIdentifier"] for n in cr.get("nameIdentifiers", []) if n.get("nameIdentifierScheme") == "ORCID"), None),
                        "affiliation": [{"name": x if isinstance(x, str) else x.get("name", "")} for x in cr.get("affiliation", [])]})
    t = (a.get("types") or {})
    typ = TYPES.get(t.get("resourceTypeGeneral"), "other")
    if doi.startswith("10.48550/"):
        typ = "posted-content"
    cont = (a.get("container") or {}).get("title") or ("arXiv" if doi.startswith("10.48550/") else None)
    return {"_q": doi, "_src": "datacite", "DOI": doi, "type": typ, "title": [x["title"] for x in a.get("titles", [])[:1]],
            "author": authors, "issued": {"date-parts": [[a.get("publicationYear")]]}, "container-title": [cont] if cont else [],
            "publisher": a.get("publisher") if isinstance(a.get("publisher"), str) else (a.get("publisher") or {}).get("name"),
            "is-referenced-by-count": a.get("citationCount"),
            "reference": [{"DOI": r["relatedIdentifier"]} for r in a.get("relatedIdentifiers", [])
                          if r.get("relationType") == "References" and r.get("relatedIdentifierType") == "DOI"] or None,
            "relation": {"is-preprint-of": [{"id": r["relatedIdentifier"]} for r in a.get("relatedIdentifiers", [])
                                            if r.get("relationType") in ("IsPreviousVersionOf", "IsVersionOf") and r.get("relatedIdentifierType") == "DOI"]}}


q = queue.Queue(); [q.put(x) for x in todo]
lock = threading.Lock(); f = gzip.open(os.path.join(D, f"datacite_{inst}.jsonl.gz"), "at")


def w():
    while True:
        try:
            doi = q.get_nowait()
        except queue.Empty:
            return
        r = get(f"https://api.datacite.org/dois/{doi}")
        rec = convert(r.json()["data"], doi) if r.status_code == 200 else {"_q": doi, "_missing": True, "_src": "datacite"}
        with lock:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


ts = [threading.Thread(target=w) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
f.close(); print("done")

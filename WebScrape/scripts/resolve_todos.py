"""Step R: confirmatory pass that tries to resolve remaining TODO fields from external sources.
All results go to caches that finalize.py / build_candidates.py consume; nothing is written into the
output JSON directly. Run after a finalize; then re-run build -> enrich -> finalize.

  R1  Crossref single-DOI retry for DOIs never found (batch filter queries gave false negatives
      for ~12 % of these in a 40-DOI sample)                -> raw/crossref_full/single_retry.jsonl.gz
  R2  doi.org content negotiation (CSL-JSON; works for every registration agency, e.g. mEDRA, JaLC)
      for DOIs unknown to Crossref and DataCite             -> raw/crossref_full/csl.jsonl.gz
  R3  DOI-less records: title search in Crossref (bibliographic), DataCite and Semantic Scholar
      (/paper/search/match). Accepted only if title-token Jaccard >= 0.9, |year diff| <= 1 and, when
      both sides list authors, at least one shared surname    -> raw/doi_resolved2_<inst>.tsv
  R4  ISSN for journal records without ISSN: Crossref /journals title search, exact normalised
      title match only                                      -> raw/issn_lookup.json
  R5  Semantic Scholar batch (citationCount, reference DOIs) for DOI/arXiv records whose references are
      TODO                                                  -> raw/s2/s2.jsonl

usage: python3 resolve_todos.py <inst_key> [<inst_key> ...]
"""
import os, re, sys, json, gzip, glob, time, html, unicodedata, urllib.parse
from common import get, post, RAW, OUT, MAILTO, read_jsonl_gz, norm_doi

INSTS = sys.argv[1:]


def toks(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z0-9]+", t))


def jacc(a, b):
    return len(a & b) / max(1, len(a | b))


def surnames(names):
    out = set()
    for n in names or []:
        n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
        n = n.split(",")[0] if "," in n else (n.split()[-1] if n.split() else "")
        if len(n) > 1:
            out.add(n)
    return out


def load_records():
    recs = []
    for inst in INSTS:
        for f in (inst + ".json", f"candidates_unconfirmed_{inst}.json"):
            p = os.path.join(OUT, f)
            if os.path.exists(p):
                recs += [(inst, r) for r in json.load(open(p))["records"]]
    return recs


RECS = load_records()
CRD = os.path.join(RAW, "crossref_full")
known, cr_found = set(), set()
for fn in glob.glob(os.path.join(CRD, "*.jsonl.gz")):
    for r in read_jsonl_gz(fn):
        if not r.get("_missing"):
            cr_found.add(r["_q"])
all_dois = {norm_doi(r["doi"]) for _, r in RECS if r["doi"] != "TODO"}
never = sorted(d for d in all_dois if d and d not in cr_found)
print("R1/R2: DOIs with no metadata record:", len(never), flush=True)

# ---------------- R1 Crossref single retry
f1 = gzip.open(os.path.join(CRD, "single_retry.jsonl.gz"), "at")
still = []
for d in never:
    r = get("https://api.crossref.org/works/" + urllib.parse.quote(d, safe="/()"), params={"mailto": MAILTO})
    if r.status_code == 200:
        it = r.json()["message"]; it["_q"] = d
        f1.write(json.dumps(it, ensure_ascii=False) + "\n")
    else:
        still.append(d)
f1.close()
print("R1 recovered", len(never) - len(still), flush=True)

# ---------------- R2 CSL content negotiation
f2 = gzip.open(os.path.join(CRD, "csl.jsonl.gz"), "at"); n2 = 0
for d in still:
    if d.startswith("10.48550/"):
        continue
    try:
        r = get("https://doi.org/" + urllib.parse.quote(d, safe="/()"), headers={"Accept": "application/vnd.citationstyles.csl+json"}, timeout=60)
        if r.status_code != 200 or not r.text.strip().startswith("{"):
            continue
        c = r.json()
    except Exception:
        continue
    typ = {"article-journal": "journal-article", "paper-conference": "proceedings-article", "chapter": "book-chapter",
           "book": "book", "posted-content": "posted-content", "report": "report", "thesis": "dissertation"}.get(c.get("type"), "other")
    cont = c.get("container-title")
    rec = {"_q": d, "_src": "csl", "DOI": d, "type": typ, "title": [c.get("title")] if c.get("title") else [],
           "author": [{"given": a.get("given"), "family": a.get("family") or a.get("literal"), "affiliation": []} for a in c.get("author", [])],
           "issued": c.get("issued") or {"date-parts": [[None]]}, "container-title": [cont] if isinstance(cont, str) else (cont or []),
           "ISSN": c.get("ISSN") if isinstance(c.get("ISSN"), list) else ([c["ISSN"]] if c.get("ISSN") else []),
           "publisher": c.get("publisher")}
    f2.write(json.dumps(rec, ensure_ascii=False) + "\n"); n2 += 1
    time.sleep(0.3)
f2.close()
print("R2 csl records", n2, flush=True)

# ---------------- R3 DOI-less title resolution (on candidate keys, so build_candidates can apply them)
for inst in INSTS:
    outfn = os.path.join(RAW, f"doi_resolved2_{inst}.tsv")
    done = {l.split("\t")[0] for l in open(outfn)} if os.path.exists(outfn) else set()
    final_titles = {"".join(sorted(toks(r["title"]))) for i, r in RECS if i == inst and r["doi"] == "TODO" and isinstance(r["title"], str)}
    cands = [c for c in read_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz"))
             if not c["doi"] and c.get("title") and c["key"] not in done and "".join(sorted(toks(c["title"]))) in final_titles]
    print(f"R3 {inst}: DOI-less candidates to resolve", len(cands), flush=True)
    out = open(outfn, "a"); hit = 0
    for c in cands:
        T = toks(c["title"]); y = c["year"]
        names = c["meta"].get("epmc_authors") or c["meta"].get("doaj_authors") or []
        mine = surnames(names) | surnames([re.sub(r"[\(\[].*", "", p).strip() for p in c.get("persons", [])])
        best = ""
        if len(T) >= 4:
            # Crossref
            try:
                items = get("https://api.crossref.org/works", params={"query.bibliographic": c["title"], "rows": 5, "mailto": MAILTO,
                            "select": "DOI,title,issued,author"}).json()["message"]["items"]
            except Exception:
                items = []
            for it in items:
                iy = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
                au = surnames([(a.get("family") or "") for a in it.get("author", [])])
                if iy and abs(iy - y) <= 1 and jacc(T, toks((it.get("title") or [""])[0])) >= 0.9 and (not mine or not au or mine & au):
                    best = norm_doi(it["DOI"]); break
            # DataCite
            if not best:
                try:
                    q = 'titles.title:"' + c["title"].replace('"', " ") + '"'
                    for it in get("https://api.datacite.org/dois", params={"query": q, "page[size]": 5}).json().get("data", []):
                        a = it["attributes"]
                        tt = (a.get("titles") or [{}])[0].get("title", "")
                        if a.get("publicationYear") and abs(int(a["publicationYear"]) - y) <= 1 and jacc(T, toks(tt)) >= 0.9:
                            best = norm_doi(a["doi"]); break
                except Exception:
                    pass
            # arXiv id known
            if not best and c["meta"].get("arxiv"):
                best = "10.48550/arxiv." + re.sub(r"v\d+$", "", c["meta"]["arxiv"].lower().replace("arxiv:", ""))
            # Semantic Scholar title match (shared anonymous pool: tolerate failures)
            if not best:
                try:
                    r = get("https://api.semanticscholar.org/graph/v1/paper/search/match",
                            params={"query": c["title"], "fields": "title,year,externalIds"}, tries=4)
                    if r.status_code == 200:
                        for it in r.json().get("data", []):
                            ex = it.get("externalIds") or {}
                            if it.get("year") and abs(it["year"] - y) <= 1 and jacc(T, toks(it.get("title"))) >= 0.9:
                                best = norm_doi(ex.get("DOI")) or ("10.48550/arxiv." + ex["ArXiv"].lower() if ex.get("ArXiv") else "")
                                break
                except Exception:
                    pass
        out.write(f"{c['key']}\t{best or ''}\n"); out.flush(); hit += bool(best)
    out.close()
    print(f"R3 {inst}: resolved {hit}", flush=True)

# ---------------- R4 ISSN lookup by journal title
ifn = os.path.join(RAW, "issn_lookup.json")
ISSN = json.load(open(ifn)) if os.path.exists(ifn) else {}
venues = sorted({r["venue"] for _, r in RECS if r["type"] == "journal" and r["issn"] == "TODO" and isinstance(r["venue"], str) and r["venue"] != "TODO"} - set(ISSN))
print("R4 venues needing ISSN", len(venues), flush=True)
for v in venues:
    res = []
    try:
        for it in get("https://api.crossref.org/journals", params={"query": v, "rows": 5, "mailto": MAILTO}).json()["message"]["items"]:
            if "".join(sorted(toks(it.get("title")))) == "".join(sorted(toks(v))):
                res = it.get("ISSN") or []
                break
    except Exception:
        pass
    ISSN[v] = res
json.dump(ISSN, open(ifn, "w"), indent=0)
print("R4 resolved", sum(1 for v in venues if ISSN.get(v)), flush=True)

# ---------------- R5 Semantic Scholar references / citations
sd = os.path.join(RAW, "s2"); os.makedirs(sd, exist_ok=True)
sfn = os.path.join(sd, "s2.jsonl")
have = set()
if os.path.exists(sfn):
    for l in open(sfn):
        try:
            have.add(json.loads(l)["q"])
        except Exception:
            pass
ids = []
for _, r in RECS:
    if r["doi"] != "TODO" and r["references"] == "TODO":
        d = norm_doi(r["doi"])
        q = ("ARXIV:" + d.split("arxiv.", 1)[1]) if d.startswith("10.48550/arxiv.") else "DOI:" + d
        if q not in have:
            ids.append(q)
ids = sorted(set(ids))
print("R5 S2 ids", len(ids), flush=True)
out = open(sfn, "a"); got = 0
for i in range(0, len(ids), 100):
    batch = ids[i:i + 100]
    res = None
    for attempt in range(12):
        try:
            r = post("https://api.semanticscholar.org/graph/v1/paper/batch", json_body={"ids": batch},
                     params={"fields": "externalIds,citationCount,referenceCount,references.externalIds"}, tries=1, timeout=120)
            res = r.json(); break
        except Exception:
            time.sleep(5 + 5 * attempt)
    if res is None:
        continue
    for q, p in zip(batch, res):
        row = {"q": q}
        if p:
            refs = sorted({norm_doi((x.get("externalIds") or {}).get("DOI")) for x in (p.get("references") or [])} - {None})
            arx = sorted({"10.48550/arxiv." + (x.get("externalIds") or {}).get("ArXiv").lower() for x in (p.get("references") or [])
                          if (x.get("externalIds") or {}).get("ArXiv") and not (x.get("externalIds") or {}).get("DOI")})
            row.update(citation_count=p.get("citationCount"), reference_count=p.get("referenceCount"), references=refs + arx)
            got += 1
        out.write(json.dumps(row) + "\n"); out.flush()
    time.sleep(3)
    if (i // 100) % 10 == 0:
        print("R5", i, "/", len(ids), "found", got, flush=True)
out.close()
print("R5 done, found", got)

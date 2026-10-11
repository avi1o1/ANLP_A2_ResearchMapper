"""Top 10 most-cited papers citing each institute (PPT slide 12, Indian connectivity).
Citing papers = the same set as the citation in-flow in stats_citation.py: works of another Indian institution that cite
the institute's papers ('in_from_indian' edges), plus papers of the other IIT that cite it (cross-institute 'internal'
edges). They are ranked by their own worldwide citation count (OpenAlex cited_by_count, at fetch time).
Online step: one OpenAlex request per 100 citing works (~1,410 requests). Counts are cached in
../cache/citing_counts.json and details of the top papers in ../cache/citing_details.json, so a re-run is offline.
An OpenAlex key (OPENALEX_API_KEY) is used when set; the works endpoint also answers without one.
Output (results/): top_citing_papers.csv
usage: python stats_citing_top.py"""
import os, json, time, collections as C
import requests
from common import INSTS, DATA, CACHE, read_csv, write_csv

COUNTS = os.path.join(CACHE, "citing_counts.json")
DETAILS = os.path.join(CACHE, "citing_details.json")
TOP = 10
S = requests.Session()


def fetch(ids, select):
    """OpenAlex works for up to 100 W-ids; returns the result list."""
    params = {"filter": "openalex:" + "|".join(ids), "select": select, "per-page": 100}
    if os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = os.environ["OPENALEX_API_KEY"]
    for attempt in range(8):
        try:
            r = S.get("https://api.openalex.org/works", params=params, timeout=90)
            if r.status_code == 200:
                return r.json()["results"]
        except requests.RequestException:
            time.sleep(2 + 3 * attempt)
            continue
        if r.status_code == 429 and "budget" in r.text.lower():
            raise SystemExit("OpenAlex daily budget used up: set OPENALEX_API_KEY, or re-run after midnight UTC (resumes from cache)")
        time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"OpenAlex request failed: {ids[0]}..")


def load(path):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def fill(cache, path, ids, select, row):
    todo = sorted(set(ids) - set(cache))
    try:
        for n in range(0, len(todo), 100):
            chunk = todo[n:n + 100]
            got = {w["id"].rsplit("/", 1)[-1]: row(w) for w in fetch(chunk, select)}
            for i in chunk:
                cache[i] = got.get(i)              # None = not found (merged or deleted work)
            if n // 100 % 50 == 0 or n + 100 >= len(todo):
                print(f"  {path.rsplit(os.sep, 1)[-1]}: {min(n + 100, len(todo))}/{len(todo)}", flush=True)
            time.sleep(0.1)
    finally:                                       # keep what was fetched, so a re-run resumes (e.g. after the daily limit)
        json.dump(cache, open(path, "w", encoding="utf-8"), separators=(",", ":"))
    return cache


def main():
    cited = C.defaultdict(lambda: C.defaultdict(set))   # institute -> citing W-id -> our W-ids it cites
    for e in read_csv(os.path.join(DATA, "citation_network.csv")):
        s, t = e["source_openalex"], e["target_openalex"]
        if not s or not t:
            continue
        if e["edge_type"] == "in_from_indian":
            targets = e["target_inst"].split(";")
        elif e["edge_type"] == "internal" and e["cross_inst"] == "TRUE":
            targets = [i for i in e["target_inst"].split(";") if i not in e["source_inst"].split(";")]
        else:
            continue
        for inst in targets:
            cited[inst][s].add(t)
    allids = set().union(*[set(d) for d in cited.values()])
    print(f"{len(allids):,} distinct citing works")
    counts = fill(load(COUNTS), COUNTS, allids, "id,cited_by_count", lambda w: w["cited_by_count"])

    tops = {inst: sorted((w for w in d if counts.get(w) is not None), key=lambda w: -counts[w])[:TOP]
            for inst, d in cited.items() if inst in INSTS.values()}
    details = fill(load(DETAILS), DETAILS, {w for ws in tops.values() for w in ws},
                   "id,doi,display_name,publication_year,primary_location,authorships",
                   lambda w: {"title": w["display_name"], "doi": w["doi"], "year": w["publication_year"],
                              "journal": ((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
                              "institutions": sorted({i["display_name"] for a in w["authorships"] for i in a["institutions"]
                                                      if i.get("country_code") == "IN"})})
    rows = []
    for inst in INSTS.values():
        for rank, w in enumerate(tops[inst], 1):
            d = details.get(w) or {}
            rows.append({"scope": inst, "rank": rank, "title": d.get("title"), "journal": d.get("journal"),
                         "year": d.get("year"), "citations": counts[w], "doi": d.get("doi"),
                         "citing_institutions": "; ".join(d.get("institutions") or []),
                         "papers_cited": len(cited[inst][w]), "openalex_id": w})
    write_csv("top_citing_papers.csv", rows)


if __name__ == "__main__":
    main()

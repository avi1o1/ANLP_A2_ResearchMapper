"""Online step for the faculty and journal statistics: three small OpenAlex fetches, cached in ../cache/ so a re-run is
offline (only missing ids are fetched).
  oa_counts_by_year.json  work id -> {year: citations received that year} for every paper in the analysis set
                          (used for the h-index at the end of each year)
  oa_sources.json         source id -> journal name, publisher, 2-year mean citedness (the "IF (OpenAlex)": citations in
                          the last year to the source's papers of the two years before, divided by those papers), h-index
  oa_paper_source.json    work id -> source id, read from the cached Stage A works (Enrichment/cache/a*_works_*.jsonl)
  oa_authors.json         faculty roster id -> OpenAlex author id (the id most often attached to that person's matched
                          papers, by name) and that author's all-career h-index, i10-index, works and citations
Cost: one credit per 100 ids (about 600 credits in total). Key: OPENALEX_API_KEY or OPENALEX_KEY_FILE (see oa.py).
usage: python fetch_openalex_extra.py"""
import os, json, glob, collections as C
from common import INSTS, CACHE, ENRICH, load_records
from oa import get, credits
from faculty import compatible

F_CBY = os.path.join(CACHE, "oa_counts_by_year.json")
F_SRC = os.path.join(CACHE, "oa_sources.json")
F_PSRC = os.path.join(CACHE, "oa_paper_source.json")
F_AUT = os.path.join(CACHE, "oa_authors.json")


def load(fn):
    if os.path.exists(fn):
        with open(fn, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def dump(obj, fn):
    """Write to a temporary file, then rename, so an interrupted run never leaves a half-written cache."""
    if fn == os.devnull:
        return
    with open(fn + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(fn + ".tmp", fn)


def batched_fetch(endpoint, ids, select, handle, done, fn, label):
    todo = [i for i in sorted(ids) if i not in done]
    print(f"{label}: {len(ids)} ids, {len(todo)} to fetch")
    for k in range(0, len(todo), 100):
        chunk = todo[k:k + 100]
        res = get(endpoint, {"filter": "openalex:" + "|".join(chunk), "select": select, "per-page": 100}) or {}
        for x in res.get("results", []):
            handle(x)
        for i in chunk:                                     # ids OpenAlex no longer knows: remember as empty
            done.setdefault(i, None)
        if k // 100 % 20 == 19:
            dump(done, fn)
            print(f"  {k + len(chunk)}/{len(todo)}  credits used {credits['used']}, remaining {credits['remaining']}")
    dump(done, fn)


def paper_sources(wanted):
    """work id -> source id from the cached Stage A/A2 works (no request needed)."""
    out = load(F_PSRC)
    if wanted <= set(out):
        return out
    for fn in sorted(glob.glob(os.path.join(ENRICH, "cache", "a*_works_*.jsonl"))):
        with open(fn, encoding="utf-8") as fh:
            for line in fh:
                tag = '"id": "https://openalex.org/'
                i = line.find(tag + "W")
                if i < 0:
                    continue
                i += len(tag)
                w = line[i:line.index('"', i)]
                if w not in wanted or w in out:
                    continue
                src = ((json.loads(line).get("primary_location") or {}).get("source") or {}).get("id")
                out[w] = src.rsplit("/", 1)[-1] if src else None
    dump(out, F_PSRC)
    return out


def faculty_author_ids(recs):
    """roster id -> (OpenAlex author id, papers where it is attached, papers checked)."""
    votes = C.defaultdict(C.Counter)
    for r in recs:
        for f in r.get("faculty") or []:
            for a in r.get("authors_openalex") or []:
                if a.get("openalex_author") and compatible(a["name"], f["name"]):
                    votes[f["roster_id"]][a["openalex_author"]] += 1
                    break
    return {rid: (*v.most_common(1)[0], sum(v.values())) for rid, v in votes.items()}


def main():
    recs = [r for i in INSTS for r in load_records(i)]
    works = {r["openalex_id"] for r in recs if r.get("openalex_id")}
    print(len(recs), "analysis records,", len(works), "with an OpenAlex id")

    cby = load(F_CBY)
    batched_fetch("/works", works, "id,counts_by_year",
                  lambda x: cby.__setitem__(x["id"].rsplit("/", 1)[-1],
                                            {str(c["year"]): c["cited_by_count"] for c in x.get("counts_by_year") or []}),
                  cby, F_CBY, "works counts_by_year")

    psrc = paper_sources(works)
    srcs = {s for w, s in psrc.items() if s and w in works}
    src = load(F_SRC)
    batched_fetch("/sources", srcs, "id,display_name,host_organization_name,issn_l,type,summary_stats",
                  lambda x: src.__setitem__(x["id"].rsplit("/", 1)[-1], {
                      "name": x.get("display_name"), "publisher": x.get("host_organization_name"),
                      "issn_l": x.get("issn_l"), "type": x.get("type"),
                      "if_2yr": (x.get("summary_stats") or {}).get("2yr_mean_citedness"),
                      "h_index": (x.get("summary_stats") or {}).get("h_index")}),
                  src, F_SRC, "sources")

    ids = faculty_author_ids(recs)
    keys = ("oa_name", "works", "citations", "h_index", "i10_index")
    stats = {d["author"]: {k: d[k] for k in keys} for d in load(F_AUT).values() if "h_index" in d}
    batched_fetch("/authors", {a for a, _, _ in ids.values()}, "id,display_name,works_count,cited_by_count,summary_stats",
                  lambda x: stats.__setitem__(x["id"].rsplit("/", 1)[-1], {
                      "oa_name": x.get("display_name"), "works": x.get("works_count"), "citations": x.get("cited_by_count"),
                      "h_index": (x.get("summary_stats") or {}).get("h_index"),
                      "i10_index": (x.get("summary_stats") or {}).get("i10_index")}),
                  dict(stats), os.devnull, "authors")
    aut = {rid: dict({"author": a, "papers_with_this_id": n, "papers_checked": tot}, **stats.get(a, {}))
           for rid, (a, n, tot) in ids.items()}
    dump(aut, F_AUT)
    print("done; credits used", credits["used"], "remaining", credits["remaining"])


if __name__ == "__main__":
    main()

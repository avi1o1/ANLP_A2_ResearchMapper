"""Stages B and C: Indian works our papers cite (B) and Indian works that cite our papers (C).
For every batch of 100 of our OpenAlex work ids:
  B: /works?filter=cited_by:W1|..|W100,authorships.institutions.country_code:IN   -> works our papers cite
  C: /works?filter=cites:W1|..|W100,authorships.institutions.country_code:IN      -> works citing our papers
All result pages are followed with cursor paging. The which-paper-cites-which link is recovered locally:
  B: X is cited by our P  iff  X in P.referenced_works
  C: Y cites our P        iff  P in Y.referenced_works
Resumable per batch: cache/<b|c>_done_<inst>.txt (batch first id), cache/<b|c>_works_<inst>.jsonl.
usage: python stage_bc_indian.py <b|c> <inst_key> [...]"""
import os, sys, json
from oa import get, read_jsonl, CACHE, credits

stage = sys.argv[1]
assert stage in ("b", "c")
FILTER = {"b": "cited_by", "c": "cites"}[stage]
SEL = {"b": "id,doi,publication_year,authorships",
       "c": "id,doi,publication_year,authorships,referenced_works"}[stage]


def slim(w):
    """Keep only what the network files need: ids, year, and each author's institutions."""
    out = {"id": w["id"].rsplit("/", 1)[-1], "doi": w.get("doi"), "year": w.get("publication_year"),
           "institutions": sorted({(i["id"].rsplit("/", 1)[-1], i.get("display_name"), i.get("country_code"))
                                   for a in w.get("authorships") or [] for i in a.get("institutions") or [] if i.get("id")})}
    if "referenced_works" in w:
        out["referenced_works"] = [x.rsplit("/", 1)[-1] for x in w.get("referenced_works") or []]
    return out


for inst in sys.argv[2:]:
    ours = sorted({w["id"].rsplit("/", 1)[-1] for fn in (f"a_works_{inst}.jsonl", f"a2_works_{inst}.jsonl")
                   for w in read_jsonl(os.path.join(CACHE, fn))})
    dfn = os.path.join(CACHE, f"{stage}_done_{inst}.txt")
    wfn = os.path.join(CACHE, f"{stage}_works_{inst}.jsonl")
    done = set(open(dfn).read().split()) if os.path.exists(dfn) else set()
    batches = [ours[i:i + 100] for i in range(0, len(ours), 100)]
    todo = [b for b in batches if b[0] not in done]
    print(f"{inst} stage {stage}: {len(ours)} works, {len(batches)} batches, {len(todo)} to do", flush=True)
    with open(wfn, "a", encoding="utf8") as wf, open(dfn, "a") as df:
        for k, b in enumerate(todo):
            cursor, rows = "*", []
            while cursor:
                j = get("/works", {"filter": f"{FILTER}:" + "|".join(b) + ",authorships.institutions.country_code:IN",
                                   "per-page": 200, "cursor": cursor, "select": SEL})
                rows += [slim(w) for w in j["results"]]
                cursor = j["meta"].get("next_cursor") if j["results"] else None
            # write the whole batch at once so an interruption never leaves a half-done batch marked done
            wf.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)); wf.flush()
            df.write(b[0] + "\n"); df.flush()
            if k % 20 == 0:
                print(f"  {inst} {stage} batch {k + 1}/{len(todo)} rows={len(rows)} credits_used={credits['used']} remaining={credits['remaining']}", flush=True)
    print(f"{inst} stage {stage}: done; credits_used={credits['used']} remaining={credits['remaining']}", flush=True)

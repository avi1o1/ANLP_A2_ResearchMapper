"""Look up DOIs of the works cited by records whose references are TODO (OpenAlex ids -> DOI, 100 per request).
Writes cache/ref_dois.jsonl rows {id, doi}; doi is null when OpenAlex has the work but no DOI for it.
usage: python stage_refdoi.py"""
import os, json
from oa import get, read_jsonl, norm_doi, CACHE, OUT, credits

need = set()
for inst in ("iit_kharagpur", "iit_roorkee"):
    with open(os.path.join(OUT, f"{inst}_enriched.json"), encoding="utf8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line.startswith('{"title"'):
                r = json.loads(line)
                if r["references"] == "TODO" and r.get("references_openalex"):
                    need.update(r["references_openalex"])
fn = os.path.join(CACHE, "ref_dois.jsonl")
have = {row["id"] for row in read_jsonl(fn)}
todo = sorted(need - have)
print("cited works to look up:", len(todo), flush=True)
with open(fn, "a", encoding="utf8") as out:
    for i in range(0, len(todo), 100):
        b = todo[i:i + 100]
        j = get("/works", {"filter": "openalex:" + "|".join(b), "per-page": 100, "select": "id,doi"})
        got = {w["id"].rsplit("/", 1)[-1]: norm_doi(w.get("doi")) for w in j["results"]}
        # ids OpenAlex does not return are deleted works: merge.py treats them like cited works without a DOI
        out.write("".join(json.dumps({"id": k, "doi": v}) + "\n" for k, v in got.items()))
        out.flush()
# every id in `todo` was queried; ids not returned no longer exist in OpenAlex (deleted works -> 404)
with open(os.path.join(CACHE, "ref_queried.txt"), "a") as q:
    q.write("".join(i + "\n" for i in todo))
print("done; credits_used", credits["used"], "remaining", credits["remaining"])

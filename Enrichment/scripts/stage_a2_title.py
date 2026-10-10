"""Stage A2: records with no DOI -> OpenAlex title search (1 credit each).
Accepted only if: title-token Jaccard >= 0.9, |year difference| <= 1, and at least one shared author surname
(our authors, or the faculty names that found the record). Same thresholds as the original pipeline's R3 step.
Resumable: cache/a2_queried_<inst>.txt (record ids), cache/a2_works_<inst>.jsonl (accepted works, with _record_id).
usage: python stage_a2_title.py <inst_key> [...]"""
import os, re, sys, json, html, unicodedata
from oa import get, load_records, CACHE, credits, SELECT


def toks(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return set(re.findall(r"[a-z0-9]+", t))


def surname(n):
    n = unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[\(\[].*", "", n).strip()
    n = n.split(",")[0] if "," in n else (n.split()[-1] if n.split() else "")
    return n if len(n) > 1 else None


def our_surnames(r):
    names = [a.get("name") for a in r["authors"]] if isinstance(r["authors"], list) else []
    names += r.get("found_via_person") or []
    return {s for s in map(surname, names) if s}


for inst in sys.argv[1:]:
    recs = [r for r in load_records(inst) if r["doi"] == "TODO" and isinstance(r["title"], str) and isinstance(r["year"], int)]
    qfn = os.path.join(CACHE, f"a2_queried_{inst}.txt")
    wfn = os.path.join(CACHE, f"a2_works_{inst}.jsonl")
    done = set(open(qfn).read().split()) if os.path.exists(qfn) else set()
    todo = [r for r in recs if r["record_id"] not in done]
    print(f"{inst}: {len(recs)} DOI-less records, {len(todo)} to search", flush=True)
    hits = 0
    with open(wfn, "a", encoding="utf8") as wf, open(qfn, "a") as qf:
        for k, r in enumerate(todo):
            T = toks(r["title"]); y = r["year"]; mine = our_surnames(r)
            if len(T) >= 4 and mine:
                q = " ".join(sorted(T, key=lambda t: -len(t))[:20])   # plain words only: no filter-syntax characters
                j = get("/works", {"search": q, "filter": f"publication_year:{y - 1}-{y + 1}", "per-page": 5, "select": SELECT})
                for w in (j or {}).get("results", []):
                    wt = toks(w.get("title"))
                    jac = len(T & wt) / max(1, len(T | wt))
                    theirs = {surname((a.get("author") or {}).get("display_name")) for a in w.get("authorships") or []} - {None}
                    if jac >= 0.9 and abs((w.get("publication_year") or 0) - y) <= 1 and mine & theirs:
                        w["_record_id"] = r["record_id"]; w["_title_jaccard"] = round(jac, 3)
                        wf.write(json.dumps(w, ensure_ascii=False) + "\n"); wf.flush(); hits += 1
                        break
            qf.write(r["record_id"] + "\n"); qf.flush()
            if k % 200 == 0:
                print(f"  {inst} {k}/{len(todo)} hits={hits} credits_used={credits['used']} remaining={credits['remaining']}", flush=True)
    print(f"{inst}: title matches accepted {hits}", flush=True)

"""Live re-check of cites_indian_inst / cited_by_indian_inst against fresh OpenAlex queries (costs ~4 credits per
sampled paper; default 10 per flag value -> ~40 credits per institute).
For cited_by FALSE, only papers with >= 1 citation are sampled (a paper nobody cites is trivially FALSE).
usage: python spotcheck_flags.py <inst_key> [n_per_value] [seed]
Set OPENALEX_KEY_FILE to choose the key file (default .openalex_key)."""
import os, sys, json, random
from oa import get, OUT, INST, credits

inst = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 11)
own = INST[inst]["oa"]
recs = []
for line in open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8"):
    s = line.strip().rstrip(",")
    if s.startswith('{"title"'):
        recs.append(json.loads(s))


def live(flt, wid):
    rows, cur = [], "*"
    while cur:
        j = get("/works", {"filter": f"{flt}:{wid},authorships.institutions.country_code:IN", "per-page": 200,
                           "cursor": cur, "select": "id,authorships"})
        rows += j["results"]
        cur = j["meta"].get("next_cursor") if j["results"] else None
    return any(i.get("country_code") == "IN" and i["id"].rsplit("/", 1)[-1] != own
               for w in rows for a in w["authorships"] for i in a.get("institutions") or [])


bad = 0
for flag, flt, eligible in [("cited_by_indian_inst", "cites", lambda r: isinstance(r["citations"], int) and r["citations"] > 0),
                            ("cites_indian_inst", "cited_by", lambda r: True)]:
    for val in (True, False):
        pool = [r for r in recs if r.get(flag) is val and eligible(r)]
        sample = random.sample(pool, min(n, len(pool)))
        agree = sum(live(flt, r["openalex_id"]) == val for r in sample)
        bad += len(sample) - agree
        print(f"{inst} {flag}={val}: live OpenAlex agrees {agree}/{len(sample)}")
print("disagreements:", bad, "| credits used:", credits["used"])

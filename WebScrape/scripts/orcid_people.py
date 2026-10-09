"""Channel B1: ORCID person channel.

1. Search ORCID for profiles whose affiliations mention the institute (name token OR ROR id).
2. Fetch each public record; keep affiliation entries (employment/education/qualification/
   invited-position) that are *this* IIT (name must contain the city token AND IIT/'Indian
   Institute of Technology', or carry the institute's ROR/GRID/Ringgold id).
3. Save person + tenure windows + work summaries to WebScrape/raw/orcid/<inst>.jsonl.gz.
Filtering of works by tenure window happens in the merge step (documented there).

usage: python3 orcid_people.py <inst_key>
"""
import os, re, sys, json, threading, queue, time
from common import get, RAW, LOGS, write_jsonl_gz

CFG = {
    "iit_ropar": {"q": 'affiliation-org-name:(Ropar) OR affiliation-org-name:(Rupnagar) OR ror-org-id:"https://ror.org/02qkhhn56"',
                  "city": re.compile(r"ropar|rupnagar|roopnagar", re.I), "ids": {"https://ror.org/02qkhhn56", "grid.462391.b"}},
    "iit_roorkee": {"q": 'affiliation-org-name:(Roorkee) OR ror-org-id:"https://ror.org/00582g326"',
                    "city": re.compile(r"roorkee|roorke|rorkee|saharanpur", re.I), "ids": {"https://ror.org/00582g326", "grid.19003.3b"}},
    "iit_kharagpur": {"q": 'affiliation-org-name:(Kharagpur) OR ror-org-id:"https://ror.org/03w5sq511"',
                      "city": re.compile(r"kharagpur|kharagapur|khragpur|\bkgp\b", re.I), "ids": {"https://ror.org/03w5sq511", "grid.429017.9"}},
}
IIT = re.compile(r"\biit\b|indian institute of technology|iitkgp|iit-?kgp|iit\s*rpr", re.I)
H = {"Accept": "application/json"}
inst = sys.argv[1]; cfg = CFG[inst]

# 1. search
ids, start = [], 0
while True:
    d = get("https://pub.orcid.org/v3.0/search/", params={"q": cfg["q"], "rows": 1000, "start": start}, headers=H).json()
    res = d.get("result") or []
    ids += [r["orcid-identifier"]["path"] for r in res]
    start += 1000
    if start >= d["num-found"] or not res:
        break
ids = sorted(set(ids))
print(inst, "profiles:", len(ids), flush=True)


def yr(dt):
    try:
        return int(dt["year"]["value"])
    except Exception:
        return None


def matches(org):
    name = org.get("name", "")
    did = (org.get("disambiguated-organization") or {}).get("disambiguated-organization-identifier", "")
    return (cfg["city"].search(name) and IIT.search(name)) or did in cfg["ids"]


def parse(orcid, rec):
    a = rec.get("activities-summary") or {}
    tenures = []
    for sec, key in (("employments", "employment-summary"), ("educations", "education-summary"),
                     ("qualifications", "qualification-summary"), ("invited-positions", "invited-position-summary")):
        for g in (a.get(sec) or {}).get("affiliation-group", []):
            for s in g.get("summaries", []):
                e = s.get(key) or {}
                org = e.get("organization") or {}
                if matches(org):
                    tenures.append({"kind": sec, "org": org.get("name"), "dept": e.get("department-name"),
                                    "role": e.get("role-title"), "start": yr(e.get("start-date")), "end": yr(e.get("end-date"))})
    works = []
    for g in (a.get("works") or {}).get("group", []):
        s = g["work-summary"][0]
        ext = {}
        for x in (g.get("external-ids") or {}).get("external-id", []):
            ext.setdefault(x["external-id-type"], x["external-id-value"])
        works.append({"title": ((s.get("title") or {}).get("title") or {}).get("value"),
                      "year": yr(s.get("publication-date")), "type": s.get("type"),
                      "journal": (s.get("journal-title") or {}).get("value"), "ext": ext,
                      "source": ((s.get("source") or {}).get("source-name") or {}).get("value")})
    p = (rec.get("person") or {}).get("name") or {}
    name = " ".join(filter(None, [((p.get("given-names") or {}).get("value")), ((p.get("family-name") or {}).get("value"))]))
    return {"orcid": orcid, "name": name, "tenures": tenures, "works": works}


q, out, lock = queue.Queue(), [], threading.Lock()
for i in ids:
    q.put(i)


def worker():
    while True:
        try:
            o = q.get_nowait()
        except queue.Empty:
            return
        try:
            r = get(f"https://pub.orcid.org/v3.0/{o}/record", headers=H)
            row = parse(o, r.json()) if r.status_code == 200 else {"orcid": o, "error": r.status_code}
        except Exception as e:
            row = {"orcid": o, "error": str(e)}
        with lock:
            out.append(row)
            if len(out) % 250 == 0:
                print(inst, len(out), "/", len(ids), flush=True)
        time.sleep(0.5)


ts = [threading.Thread(target=worker) for _ in range(6)]
[t.start() for t in ts]; [t.join() for t in ts]
os.makedirs(os.path.join(RAW, "orcid"), exist_ok=True)
write_jsonl_gz(os.path.join(RAW, "orcid", inst + ".jsonl.gz"), out)
nt = sum(1 for r in out if r.get("tenures"))
with open(os.path.join(LOGS, "orcid_runs.tsv"), "a") as lg:
    lg.write(f"{inst}\t{cfg['q']}\tprofiles={len(ids)}\twith_matching_tenure={nt}\terrors={sum(1 for r in out if 'error' in r)}\n")
print("done", inst, len(out), "with tenure", nt)

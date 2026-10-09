"""Step M1: union of all discovery channels -> candidate set with per-record evidence trail.

Evidence kinds (strongest first):
  aff:<channel>        an author affiliation string on the record classifies as this IIT
  aff_uncertain:<ch>   only ambiguous affiliation strings mention the city (e.g. "Rupnagar/IN")
  orcid_tenure         work listed on an ORCID profile of a person affiliated with this IIT, dated
                       within [start, end+1] of that affiliation (open end -> start of next job, else 2026)
  orcid_untimed        same, but the affiliation has no start year (weak)
  dblp_person          work of a DBLP person whose (undated) DBLP affiliation is this IIT (weak)
  roster_*             added later by person-channel scripts driven by the faculty roster
Records whose affiliation strings mention the city but classify only as 'other' are logged as
rejected (not institute papers).

usage: python3 build_candidates.py <inst_key>
"""
import os, re, sys, glob, json, collections, unicodedata
from common import read_jsonl_gz, write_jsonl_gz, norm_doi, RAW, LOGS, YEAR_MIN, YEAR_MAX
from affil import classify

inst = sys.argv[1]
TOK = {"iit_ropar": ["Ropar", "Rupnagar", "Roopnagar", "140001", "Punjab"],
       "iit_roorkee": ["Roorkee", "247667", "Roorke", "Rorkee", "Saharanpur", "247001", "Uttarakhand"],
       "iit_kharagpur": ["Kharagpur", "721302", "Khargpur", "Kgp", "Kharagapur", "Kharagur", "Kharapur", "Khragpur",
                         "Karagpur", "Kharagpu", "IITKGP", "West_Bengal"]}[inst]


def tkey(title, year):
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9]+", "", t)
    return f"t:{t[:120]}:{year}" if t else None


cands = {}
rejected = collections.Counter()


def add(doi, title, year, ev, meta=None):
    if year is None or not (YEAR_MIN <= int(year) <= YEAR_MAX):
        return
    doi = norm_doi(doi)
    key = doi or tkey(title, year)
    if not key:
        return
    c = cands.setdefault(key, {"key": key, "doi": doi, "title": title, "year": int(year), "evidence": [], "meta": {}})
    if ev not in c["evidence"]:
        c["evidence"].append(ev)
    if meta:
        for k, v in meta.items():
            c["meta"].setdefault(k, v)
        for pk in ("orcid_person", "dblp_person", "roster_person"):
            if meta.get(pk):
                ps = c.setdefault("persons", [])
                if meta[pk] not in ps:
                    ps.append(meta[pk])


def classify_authors(author_affs):
    """author_affs: list of affiliation strings (one per author). -> ('iit'|'uncertain'|'other'|None, matched)"""
    ks = [(classify(inst, s), s) for s in author_affs if s]
    if any(k == "iit" for k, _ in ks):
        return "iit", [s for k, s in ks if k == "iit"]
    if any(k == "uncertain" for k, _ in ks):
        return "uncertain", [s for k, s in ks if k == "uncertain"]
    if any(k == "other" for k, _ in ks):
        return "other", []
    return None, []


# --- A1 Crossref affiliation sweeps
for fn in glob.glob(os.path.join(RAW, "crossref_aff", "*.light.jsonl.gz")):
    tok = os.path.basename(fn).split(".")[0]
    if tok not in TOK:
        continue
    for it in read_jsonl_gz(fn):
        affs = [" | ".join(a.get("name", "") for a in au.get("affiliation", [])) for au in it.get("author", [])]
        k, matched = classify_authors(affs)
        y = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        if k == "iit":
            add(it["DOI"], (it.get("title") or [None])[0], y, "aff:crossref", {"aff_matched": matched[:5]})
        elif k == "uncertain":
            add(it["DOI"], (it.get("title") or [None])[0], y, "aff_uncertain:crossref", {"aff_uncertain": matched[:5]})
        elif k == "other":
            rejected["crossref_other_org"] += 1

# --- A2 Europe PMC
for r in read_jsonl_gz(os.path.join(RAW, "europepmc", inst + ".jsonl.gz")):
    affs = []
    for au in (r.get("authorList") or {}).get("author", []):
        affs.append(" | ".join(a.get("affiliation", "") for a in (au.get("authorAffiliationDetailsList") or {}).get("authorAffiliation", [])))
    if not any(affs) and r.get("affiliation"):
        affs = [r["affiliation"]]
    k, matched = classify_authors(affs)
    meta = {"pmid": r.get("pmid"), "epmc_citedby": r.get("citedByCount"),
            "epmc_journal": ((r.get("journalInfo") or {}).get("journal") or {}).get("title"),
            "epmc_issn": [x for x in [((r.get("journalInfo") or {}).get("journal") or {}).get(k) for k in ("issn", "essn")] if x],
            "epmc_authors": [a.get("fullName") for a in (r.get("authorList") or {}).get("author", [])],
            "epmc_type": (r.get("pubTypeList") or {}).get("pubType")}
    if k == "iit":
        meta["aff_matched"] = matched[:5]
        add(r.get("doi"), r.get("title"), r.get("pubYear"), "aff:europepmc", meta)
    elif k == "uncertain":
        meta["aff_uncertain"] = matched[:5]
        add(r.get("doi"), r.get("title"), r.get("pubYear"), "aff_uncertain:europepmc", meta)
    else:
        rejected[f"europepmc_{k}"] += 1

# --- A3 DOAJ
for r in read_jsonl_gz(os.path.join(RAW, "doaj", inst + ".jsonl.gz")):
    b = r["bibjson"]
    affs = [a.get("affiliation", "") for a in b.get("author", [])]
    k, matched = classify_authors(affs)
    doi = next((i["id"] for i in b.get("identifier", []) if i.get("type", "").lower() == "doi"), None)
    meta = {"doaj_journal": (b.get("journal") or {}).get("title"), "doaj_issns": (b.get("journal") or {}).get("issns"),
            "doaj_authors": [a.get("name") for a in b.get("author", [])]}
    if k == "iit":
        meta["aff_matched"] = matched[:5]
        add(doi, b.get("title"), b.get("year"), "aff:doaj", meta)
    elif k == "uncertain":
        meta["aff_uncertain"] = matched[:5]
        add(doi, b.get("title"), b.get("year"), "aff_uncertain:doaj", meta)
    else:
        rejected[f"doaj_{k}"] += 1

# --- A4 INSPIRE-HEP (curated affiliations; query itself is by institution)
fn = os.path.join(RAW, "inspire", inst + ".jsonl.gz")
if os.path.exists(fn):
    for r in read_jsonl_gz(fn):
        doi = ((r.get("dois") or [{}])[0]).get("value")
        arx = ((r.get("arxiv_eprints") or [{}])[0]).get("value")
        if not doi and arx:
            doi = "10.48550/arxiv." + arx
        y = int((r.get("earliest_date") or "0")[:4] or 0)
        pi = (r.get("publication_info") or [{}])[0]
        matched = sorted({x.get("value", "") for a in r.get("authors", []) for x in (a.get("affiliations") or [])
                          if classify(inst, x.get("value", "")) == "iit"})
        add(doi, ((r.get("titles") or [{}])[0]).get("title"), y, "aff:inspire" if matched else "inspire_unmatched",
            {"arxiv": arx, "inspire_journal": pi.get("journal_title"), "inspire_citations": r.get("citation_count"),
             "aff_matched": matched[:5], "inspire_authors": [a.get("full_name") for a in r.get("authors", [])][:200]})

# --- B1 ORCID person channel
fn = os.path.join(RAW, "orcid", inst + ".jsonl.gz")
if os.path.exists(fn):
    for p in read_jsonl_gz(fn):
        if not p.get("tenures"):
            continue
        # other employments' start years, to close open-ended tenures
        windows, untimed = [], False
        for t in p["tenures"]:
            if t["start"] is None:
                untimed = True
                continue
            end = t["end"] if t["end"] else YEAR_MAX
            windows.append((t["start"], end + 1))
        for w in p["works"]:
            y = w.get("year")
            if y is None:
                continue
            if any(a <= y <= b for a, b in windows):
                ev = "orcid_tenure"
            elif untimed and not windows:
                ev = "orcid_untimed"
            else:
                continue
            add(w["ext"].get("doi"), w.get("title"), y, ev,
                {"orcid_person": f"{p['name']} ({p['orcid']})", "orcid_type": w.get("type"), "orcid_journal": w.get("journal"),
                 "arxiv": w["ext"].get("arxiv")})

# --- B2 DBLP person channel
fn = os.path.join(RAW, "dblp", inst + ".jsonl.gz")
if os.path.exists(fn):
    for r in read_jsonl_gz(fn):
        doi = r.get("doi") or None
        if doi:
            doi = doi.replace("https://doi.org/", "")
        add(doi, r.get("title"), int(r["year"]), "dblp_person",
            {"dblp_person": r["person_name"], "dblp_venue": r.get("venue"), "dblp_type": r.get("type", "").split("#")[-1], "dblp_pub": r.get("pub")})

# --- B3-B5 roster-driven person channels (roster_channels.py)
for fn in [os.path.join(RAW, "roster", inst + sfx + ".jsonl.gz") for sfx in ("", "_arxiv", "_loose")]:
    if not os.path.exists(fn):
        continue
    for r in read_jsonl_gz(fn):
        add(r.get("doi"), r.get("title"), r["year"], r["channel"],
            {"roster_person": r["person"], "roster_why": r.get("why"), "orcid_type": r.get("orcid_type"), "orcid_journal": r.get("journal"),
             "arxiv": r.get("arxiv"), "dblp_venue": r.get("dblp_venue"), "dblp_type": r.get("dblp_type")})

# --- apply DOIs found by doi_resolve.py (exact-title Crossref match), merging into existing DOI keys
for fn in (os.path.join(RAW, f"doi_resolved_{inst}.tsv"), os.path.join(RAW, f"doi_resolved2_{inst}.tsv")):
    if not os.path.exists(fn):
        continue
    for line in open(fn):
        k, d = (line.rstrip("\n").split("\t") + [""])[:2]
        if d and k in cands:
            c = cands.pop(k)
            d = norm_doi(d)
            if d in cands:
                t = cands[d]
                t["evidence"] = t["evidence"] + [e for e in c["evidence"] if e not in t["evidence"]]
                for mk, mv in c["meta"].items():
                    t["meta"].setdefault(mk, mv)
                t["persons"] = t.get("persons", []) + [p for p in c.get("persons", []) if p not in t.get("persons", [])]
            else:
                c["doi"] = d; c["key"] = d; c["meta"]["doi_resolved_by_title"] = True
                cands[d] = c
out = list(cands.values())
write_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz"), out)
ev = collections.Counter(e for c in out for e in c["evidence"])
strong = sum(1 for c in out if any(e.startswith("aff:") for e in c["evidence"]))
msg = f"{inst}\tcandidates={len(out)}\twith_doi={sum(1 for c in out if c['doi'])}\tstrong_aff={strong}\tevidence={dict(ev)}\trejected={dict(rejected)}"
print(msg)
with open(os.path.join(LOGS, "build_candidates.tsv"), "a") as lg:
    lg.write(msg + "\n")

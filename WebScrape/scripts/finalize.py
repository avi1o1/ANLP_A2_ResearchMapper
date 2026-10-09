"""Step M3: verification + field extraction -> WebScrape/<inst>.json

Per candidate (see build_candidates.py for evidence kinds):
  * Crossref full record (if DOI) is the canonical metadata source; channel metadata is fallback.
  * Verification of institute affiliation:
      verified      : >=1 affiliation-string evidence (any channel), OR the Crossref record's deposited
                      author affiliations classify as this IIT.
      contradicted  : person-channel only, AND Crossref has deposited affiliations, AND either the channel
                      person (matched by ORCID iD, else surname) has a deposited affiliation that is not this
                      IIT, or every author has an affiliation and none is this IIT.  -> excluded (audit file)
      unverified    : otherwise (typically publisher deposits no affiliations, e.g. Elsevier) -> kept,
                      affiliation_status = "TODO: ...".
  * Excluded Crossref types: peer-review, component, dataset, database, grant, journal-issue, journal,
    proceedings, proceedings-series, book-series, report-component, standard.
  * Year = Crossref `issued` (earliest of print/online); must lie in 2016..2026.
Field rules are documented in METHODOLOGY.md §5.

usage: python3 finalize.py <inst_key>
"""
import os, re, sys, glob, json, html, collections, datetime, unicodedata
from common import read_jsonl_gz, write_jsonl_gz, norm_doi, RAW, OUT, LOGS, YEAR_MIN, YEAR_MAX, INSTITUTES
from affil import classify, IIT as IIT_RX, OTHER_IIT_CITY

inst = sys.argv[1]
TODO = "TODO"
EXCL = {"peer-review", "component", "dataset", "database", "grant", "journal-issue", "journal", "proceedings",
        "proceedings-series", "book-series", "report-component", "standard", "journal-volume", "book-set"}
CONF_RX = re.compile(r"\b(proceedings?|conference|conf\.|symposium|workshop|congress|colloquium|meeting|summit)\b", re.I)
TAG_RX = re.compile(r"<[^>]+>")


def clean(t):
    if not t:
        return None
    t = html.unescape(TAG_RX.sub("", t))
    return re.sub(r"\s+", " ", t).strip() or None


def tkey(title):
    t = unicodedata.normalize("NFKD", clean(title) or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)[:120]


# ---------- load Crossref cache
# memory: load cached metadata only for this institute's candidate DOIs and keep only the fields used
NEED = {c["doi"] for c in read_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz")) if c.get("doi")}
KEEP = ("_q", "_src", "type", "subtype", "title", "author", "issued", "container-title", "event", "issn-type", "ISSN",
        "references-count", "is-referenced-by-count", "publisher", "ISBN", "relation", "institution", "group-title")
CR = {}
for fn in glob.glob(os.path.join(RAW, "crossref_full", "*.jsonl.gz")):
    try:
        for r in read_jsonl_gz(fn):
            if r.get("_q") not in NEED:
                continue
            if not r.get("_missing"):
                refs = r.get("reference")
                r = {k: r[k] for k in KEEP if k in r}
                if refs is not None:
                    r["reference"] = [{"DOI": x["DOI"]} if x.get("DOI") else {} for x in refs]
                # Crossref records win over DataCite / CSL fallbacks
                if r["_q"] not in CR or (CR[r["_q"]].get("_src") and not r.get("_src")):
                    CR[r["_q"]] = r
    except EOFError:
        pass
OC = {}  # optional OpenCitations fallback cache (references / counts)
_ocf = os.path.join(RAW, "opencitations", "oc.jsonl")
if os.path.exists(_ocf):
    for _l in open(_ocf):
        try:
            r = json.loads(_l); OC[r["doi"]] = r
        except json.JSONDecodeError:
            pass
# verification channels V1/V2: per-author affiliations from Springer landing pages / Europe PMC by DOI,
# converted to Crossref-like author dicts
LANDING = {}
def _rows(path):
    if path.endswith(".gz"):
        yield from read_jsonl_gz(path)
    else:
        for _l in open(path):
            try:
                yield json.loads(_l)
            except json.JSONDecodeError:
                pass


for _src, _fn in (("springer_page", "springer.jsonl"), ("europepmc_doi", "epmc_doi.jsonl.gz")):
    _p = os.path.join(RAW, "landing", _fn)
    if os.path.exists(_p):
        for _r in _rows(_p):
            if _r.get("status") == "ok" and _r.get("authors"):
                conv = []
                for _a in _r["authors"]:
                    nm = _a.get("name") or ""
                    if "," in nm:
                        fam, giv = [x.strip() for x in nm.split(",", 1)]
                    else:  # Europe PMC "Family II"
                        parts = nm.split()
                        fam, giv = (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (nm, "")
                    conv.append({"given": giv, "family": fam, "affiliation": [{"name": x} for x in _a.get("institutions", []) if x]})
                if any(a["affiliation"] for a in conv):
                    LANDING.setdefault(_r["doi"], (_src, conv))
ISSN_LOOKUP = json.load(open(os.path.join(RAW, "issn_lookup.json"))) if os.path.exists(os.path.join(RAW, "issn_lookup.json")) else {}
S2 = {}
if os.path.exists(os.path.join(RAW, "s2", "s2.jsonl")):
    for _l in open(os.path.join(RAW, "s2", "s2.jsonl")):
        try:
            _r = json.loads(_l)
        except json.JSONDecodeError:
            continue
        if "references" in _r or "citation_count" in _r:
            _k = _r["q"].split(":", 1)[1].lower()
            S2[("10.48550/arxiv." + _k) if _r["q"].startswith("ARXIV:") else _k] = _r
ROSTER_JOIN = {}  # optional: name -> joining year, from roster (used for dblp/roster person channels)

cands = list(read_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz")))


def cr_type(cr, venue):
    t = cr.get("type")
    if t == "journal-article":
        return "conference" if venue and CONF_RX.search(venue) else "journal"
    if t == "proceedings-article":
        return "conference"
    if t in ("book-chapter", "book-part", "book-section"):
        return "conference" if (cr.get("event") or (venue and CONF_RX.search(venue))) else "book-chapter"
    if t == "posted-content":
        return "preprint"
    if t in ("book", "monograph", "edited-book", "reference-book", "book-track"):
        return "book"
    if t == "dissertation":
        return "thesis"
    if t in ("report", "report-series"):
        return "report"
    return "other"


def person_contradicted(c, cr):
    """True if Crossref affiliations positively contradict the person-channel attribution."""
    auths = cr.get("author", [])
    if not auths:
        return False
    with_aff = [au for au in auths if au.get("affiliation")]
    if not with_aff:
        return False
    # locate the channel person
    names = [c["meta"].get("orcid_person"), c["meta"].get("dblp_person"), c["meta"].get("roster_person")]
    orcids = re.findall(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", " ".join(n for n in names if n))
    names += c.get("persons", [])
    bare = [re.sub(r"[\(\[].*", "", n).strip() for n in names if n]
    surnames = {b.split()[-1].lower() for b in bare if b}
    for au in auths:
        hit = (au.get("ORCID") and any(o in au["ORCID"] for o in orcids)) or ((au.get("family") or "").lower() in surnames)
        if hit and au.get("affiliation"):
            s = " | ".join(a.get("name", "") for a in au["affiliation"])
            if classify(inst, s) != "iit" and not bare_iit(s):
                return True
            return False
    # all authors carry affiliations, none is this IIT and none is a bare city-less "IIT"
    return len(with_aff) == len(auths) and not any(bare_iit(" | ".join(a.get("name", "") for a in au["affiliation"])) for au in with_aff)


def bare_iit(s):
    """'Indian Institute of Technology' with no city -> ambiguous, never a contradiction."""
    return bool(IIT_RX.search(s)) and not OTHER_IIT_CITY.search(s)


# ---------- person-level observed tenure (data-driven): years in which a channel person has an
# affiliation-VERIFIED paper. Unverified person-channel papers inside [min-1, max+1] of those years
# are tagged "likely", others "possible".
def is_verified_cand(c):
    if any(e.startswith("aff:") for e in c["evidence"]):
        return True
    cr = CR.get(c["doi"]) if c["doi"] else None
    if cr:
        for au in cr.get("author", []):
            s = " | ".join(a.get("name", "") for a in au.get("affiliation", []))
            if s and classify(inst, s) == "iit":
                return True
    return False


PERSON_YEARS = collections.defaultdict(list)
for c in cands:
    if c.get("persons") and is_verified_cand(c):
        for p in c["persons"]:
            PERSON_YEARS[p].append(c["year"])

records, rejected, stats = [], [], collections.Counter()
title_index = {}
for c in cands:
    cr = CR.get(c["doi"]) if c["doi"] else None
    m = c["meta"]
    if cr and cr.get("type") in EXCL:
        stats["excluded_type:" + cr["type"]] += 1
        continue
    if c["doi"] and re.search(r"-supplement$|\.supplement$", c["doi"]):
        stats["excluded_supplement_doi"] += 1  # supplementary-material DOIs are not publications
        continue
    # ----- year
    year = None
    if cr:
        year = ((cr.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    year = year or c["year"]
    try:
        year = int(str(year)[:4])  # CSL/DataCite sometimes give the year as a string
    except (TypeError, ValueError):
        year = None
    if not year or not (YEAR_MIN <= year <= YEAR_MAX):
        stats["out_of_window"] += 1
        continue
    # ----- affiliation verification
    ev = c["evidence"]
    aff_strings = list(m.get("aff_matched") or [])
    inst_author_idx = []
    if cr:
        for i, au in enumerate(cr.get("author", [])):
            s = " | ".join(a.get("name", "") for a in au.get("affiliation", []))
            if s and classify(inst, s) == "iit":
                inst_author_idx.append(i)
                aff_strings.append(s)
    land = LANDING.get(c["doi"]) if c["doi"] else None
    land_hit = []
    if land and not (any(e.startswith("aff:") for e in ev) or inst_author_idx):
        for au in land[1]:
            s_ = " | ".join(a["name"] for a in au["affiliation"])
            if s_ and classify(inst, s_) == "iit":
                land_hit.append(s_)
        if land_hit:
            ev = ev + ["aff:" + land[0]]
            aff_strings += land_hit
    if any(e.startswith("aff:") for e in ev) or inst_author_idx:
        status = "verified"
    elif land and person_contradicted(c, {"author": land[1]}):
        rejected.append({"key": c["key"], "title": c["title"], "year": year, "evidence": ev, "reason": f"{land[0]} affiliations contradict person-channel"})
        stats["rejected_contradicted_" + land[0]] += 1
        continue
    elif cr and person_contradicted(c, cr):
        rejected.append({"key": c["key"], "title": c["title"], "year": year, "evidence": ev, "reason": "crossref affiliations contradict person-channel"})
        stats["rejected_contradicted"] += 1
        continue
    elif any(e.startswith("aff_uncertain") for e in ev):
        status = "TODO: ambiguous affiliation string only (" + "; ".join(m.get("aff_uncertain", [])[:2]) + ")"
    else:
        tier = "possible"
        for p in c.get("persons", []):
            ys = PERSON_YEARS.get(p)
            if ys and min(ys) - 1 <= year <= max(ys) + 1:
                tier = "likely"
        stats["unverified_" + tier] += 1
        status = (f"TODO: unverified-{tier} - found via person channel ({','.join(sorted(set(ev)))}); "
                  "no affiliation metadata available to confirm")
    # ----- fields
    if cr:
        title = clean((cr.get("title") or [None])[0]) or clean(c["title"])
        authors = []
        for i, au in enumerate(cr.get("author", [])):
            nm = " ".join(x for x in [au.get("given"), au.get("family")] if x) or au.get("name")
            authors.append({"name": nm, "orcid": (au.get("ORCID") or "").replace("http://orcid.org/", "").replace("https://orcid.org/", "") or None,
                            "affiliations": [clean(a.get("name")) for a in au.get("affiliation", [])],
                            "institute_author": True if i in inst_author_idx else (None if not au.get("affiliation") else False)})
        venue = (clean((cr.get("container-title") or [None])[0]) or clean((cr.get("event") or {}).get("name"))
                 or clean(m.get("epmc_journal") or m.get("doaj_journal") or m.get("orcid_journal") or m.get("dblp_venue")))
        if not venue and cr.get("type") == "posted-content":
            inst_names = [x.get("name") for x in (cr.get("institution") or []) if x.get("name")]
            gt = cr.get("group-title")
            server = inst_names[0] if inst_names else (gt if gt and "/" not in gt and len(gt) < 40 else cr.get("publisher"))
            venue = f"{server} (preprint server)" if server else None
        typ = cr_type(cr, venue)
        issn_list = [x["value"] for x in cr.get("issn-type", [])] or cr.get("ISSN") or []
        issn = issn_list or m.get("epmc_issn") or m.get("doaj_issns") or (ISSN_LOOKUP.get(venue) if venue else None) or None
        refs_raw = cr.get("reference")
        if refs_raw:
            ref_dois = sorted({norm_doi(r["DOI"]) for r in refs_raw if r.get("DOI")} - {None, c["doi"]})
            references = ref_dois
            ref_meta = {"deposited": len(refs_raw), "with_doi": len(ref_dois), "source": "crossref"}
        elif c["doi"] in OC and OC[c["doi"]].get("references") is not None:
            references = [x for x in OC[c["doi"]]["references"] if x != c["doi"]]
            ref_meta = {"deposited": None, "with_doi": len(references), "source": "opencitations"}
        elif c["doi"] in S2 and S2[c["doi"]].get("references"):
            references = [x for x in S2[c["doi"]]["references"] if x != c["doi"]]
            ref_meta = {"deposited": S2[c["doi"]].get("reference_count"), "with_doi": len(references), "source": "semantic_scholar"}
        else:
            references = TODO
            ref_meta = {"deposited": cr.get("references-count"), "with_doi": None, "source": None,
                        "note": "reference list not deposited/open in Crossref"}
        citations = cr.get("is-referenced-by-count")
        cit_src = {"crossref": citations}
        if m.get("epmc_citedby") is not None:
            cit_src["europepmc"] = m["epmc_citedby"]
        if c["doi"] in OC and OC[c["doi"]].get("citation_count") is not None:
            cit_src["opencitations"] = OC[c["doi"]]["citation_count"]
        if c["doi"] in S2 and S2[c["doi"]].get("citation_count") is not None:
            cit_src["semantic_scholar"] = S2[c["doi"]]["citation_count"]
        if citations is None:  # e.g. CSL/DataCite records without a count
            citations = next((cit_src[k] for k in ("semantic_scholar", "opencitations", "europepmc") if cit_src.get(k) is not None), None)
        type_raw = cr.get("type")
        publisher = cr.get("publisher")
        isbn = cr.get("ISBN")
    else:
        title = clean(c["title"])
        names = m.get("epmc_authors") or m.get("doaj_authors")
        authors = [{"name": n, "orcid": None, "affiliations": [], "institute_author": None} for n in names] if names else TODO
        venue = clean(m.get("epmc_journal") or m.get("doaj_journal") or m.get("orcid_journal") or m.get("dblp_venue"))
        dt = (m.get("dblp_type") or "").lower(); ot = (m.get("orcid_type") or "").lower()
        if "inproceedings" in dt or "conference" in ot:
            typ = "conference"
        elif "article" in dt or ot == "journal-article" or m.get("epmc_journal") or m.get("doaj_journal"):
            typ = "journal"
        elif "informal" in dt or ot == "preprint" or m.get("arxiv"):
            typ = "preprint"
        else:
            typ = TODO
        issn = m.get("epmc_issn") or m.get("doaj_issns") or None
        references, ref_meta = TODO, {"note": "no DOI - references not retrievable automatically"}
        citations, cit_src = None, {}
        if m.get("epmc_citedby") is not None:
            citations = m["epmc_citedby"]; cit_src["europepmc"] = citations
        type_raw, publisher, isbn = m.get("dblp_type") or m.get("orcid_type"), None, None
    if issn:  # normalise: split joined values, format XXXX-XXXX, de-duplicate, drop malformed
        _flat = []
        for x in (issn if isinstance(issn, list) else [issn]):
            for y in re.split(r"[,;\s]+", str(x)):
                y = y.strip().upper().replace("-", "")
                if re.fullmatch(r"\d{7}[\dX]", y):
                    y = y[:4] + "-" + y[4:]
                    if y not in _flat:
                        _flat.append(y)
        issn = _flat or None
    if not issn:
        issn = TODO if typ in ("journal", TODO) else "N/A (not a journal)"
    rec = {
        "title": title or TODO,
        "authors": authors if authors else TODO,
        "year": year,
        "type": typ or TODO,
        "venue": venue or TODO,
        "issn": issn,
        "doi": ("https://doi.org/" + c["doi"]) if c["doi"] else TODO,
        "citations": citations if citations is not None else TODO,
        "references": references,
        # ---- provenance / audit fields
        "affiliation_status": status,
        "institute_affiliations_matched": sorted(set(aff_strings))[:5],
        "evidence": sorted(set(ev)),
        "type_raw": type_raw,
        "publisher": publisher,
        "isbn": isbn,
        "citations_by_source": cit_src,
        "references_meta": ref_meta,
        "pmid": m.get("pmid"),
        "arxiv": m.get("arxiv"),
        "found_via_person": c.get("persons", []),
    }
    rec["todo_fields"] = [k for k in ("title", "authors", "year", "type", "venue", "issn", "doi", "citations", "references")
                          if rec[k] == TODO] + (["affiliation"] if status != "verified" else [])
    records.append(rec)

# ----- merge DOI-less records into DOI records with the same title (±1 year)
by_title = collections.defaultdict(list)
for r in records:
    if r["doi"] != TODO:
        by_title[tkey(r["title"])].append(r)
final = []
for r in records:
    if r["doi"] == TODO:
        k = tkey(r["title"])
        twin = next((x for x in by_title.get(k, []) if abs(x["year"] - r["year"]) <= 1), None) if k else None
        if twin:
            twin["evidence"] = sorted(set(twin["evidence"]) | set(r["evidence"]))
            twin["found_via_person"] = sorted(set(twin["found_via_person"]) | set(r["found_via_person"]))
            stats["merged_nodoi_into_doi"] += 1
            continue
    final.append(r)
# ----- drop preprints that Crossref links to a published version present in the set
dois_in = {r["doi"] for r in final}
pre_dup = 0
for r in final:
    crr = CR.get(norm_doi(r["doi"])) if r["doi"] != TODO else None
    if crr and crr.get("type") == "posted-content":
        tgt = [x.get("id") for x in (crr.get("relation") or {}).get("is-preprint-of", [])]
        if any(("https://doi.org/" + norm_doi(t)) in dois_in for t in tgt if t):
            r["duplicate_of_published_version"] = True; pre_dup += 1
# preprints (posted-content / arXiv) whose title matches a non-preprint record in the set
pub_titles = collections.defaultdict(list)
for r in final:
    if r["type"] != "preprint" and isinstance(r["title"], str):
        pub_titles[tkey(r["title"])].append(r)
for r in final:
    if r["type"] == "preprint" and isinstance(r["title"], str) and not r.get("duplicate_of_published_version"):
        tw = pub_titles.get(tkey(r["title"]))
        if tw:
            tw[0]["evidence"] = sorted(set(tw[0]["evidence"]) | set(r["evidence"]))
            tw[0]["found_via_person"] = sorted(set(tw[0]["found_via_person"]) | set(r["found_via_person"]))
            tw[0].setdefault("preprint_versions", []).append(r["doi"])
            r["duplicate_of_published_version"] = True; pre_dup += 1
final = [r for r in final if not r.get("duplicate_of_published_version")]
stats["preprint_dups_dropped"] = pre_dup

# ----- duplicate registrations of the same work (found by validate.py): same normalised title,
# |year diff| <= 1, and either (a) all preprints, (b) same type and same venue, or (c) a known
# double-registration pattern (ASME 'conference-paper' twins, Angewandte German edition 'ange.',
# Inderscience '.10000…' twins). Conference vs journal versions are distinct publications -> kept.
def _tk(t):
    return tkey(t) if isinstance(t, str) else ""


def _twin(a, b):
    if a["type"] == b["type"] == "preprint":
        return True
    pat = lambda r: (r.get("type_raw") == "conference-paper" or "/ange." in r["doi"] or re.search(r"\.1000\d{4}$", r["doi"]) is not None)
    if (pat(a) or pat(b)) and a["type"] == b["type"]:
        return True
    return a["type"] == b["type"] and _tk(a["venue"]) == _tk(b["venue"]) and _tk(a["venue"]) != ""


groups = collections.defaultdict(list)
for r in final:
    if len(_tk(r["title"])) > 25:
        groups[_tk(r["title"])].append(r)
drop = set()
for g in groups.values():
    if len(g) < 2:
        continue
    # keep the record with a canonical Crossref type and most citations
    g.sort(key=lambda r: (r.get("type_raw") in ("journal-article", "proceedings-article", "book-chapter", "posted-content"),
                          r["affiliation_status"] == "verified", r["citations"] if isinstance(r["citations"], int) else -1), reverse=True)
    keep = g[0]
    for o in g[1:]:
        if id(o) in drop or abs(o["year"] - keep["year"]) > 1 or not _twin(keep, o):
            continue
        drop.add(id(o))
        keep.setdefault("duplicate_dois", []).append(o["doi"])
        keep["evidence"] = sorted(set(keep["evidence"]) | set(o["evidence"]))
        keep["found_via_person"] = sorted(set(keep["found_via_person"]) | set(o["found_via_person"]))
        if o["affiliation_status"] == "verified" and keep["affiliation_status"] != "verified":
            keep["affiliation_status"] = "verified"; keep["institute_affiliations_matched"] = o["institute_affiliations_matched"]
            keep["todo_fields"] = [f for f in keep["todo_fields"] if f != "affiliation"]
stats["duplicate_registrations_merged"] = len(drop)
final = [r for r in final if id(r) not in drop]

# ----- split main output vs. unconfirmed candidates (precision audit, METHODOLOGY.md §9):
# person-channel evidence that is dated/specific is kept when the year is consistent with the
# person's affiliation-verified years ("likely"); undated DBLP / undated ORCID evidence alone and
# the "possible" tier (audit precision ~12%) go to candidates_unconfirmed_<inst>.json.
STRONG_PERSON = {"orcid_tenure", "roster_orcid", "roster_crossref_author", "roster_arxiv", "roster_dblp"}
main, unconfirmed = [], []
for r in final:
    s_ = r["affiliation_status"]
    if s_ == "verified" or s_.startswith("TODO: ambiguous"):
        main.append(r)
    elif "unverified-likely" in s_ and STRONG_PERSON & set(r["evidence"]):
        main.append(r)
    else:
        if "possible" in s_:
            r["unconfirmed_reason"] = "tier=possible (year outside the person's affiliation-verified years)"
        elif "roster_crossref_author_loose" in r["evidence"] and not (STRONG_PERSON & set(r["evidence"])):
            r["unconfirmed_reason"] = "only loose name-match evidence (roster author search with snowballed profile)"
        else:
            r["unconfirmed_reason"] = "only undated person evidence (DBLP current affiliation / ORCID affiliation without dates)"
        unconfirmed.append(r)
stats["moved_to_unconfirmed"] = len(unconfirmed)
for lst, pref in ((unconfirmed, "U"),):
    lst.sort(key=lambda r: (r["year"], r["title"] if isinstance(r["title"], str) else ""))
    for i, r in enumerate(lst):
        r["record_id"] = f"{inst}-{pref}{i + 1:06d}"
with open(os.path.join(OUT, f"candidates_unconfirmed_{inst}.json"), "w") as f:
    json.dump({"note": "Person-channel candidates NOT included in the main file (low estimated precision). "
                       "Kept for manual follow-up; see METHODOLOGY.md §9.", "n_records": len(unconfirmed), "records": unconfirmed},
              f, ensure_ascii=False, separators=(",", ":"))
final = main
final.sort(key=lambda r: (r["year"], r["title"] if isinstance(r["title"], str) else ""))
for i, r in enumerate(final):
    r["record_id"] = f"{inst}-{i + 1:06d}"
summary = {
    "institute": INSTITUTES[inst]["name"], "ror": INSTITUTES[inst]["ror"], "window": [YEAR_MIN, YEAR_MAX],
    "generated": datetime.date.today().isoformat(), "n_records": len(final),
    "n_verified": sum(1 for r in final if r["affiliation_status"] == "verified"),
    "n_unverified_likely": sum(1 for r in final if "unverified-likely" in r["affiliation_status"]),
    "n_unconfirmed_candidates_in_separate_file": len(unconfirmed),
    "by_year": dict(sorted(collections.Counter(r["year"] for r in final).items())),
    "by_type": dict(collections.Counter(r["type"] for r in final).most_common()),
    "todo_field_counts": dict(collections.Counter(f for r in final for f in r["todo_fields"]).most_common()),
    "pipeline_stats": dict(stats), "methodology": "see WebScrape/PROCESS.md",
    "field_notes": {"year": "Crossref 'issued' (earliest of print/online)", "citations": "Crossref is-referenced-by-count at collection date; other sources in citations_by_source",
                    "references": "DOIs of referenced works (Crossref deposited reference list; OpenCitations fallback)",
                    "TODO": "value could not be established automatically - manual follow-up"},
}
# readable but compact: pretty summary, one record per line (pretty-printing every record would push the
# Kharagpur file past GitHub's 100 MB limit)
with open(os.path.join(OUT, inst + ".json"), "w") as f:
    f.write('{\n"summary": ' + json.dumps(summary, ensure_ascii=False, indent=1) + ',\n"records": [\n')
    for _i, _r in enumerate(final):
        f.write(json.dumps(_r, ensure_ascii=False, separators=(",", ":")) + (",\n" if _i < len(final) - 1 else "\n"))
    f.write("]\n}\n")
write_jsonl_gz(os.path.join(OUT, "logs", f"rejected_{inst}.jsonl.gz"), rejected)
print(json.dumps(summary, indent=1))

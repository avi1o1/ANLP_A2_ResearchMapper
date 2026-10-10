"""Turn one OpenAlex work into the compact facts the merge step needs (no network access)."""
from affil import classify, IIT, OTHER_IIT_CITY

SOURCE_TYPE_TO_TYPE = {"journal": "journal", "conference": "conference", "repository": "preprint", "ebook platform": "book-chapter",
                       "book series": "book-chapter"}
WORK_TYPE_TO_TYPE = {"book-chapter": "book-chapter", "book": "book", "preprint": "preprint", "dissertation": "thesis",
                     "report": "report", "review": None, "article": None, "letter": None, "editorial": None, "erratum": "other",
                     "paratext": "other", "dataset": "other", "peer-review": "other", "other": "other", "standard": "other"}


def short(oa_id):
    return oa_id.rsplit("/", 1)[-1] if isinstance(oa_id, str) else None


def facts(w, inst, inst_oa_id):
    """Affiliation evidence and enrichment values for institute `inst` from OpenAlex work `w`."""
    auths = []
    raw_iit = inst_match = False
    with_info = 0
    for a in w.get("authorships") or []:
        raws = [s for s in (a.get("raw_affiliation_strings") or []) if s]
        insts = [{"id": short(i.get("id")), "name": i.get("display_name"), "ror": i.get("ror"), "country": i.get("country_code")}
                 for i in (a.get("institutions") or []) if i.get("id")]
        cls = [classify(inst, s) for s in raws]
        # "Indian Institute of Technology" with no city that names another IIT: could be this IIT -> undecidable
        cls = ["uncertain" if (c is None and IIT.search(s) and not OTHER_IIT_CITY.search(s)) else c for c, s in zip(cls, raws)]
        a_raw_iit = "iit" in cls
        a_inst = any(i["id"] == inst_oa_id for i in insts)
        raw_iit |= a_raw_iit
        inst_match |= a_inst
        if raws or insts:
            with_info += 1
        auths.append({"name": (a.get("author") or {}).get("display_name") or a.get("raw_author_name"),
                      "orcid": ((a.get("author") or {}).get("orcid") or "").replace("https://orcid.org/", "") or None,
                      "openalex_author": short((a.get("author") or {}).get("id")),
                      "affiliations": raws, "institutions": insts,
                      "institute_author": True if (a_raw_iit or a_inst) else (False if (raws or insts) else None),
                      "raw_cls": cls})
    n = len(auths)
    if raw_iit:
        aff = "raw_string_match"
    elif inst_match:
        aff = "institution_match"
    elif n and with_info == n and not any("uncertain" in x["raw_cls"] for x in auths):
        aff = "contradicted"          # every author has affiliation info and none of it is this IIT
    else:
        aff = "no_info"

    src = ((w.get("primary_location") or {}).get("source") or {})
    wtype = w.get("type")
    typ = WORK_TYPE_TO_TYPE.get(wtype)
    if typ is None:  # article-like: decide by venue kind
        typ = SOURCE_TYPE_TO_TYPE.get(src.get("type"))
    pt = w.get("primary_topic") or {}
    area = None
    if pt:
        area = {"topic": pt.get("display_name"), "subfield": (pt.get("subfield") or {}).get("display_name"),
                "field": (pt.get("field") or {}).get("display_name"), "domain": (pt.get("domain") or {}).get("display_name"),
                "score": pt.get("score")}
    co = {}
    for a in auths:
        for i in a["institutions"]:
            if i["id"] != inst_oa_id:
                co[i["id"]] = i
    return {
        "openalex_id": short(w.get("id")),
        "affiliation_openalex": aff,
        "authors": auths,
        "type": typ,
        "type_openalex": wtype,
        "venue": src.get("display_name"),
        "venue_type": src.get("type"),
        "issn": src.get("issn") or None,
        "citations": w.get("cited_by_count"),
        "references_openalex": [short(x) for x in (w.get("referenced_works") or [])],
        "research_area": area,
        "coauthor_institutions": sorted(co.values(), key=lambda i: (i["country"] != "IN", i["name"] or "")),
    }

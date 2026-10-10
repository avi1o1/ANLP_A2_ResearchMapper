"""Merge OpenAlex facts, scope and ranks into a copy of the dataset.
Rules:
 * Existing values are never overwritten; only fields that are currently TODO get filled.
 * Every filled field is listed in record["filled"] = {field: source}.
 * Values that cannot be found stay TODO (or null for the new fields).
 * New OpenAlex fields (openalex_id, research_area, coauthor_institutions, references_openalex, authors_openalex,
   citations_openalex, affiliation_openalex) are added only where OpenAlex has the work.
Affiliation tiers for records that were 'TODO: unverified-likely':
 * raw_string_match  -> 'verified'   (an author's affiliation text on the paper names this IIT; same classifier
                                       and same criterion as the original pipeline's 'verified')
 * contradicted      -> 'rejected: ...' (every author has affiliation info in OpenAlex and none is this IIT);
                                       kept in the file, excluded from stats
 * institution_match / no_info -> unchanged (still TODO)
Every record also gets:
 * sci_eng_scope {in_scope: true/false/null, basis}   (scope.py)
 * quartile {quartile, sjr_year, ...} or null          (ranks.py; journals; needs the Scimago CSVs)
 * core {core_rank, core_edition, ...} or null        (ranks.py; conference papers)
 * cites_indian_inst      true/false/null  (+ cites_indian_institutions {name: n_cited_works})
       true  = the paper cites >=1 work with an Indian institution other than this IIT (OpenAlex Stage B)
       false = OpenAlex has the paper's reference list and none of the cited works qualifies
       null  = no OpenAlex reference list, or the paper's Stage-B batch was not fetched
 * cited_by_indian_inst   true/false/null  (+ cited_by_indian_institutions, cited_by_indian_works)
       true  = >=1 citing work with an Indian institution other than this IIT (OpenAlex Stage C)
       false = none among OpenAlex's citing works; null = not in OpenAlex or batch not fetched
output: out/<inst>_enriched.json  (same layout: {summary, records})
usage: python merge.py <inst_key> [...]"""
import os, sys, json, collections as C
from oa import read_jsonl, norm_doi, CACHE, OUT, DATA, INST
from oa_extract import facts
from scope import scope
from ranks import quartile, core_rank, SJR

REJECT = "rejected: OpenAlex affiliations of all authors name other institutions"


def is_todo(v):
    return isinstance(v, str) and v.startswith("TODO")


def lookup_tables(inst):
    works = {}
    for fn in (f"a_works_{inst}.jsonl", f"a2_works_{inst}.jsonl"):
        for w in read_jsonl(os.path.join(CACHE, fn)):
            if fn.startswith("a2_"):
                works[("rid", w["_record_id"])] = w
            elif norm_doi(w.get("doi")):
                works[norm_doi(w["doi"])] = w
    refdoi = {}
    qfn = os.path.join(CACHE, "ref_queried.txt")
    for i in (open(qfn).read().split() if os.path.exists(qfn) else []):
        refdoi[i] = None                     # queried; None unless OpenAlex returned a DOI below
    for row in read_jsonl(os.path.join(CACHE, "ref_dois.jsonl")):
        refdoi[row["id"]] = row["doi"]
    return works, refdoi


def find_work(r, works):
    if not is_todo(r["doi"]) and norm_doi(r["doi"]) in works:
        return works[norm_doi(r["doi"])], "doi"
    for d in r.get("duplicate_dois") or []:
        if norm_doi(d) in works:
            return works[norm_doi(d)], "doi"
    if ("rid", r["record_id"]) in works:
        return works[("rid", r["record_id"])], "title"
    return None, None


def apply_openalex(r, w, via, inst, refdoi, filled, stats):
    f = facts(w, inst, INST[inst]["oa"])
    r["openalex_id"] = f["openalex_id"]
    r["openalex_match"] = via
    r["affiliation_openalex"] = f["affiliation_openalex"]
    r["research_area"] = f["research_area"]
    r["coauthor_institutions"] = f["coauthor_institutions"]
    r["references_openalex"] = f["references_openalex"]
    r["citations_openalex"] = f["citations"]
    r["authors_openalex"] = [{"name": a["name"], "openalex_author": a["openalex_author"], "orcid": a["orcid"],
                              "institutions": [i["id"] for i in a["institutions"]], "institute_author": a["institute_author"],
                              "affiliations": a["affiliations"]}
                             for a in f["authors"]]
    if via == "title" and is_todo(r["doi"]) and norm_doi(w.get("doi")):
        r["doi"] = "https://doi.org/" + norm_doi(w["doi"]); filled["doi"] = "openalex_title_match"
    if is_todo(r["affiliation_status"]):
        if f["affiliation_openalex"] == "raw_string_match":
            r["affiliation_status"] = "verified"
            r["evidence"] = list(r.get("evidence") or []) + ["aff:openalex"]
            r["institute_affiliations_matched"] = sorted({s for a in f["authors"] for s, c in zip(a["affiliations"], a["raw_cls"]) if c == "iit"})
            filled["affiliation"] = "openalex_raw_affiliation"
        elif f["affiliation_openalex"] == "contradicted":
            r["affiliation_status"] = REJECT
            filled["affiliation"] = "openalex_contradicted"
    if is_todo(r["type"]) and f["type"]:
        r["type"] = f["type"]; filled["type"] = "openalex"
    if is_todo(r["venue"]) and f["venue"]:
        r["venue"] = f["venue"]; filled["venue"] = "openalex"
    if is_todo(r["issn"]) and f["issn"]:
        r["issn"] = f["issn"]; filled["issn"] = "openalex"
    if is_todo(r["authors"]) and f["authors"]:
        r["authors"] = [{"name": a["name"], "orcid": a["orcid"], "affiliations": a["affiliations"],
                         "institute_author": a["institute_author"]} for a in f["authors"]]
        filled["authors"] = "openalex"
    if is_todo(r["citations"]) and isinstance(f["citations"], int):
        r["citations"] = f["citations"]; r["citations_source"] = "openalex"; filled["citations"] = "openalex"
    if is_todo(r["references"]) and f["references_openalex"]:
        ids = f["references_openalex"]
        if all(i in refdoi for i in ids):   # every cited work was looked up (refdoi[i] is None if it has no DOI)
            dois = sorted({refdoi[i] for i in ids if refdoi[i]})
            r["references"] = dois
            r["references_meta"] = {"source": "openalex", "openalex_refs": len(ids), "with_doi": len(dois),
                                    "note": "cited works without a DOI, or deleted from OpenAlex, are not listed"}
            filled["references"] = "openalex"


def load_indian_links(inst):
    """Stage B/C results. Returns (covered_b, covered_c, cited, citing):
    covered_*: our OpenAlex ids whose batch was fetched in that stage;
    cited[X] / citing[Y]: Indian work -> {doi, year, institutions:[(id, name, country)], referenced_works?}."""
    ours = sorted({w["id"].rsplit("/", 1)[-1] for fn in (f"a_works_{inst}.jsonl", f"a2_works_{inst}.jsonl")
                   for w in read_jsonl(os.path.join(CACHE, fn))})
    batches = [ours[i:i + 100] for i in range(0, len(ours), 100)]
    out = []
    for stage in ("b", "c"):
        dfn = os.path.join(CACHE, f"{stage}_done_{inst}.txt")
        done = set(open(dfn).read().split()) if os.path.exists(dfn) else set()
        out.append({i for b in batches if b[0] in done for i in b})
    for stage in ("b", "c"):
        out.append({row["id"]: row for row in read_jsonl(os.path.join(CACHE, f"{stage}_works_{inst}.jsonl"))})
    return out


def other_indian(work, own_id):
    """Indian institutions on `work` other than our own IIT."""
    return sorted({(i[0], i[1]) for i in work["institutions"] if i[2] == "IN" and i[0] != own_id})


def apply_indian_links(r, links, own_id, cited_by_index):
    covered_b, covered_c, cited, _ = links
    p = r.get("openalex_id")
    # cites_indian_inst: needs our reference list from OpenAlex and a fetched Stage-B batch
    if p in covered_b and r.get("references_openalex"):
        # x != p: OpenAlex occasionally lists a work among its own references (a self-citation is not a link)
        insts = C.Counter(n for x in r["references_openalex"] if x in cited and x != p for _, n in other_indian(cited[x], own_id))
        r["cites_indian_inst"] = bool(insts)
        r["cites_indian_institutions"] = dict(insts.most_common())
    else:
        r["cites_indian_inst"] = None
    # cited_by_indian_inst: needs a fetched Stage-C batch (OpenAlex's citing works)
    if p in covered_c:
        ys = [y for y in cited_by_index.get(p, []) if y["id"] != p]      # ignore OpenAlex self-references
        insts = C.Counter(n for y in ys for _, n in other_indian(y, own_id))
        r["cited_by_indian_inst"] = bool(insts)
        r["cited_by_indian_institutions"] = dict(insts.most_common())
        r["cited_by_indian_works"] = sum(1 for y in ys if other_indian(y, own_id))
    else:
        r["cited_by_indian_inst"] = None


def merge(inst):
    src = json.load(open(os.path.join(DATA, inst + ".json"), encoding="utf8"))
    works, refdoi = lookup_tables(inst)
    links = load_indian_links(inst)
    cited_by_index = C.defaultdict(list)          # our id -> Indian works citing it
    for y in links[3].values():
        for x in y.get("referenced_works") or []:
            cited_by_index[x].append(y)
    stats = C.Counter()
    for r in src["records"]:
        filled = {}
        w, via = find_work(r, works)
        stats["matched_" + via if w else "no_openalex_match"] += 1
        if w:
            apply_openalex(r, w, via, inst, refdoi, filled, stats)
        apply_indian_links(r, links, INST[inst]["oa"], cited_by_index)
        stats["cites_indian_inst_" + str(r["cites_indian_inst"])] += 1
        stats["cited_by_indian_inst_" + str(r["cited_by_indian_inst"])] += 1
        r["sci_eng_scope"] = scope(r, r.get("research_area"))
        r["quartile"] = quartile(r["issn"], r["year"]) if r["type"] == "journal" else None
        r["core"] = core_rank(r["venue"], r["year"]) if r["type"] == "conference" else None
        stats["scope_" + str(r["sci_eng_scope"]["in_scope"])] += 1
        stats["has_quartile"] += bool(r["quartile"])
        stats["has_core_rank"] += bool(r["core"])
        if filled:
            r["filled"] = filled
            for k in filled:
                stats["filled_" + k + ":" + filled[k]] += 1
        r["todo_fields"] = [k for k in r["todo_fields"]
                            if (k == "affiliation" and is_todo(r["affiliation_status"])) or
                               (k != "affiliation" and is_todo(r.get(k)))]
    todo = C.Counter(k for r in src["records"] for k in r["todo_fields"])
    src["summary"]["enrichment"] = {
        "source": "OpenAlex (api.openalex.org), fetched 2026-10-09; CORE portal exports; Scimago SJR "
                  + ("years " + ",".join(map(str, sorted(SJR))) if SJR else "(not yet available)"),
        "rules": "see Enrichment/scripts/merge.py, scope.py, ranks.py", "counts": dict(sorted(stats.items())),
        "todo_field_counts_after": dict(todo.most_common()),
        "affiliation_status_after": dict(C.Counter(r["affiliation_status"].split(" (")[0][:60] for r in src["records"]).most_common())}
    fn = os.path.join(OUT, inst + "_enriched.json")
    with open(fn, "w", encoding="utf8") as fh:
        fh.write('{"summary": ' + json.dumps(src["summary"], ensure_ascii=False, indent=1) + ',\n"records": [\n')
        fh.write(",\n".join(json.dumps(r, ensure_ascii=False) for r in src["records"]))
        fh.write("\n]}\n")
    print("=====", inst)
    for k, v in sorted(stats.items()):
        print(f"  {k:45s} {v}")
    print("  TODO fields after:", dict(todo.most_common()))
    print("  affiliation_status after:", src["summary"]["enrichment"]["affiliation_status_after"])


if __name__ == "__main__":
    for i in sys.argv[1:]:
        merge(i)

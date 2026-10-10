"""Integrity checks of out/<inst>_enriched.json against the original WebScrape/<inst>.json (no network access).
 1. Same records, same order, same record_id.
 2. No original non-TODO value changed, except the documented ones:
      affiliation_status TODO -> verified / rejected (then evidence gets "aff:openalex" appended and
      institute_affiliations_matched is refreshed); todo_fields shrinks; references_meta when references filled.
 3. Every original TODO value that now has a value is listed in record["filled"], and vice versa.
 4. todo_fields lists exactly the fields that are still TODO.
 5. quartile: only on journal papers, taken from the Scimago file of the publication year (2026 -> 2025).
 6. core: only on conference papers.
 7. cites/cited_by flags: true only with at least one named institution; null never carries institutions.
usage: python verify.py <inst_key> [...]"""
import os, sys, json, collections as C
from oa import DATA, OUT

ALLOWED_CHANGE = {"affiliation_status", "evidence", "institute_affiliations_matched", "todo_fields", "references_meta"}
FIELDS = ["title", "authors", "year", "type", "venue", "issn", "doi", "citations", "references"]


def is_todo(v):
    return isinstance(v, str) and v.startswith("TODO")


def load_enriched(inst):
    recs = []
    with open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line.startswith('{"title"'):
                recs.append(json.loads(line))
    return recs


for inst in sys.argv[1:]:
    orig = json.load(open(os.path.join(DATA, inst + ".json"), encoding="utf8"))["records"]
    new = load_enriched(inst)
    err = C.Counter()
    examples = {}

    def bad(kind, rid):
        err[kind] += 1
        examples.setdefault(kind, rid)

    if len(orig) != len(new):
        bad("record_count_differs", f"{len(orig)} vs {len(new)}")
    for o, n in zip(orig, new):
        rid = o["record_id"]
        if n["record_id"] != rid:
            bad("record_order", rid); continue
        filled = n.get("filled", {})
        for k, v in o.items():
            if k in ALLOWED_CHANGE or k in FIELDS:
                continue
            if n.get(k) != v:
                bad("changed_" + k, rid)
        for k in FIELDS:
            if is_todo(o[k]):
                if not is_todo(n[k]) and k not in filled:
                    bad("filled_without_log_" + k, rid)
                if is_todo(n[k]) and k in filled:
                    bad("logged_but_still_todo_" + k, rid)
            elif n[k] != o[k]:
                bad("overwrote_existing_" + k, rid)
        st_o, st_n = o["affiliation_status"], n["affiliation_status"]
        if st_o != st_n:
            if not is_todo(st_o) or "affiliation" not in filled:
                bad("affiliation_changed_without_log", rid)
            if not (st_n == "verified" or st_n.startswith("rejected:")):
                bad("affiliation_unexpected_value", rid)
        elif o.get("evidence") != n.get("evidence"):
            bad("evidence_changed_without_affiliation_change", rid)
        if o.get("references_meta") != n.get("references_meta") and "references" not in filled:
            bad("references_meta_changed_without_fill", rid)
        still = {k for k in FIELDS if is_todo(n[k])} | ({"affiliation"} if is_todo(st_n) else set())
        if set(n["todo_fields"]) - still:
            bad("todo_fields_lists_filled_field", rid)
        if (still & set(o["todo_fields"])) - set(n["todo_fields"]):
            bad("todo_fields_missing_open_field", rid)
        q = n.get("quartile")
        if q:
            if n["type"] != "journal":
                bad("quartile_on_non_journal", rid)
            if q["sjr_year"] != min(n["year"], 2025):
                bad("quartile_wrong_year", rid)
        if n.get("core") and n["type"] != "conference":
            bad("core_on_non_conference", rid)
        for flag, insts in (("cites_indian_inst", "cites_indian_institutions"), ("cited_by_indian_inst", "cited_by_indian_institutions")):
            v = n.get(flag)
            if v is True and not n.get(insts):
                bad(flag + "_true_without_institutions", rid)
            if v is False and n.get(insts):
                bad(flag + "_false_with_institutions", rid)
            if v is None and n.get(insts):
                bad(flag + "_null_with_institutions", rid)
    print(f"===== {inst}: {len(new)} records checked")
    if not err:
        print("  ALL CHECKS PASSED")
    for k, v in sorted(err.items()):
        print(f"  FAIL {k}: {v}  (e.g. {examples[k]})")

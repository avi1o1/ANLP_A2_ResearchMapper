"""Export the submission CSV in the brief's column format (DPCN_Instruction_Note section 5), plus extra columns.
One row per (paper, faculty member). A paper with no identifiable faculty member gets one row with
author = the institute name (decided 2026-10-10, after ORCID / name / department matching).
Required columns: group, institution, author, title, year, type, journal_name, issn, doi, citations, quartile,
                  coauthor_institutes, cites_indian_inst, cited_by_indian_inst
  type          journal / conference as in the brief; other kinds keep their own label (book-chapter, preprint, ...)
  issn          ';'-joined
  quartile      Scimago SJR best quartile (Q1..Q4) for journal papers; 'CORE A*' / 'CORE A' / ... for conference papers
  coauthor_institutes  ';'-joined INDIAN co-author institutions other than this IIT (the brief: "for Indian
                connections"); all co-author institutions are in the extra column coauthor_institutes_all
  cites_indian_inst / cited_by_indian_inst   TRUE / FALSE / blank (blank = could not be determined)
Unknown values are left blank (never the string TODO, never a guess).
Extra columns: department, faculty_match, faculty_source, affiliation_status, in_scope, scope_basis,
  research_field, research_domain, record_id, openalex_id, quartile_basis
Outputs: out/group3_data.csv      papers with affiliation_status 'verified' and in_scope true (the submission)
         out/group3_data_all.csv  every paper except 'rejected' ones (for the team to filter differently)
usage: python export_csv.py"""
import os, csv, json, collections as C
from oa import OUT

INSTS = {"iit_kharagpur": "IIT Kharagpur", "iit_roorkee": "IIT Roorkee"}
REQUIRED = ["group", "institution", "author", "title", "year", "type", "journal_name", "issn", "doi", "citations",
            "quartile", "coauthor_institutes", "cites_indian_inst", "cited_by_indian_inst"]
EXTRA = ["department", "faculty_match", "faculty_source", "affiliation_status", "in_scope", "scope_basis",
         "research_field", "research_domain", "record_id", "openalex_id", "quartile_basis", "coauthor_institutes_all"]


def val(v):
    if v is None or (isinstance(v, str) and v.startswith("TODO")):
        return ""
    return v


def tf(v):
    return "" if v is None else ("TRUE" if v else "FALSE")


def rows_for(r, inst_name):
    q = r.get("quartile")
    core = r.get("core")
    if q:
        quart, basis = q["quartile"], f"Scimago SJR {q['sjr_year']}"
    elif core:
        quart, basis = "CORE " + core["core_rank"], f"{core['core_edition']} ({core['core_match']})"
    else:
        quart, basis = "", ""
    co = r.get("coauthor_institutions") or []
    area = r.get("research_area") or {}
    base = {
        "group": 3, "institution": inst_name, "title": val(r["title"]), "year": val(r["year"]), "type": val(r["type"]),
        "journal_name": val(r["venue"]), "issn": ";".join(r["issn"]) if isinstance(r["issn"], list) else "",
        "doi": val(r["doi"]), "citations": val(r["citations"]), "quartile": quart,
        "coauthor_institutes": ";".join(i["name"] for i in co if i.get("country") == "IN" and i.get("name")),
        "cites_indian_inst": tf(r.get("cites_indian_inst")), "cited_by_indian_inst": tf(r.get("cited_by_indian_inst")),
        "affiliation_status": "verified" if r["affiliation_status"] == "verified" else val(r["affiliation_status"]) or "unverified",
        "in_scope": tf(r["sci_eng_scope"]["in_scope"]), "scope_basis": r["sci_eng_scope"]["basis"],
        "research_field": area.get("field") or "", "research_domain": area.get("domain") or "",
        "record_id": r["record_id"], "openalex_id": r.get("openalex_id") or "", "quartile_basis": basis,
        "coauthor_institutes_all": ";".join(i["name"] for i in co if i.get("name")),
    }
    if not r["faculty"]:
        return [dict(base, author=inst_name, department="", faculty_match="none (institute)", faculty_source="")]
    return [dict(base, author=f["name"], department=f["department"], faculty_match=f["match"],
                 faculty_source=f.get("person_source", "")) for f in r["faculty"]]


def main():
    sub, allr = [], []
    stats = C.Counter()
    for inst, name in INSTS.items():
        with open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8") as fh:
            for line in fh:
                s = line.strip().rstrip(",")
                if not s.startswith('{"title"'):
                    continue
                r = json.loads(s)
                if r["affiliation_status"].startswith("rejected"):
                    stats[name + " rejected (not exported)"] += 1
                    continue
                rows = rows_for(r, name)
                allr += rows
                if r["affiliation_status"] == "verified" and r["sci_eng_scope"]["in_scope"] is True:
                    sub += rows
                    stats[name + " papers in submission"] += 1
                    stats[name + " papers credited to institute only"] += not r["faculty"]
    for fn, rows in (("group3_data.csv", sub), ("group3_data_all.csv", allr)):
        with open(os.path.join(OUT, fn), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=REQUIRED + EXTRA)
            w.writeheader()
            w.writerows(rows)
        print(f"{fn}: {len(rows)} rows")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

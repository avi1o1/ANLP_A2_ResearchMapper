"""Which research fields are in scope. Stored per record as record["sci_eng_scope"] = {in_scope, basis}
(the field name is kept from the first rule so every script keeps working).

SCOPE_MODE = "all"      (team decision, 2026-10-10) every field is in scope: Physical, Life, Health and Social
                        Sciences, and papers without an OpenAlex topic. NOTE: the TAs' clarification (2026-10-09) said
                        to focus on engineering and science papers; switch back with SCOPE_MODE = "sci_eng".
SCOPE_MODE = "sci_eng"  the TA rule:
  1. OpenAlex primary topic domain: Physical Sciences, Life Sciences -> in; Health Sciences, Social Sciences -> out.
  2. No OpenAlex topic: the roster departments of the faculty who found the record ('[roster:<dept>]' tags).
     In/out only if every tagged department agrees; mixed, ambiguous or no department -> None (unknown).
After changing SCOPE_MODE re-run Enrichment/scripts/rebuild.sh and Analysis/scripts/run_all.sh."""
import re

SCOPE_MODE = "all"

IN_DOMAINS = {"Physical Sciences", "Life Sciences"}
OUT_DOMAINS = {"Health Sciences", "Social Sciences"}
ALL_DOMAINS = IN_DOMAINS | OUT_DOMAINS
OPENALEX_DOMAIN_IDS = {"all": None, "sci_eng": "3|1"}     # for OpenAlex filters (3 Physical, 1 Life Sciences)

DEPT_OUT = {
    "Academy of Classical and Folk Arts", "Centre of Excellence for Indian Knowledge Systems",
    "Centre of Excellence in Public Policy, Law and Governance", "Education", "Humanities and Social Sciences",
    "Rajiv Gandhi School of Intellectual Property Law", "Rekhi Centre of Excellence for the Science of Happiness",
    "Vinod Gupta School of Management", "Management Studies", "Centre for Indian Knowledge Systems",
    "Rajendra Mishra School of Engg Entrepreneurship", "Dr B C Roy Multi Speciality Medical Research Centre",
}
DEPT_UNKNOWN = {
    "Architecture and Regional Planning", "Architecture and Planning", "Design", "Continuing Education Centre and QIP Centre",
    "Institute Computer Centre", "Unknown unit (institute-wide list 2019)", "School of Medical Science and Technology",
    "Centre of Excellence in Affordable Healthcare",
}


def dept_verdict(d):
    if d in DEPT_OUT:
        return False
    if d in DEPT_UNKNOWN:
        return None
    return True


def scope(record, research_area):
    dom = (research_area or {}).get("domain")
    if SCOPE_MODE == "all":
        return {"in_scope": True, "basis": "all fields in scope" + (": openalex_domain:" + dom if dom else ": no OpenAlex topic")}
    if dom in IN_DOMAINS:
        return {"in_scope": True, "basis": "openalex_domain:" + dom}
    if dom in OUT_DOMAINS:
        return {"in_scope": False, "basis": "openalex_domain:" + dom}
    depts = sorted({m for p in record.get("found_via_person") or [] for m in re.findall(r"\[roster:([^\]]+)\]", p)})
    if not depts:
        return {"in_scope": None, "basis": "unknown: no OpenAlex topic, no roster department"}
    v = {dept_verdict(d) for d in depts}
    if v == {True}:
        return {"in_scope": True, "basis": "department:" + "; ".join(depts)}
    if v == {False}:
        return {"in_scope": False, "basis": "department:" + "; ".join(depts)}
    return {"in_scope": None, "basis": "unknown: departments " + "; ".join(depts)}

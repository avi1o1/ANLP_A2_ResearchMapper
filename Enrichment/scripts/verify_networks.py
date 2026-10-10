"""Checks of the three network files against the brief and against the dataset (no network access).
citation_network.csv
  required columns present; no self-citations; no duplicate (source, target) pairs; year filled
  internal edges: both ends are submission papers; cross_inst TRUE exactly when the institutes differ
  external edges: the external side never lists the IIT(s) of the other side
  consistency with the dataset flags (submission papers, by OpenAlex id):
    cites_indian_inst FALSE  => no outgoing external edge;  TRUE => >= 1 outgoing edge, external or internal
    cited_by_indian_inst FALSE => no incoming external edge; TRUE => >= 1 incoming edge, external or internal
    (a cited/citing paper that is itself in our dataset - e.g. a Roorkee paper, or a Kharagpur paper with an IISc
    co-author - makes the flag TRUE but is stored once, as an internal edge)
  a blank year (OpenAlex has no year for the external work) is reported, not failed
  joint Kharagpur-Roorkee papers are reported separately: each institute's flag counts the OTHER IIT as an Indian
  institution, but in the network the joint paper belongs to both IITs, so a work of only one of them is not external
authorship_network.csv
  required columns present; every row has >= 1 faculty endpoint; no self-pairs; papers are submission papers
indian_connections.csv
  required columns present; no institute is its own partner; no duplicate rows;
  every joint Kharagpur-Roorkee submission paper is counted in both directions of that pair
usage: python verify_networks.py"""
import os, csv, json, collections as C
from oa import OUT, norm_doi

csv.field_size_limit(10 ** 8)
NAMES = {"iit_kharagpur": "IIT Kharagpur", "iit_roorkee": "IIT Roorkee"}
err, info = C.Counter(), C.Counter()
MISS = []


def bad(kind, n=1):
    err[kind] += n


def read(fn):
    with open(os.path.join(OUT, fn), encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return rd.fieldnames, list(rd)


# submission papers
sub, flags_cites, flags_citedby, insts_of = set(), {}, {}, C.defaultdict(set)
joint = C.defaultdict(set)
for inst, name in NAMES.items():
    with open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8") as fh:
        for line in fh:
            s = line.strip().rstrip(",")
            if not s.startswith('{"title"'):
                continue
            r = json.loads(s)
            if r["affiliation_status"] != "verified" or r["sci_eng_scope"]["in_scope"] is not True:
                continue
            d = norm_doi(r["doi"]) if not str(r["doi"]).startswith("TODO") else None
            if d:
                sub.add(d)
                joint[d].add(name)
            if r.get("openalex_id"):
                insts_of[r["openalex_id"]].add(name)
                flags_cites[r["openalex_id"]] = r.get("cites_indian_inst")
                flags_citedby[r["openalex_id"]] = r.get("cited_by_indian_inst")
joint_dois = {d for d, s in joint.items() if len(s) == 2}

# ---------------- citation network
cols, rows = read("citation_network.csv")
for c in ["source_doi", "target_doi", "source_inst", "target_inst", "year"]:
    if c not in cols:
        bad("citation: missing column " + c)
seen = set()
out_from, in_to, int_out, int_in = C.Counter(), C.Counter(), C.Counter(), C.Counter()
for r in rows:
    key = (r["source_openalex"] or r["source_doi"], r["target_openalex"] or r["target_doi"])
    if key in seen:
        bad("citation: duplicate edge")
    seen.add(key)
    if key[0] == key[1]:
        bad("citation: self-citation")
    if not r["year"]:
        info["citation: year unknown (blank)"] += 1
    info["citation " + r["edge_type"]] += 1
    if r["edge_type"] == "internal":
        int_out[r["source_openalex"]] += 1
        int_in[r["target_openalex"]] += 1
        for side in ("source", "target"):
            d = norm_doi(r[side + "_doi"])
            if d and d not in sub:
                bad("citation: internal edge end not a submission paper")
        if (r["cross_inst"] == "TRUE") != (r["source_inst"] != r["target_inst"]):
            bad("citation: cross_inst wrong on internal edge")
    elif r["edge_type"] == "out_to_indian":
        if any(n in r["target_inst"].split(";") for n in r["source_inst"].split(";")):
            bad("citation: external target lists the source's own IIT")
        out_from[r["source_openalex"]] += 1
    elif r["edge_type"] == "in_from_indian":
        if any(n in r["source_inst"].split(";") for n in r["target_inst"].split(";")):
            bad("citation: external source lists the target's own IIT")
        in_to[r["target_openalex"]] += 1
    else:
        bad("citation: unknown edge_type")
for w, v in flags_cites.items():
    if v is True and not out_from[w]:
        info["cites_indian_inst TRUE via internal edges only"] += 1
        if not int_out[w]:
            if len(insts_of[w]) == 2:
                info["joint paper: cites_indian_inst TRUE from one IIT's view, no edge"] += 1
            else:
                bad("flag cites_indian_inst TRUE but no outgoing edge at all"); MISS.append(("cites", w))
    if v is False and out_from[w]:
        bad("flag cites_indian_inst FALSE but outgoing external edges exist")
for w, v in flags_citedby.items():
    if v is True and not in_to[w]:
        info["cited_by_indian_inst TRUE via internal edges only"] += 1
        if not int_in[w]:
            if len(insts_of[w]) == 2:
                info["joint paper: cited_by_indian_inst TRUE from one IIT's view, no edge"] += 1
            else:
                bad("flag cited_by_indian_inst TRUE but no incoming edge at all"); MISS.append(("cited_by", w))
    if v is False and in_to[w]:
        bad("flag cited_by_indian_inst FALSE but incoming external edges exist")

# ---------------- authorship network
cols, rows = read("authorship_network.csv")
for c in ["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year"]:
    if c not in cols:
        bad("authorship: missing column " + c)
for r in rows:
    if r["a_is_faculty"] != "TRUE" and r["b_is_faculty"] != "TRUE":
        bad("authorship: row without a faculty endpoint")
    if r["author_a_id"] == r["author_b_id"]:
        bad("authorship: self-pair")
    d = norm_doi(r["paper_doi"])
    if d and d not in sub:
        bad("authorship: paper not in submission set")
    info["authorship rows"] += 1
    info["authorship faculty-faculty"] += r["a_is_faculty"] == r["b_is_faculty"] == "TRUE"
    info["authorship cross_inst TRUE"] += r["cross_inst"] == "TRUE"

# ---------------- indian connections
cols, rows = read("indian_connections.csv")
for c in ["your_inst", "partner_inst", "shared_papers", "total_citations"]:
    if c not in cols:
        bad("connections: missing column " + c)
pairs = set()
for r in rows:
    if r["your_inst"] == r["partner_inst"]:
        bad("connections: institute is its own partner")
    k = (r["your_inst"], r["partner_openalex"])
    if k in pairs:
        bad("connections: duplicate row")
    pairs.add(k)
    if (r["your_inst"], r["partner_inst"]) in {("IIT Kharagpur", "Indian Institute of Technology Roorkee"),
                                               ("IIT Roorkee", "Indian Institute of Technology Kharagpur")}:
        info[f"connections {r['your_inst']} -> other IIT shared_papers"] = int(r["shared_papers"])
info["joint Kharagpur-Roorkee submission papers (by DOI)"] = len(joint_dois)
for k, v in info.items():
    if k.startswith("connections") and v < len(joint_dois):
        bad("connections: KGP-Roorkee shared_papers below the number of joint papers")

for k, v in sorted(info.items()):
    print(f"  {k}: {v}")
print("ALL NETWORK CHECKS PASSED" if not err else "FAILURES:")
for k, v in sorted(err.items()):
    print(f"  FAIL {k}: {v}")
for m in MISS[:10]:
    print("    e.g.", m)

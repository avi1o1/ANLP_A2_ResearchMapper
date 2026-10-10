"""Build the three network files of the brief (DPCN_Instruction_Note sections 6-7) from the enriched data.
Papers used: the submission set = affiliation 'verified' AND sci_eng_scope.in_scope true (same as group3_data.csv).
A paper in both datasets (joint Kharagpur-Roorkee paper) is one node whose institute is 'IIT Kharagpur;IIT Roorkee'.

out/citation_network.csv  - directed edges "source paper cites target paper"
  required: source_doi, target_doi, source_inst, target_inst, year (= year of the citing paper)
  extra:    source_openalex, target_openalex, edge_type, cross_inst
  edge_type internal      both papers in our submission set (KGP->KGP, Roorkee->Roorkee, KGP<->Roorkee)
            out_to_indian our paper cites a work with an Indian institution other than ours (OpenAlex stage B)
            in_from_indian a work with an Indian institution other than ours cites our paper (OpenAlex stage C)
  Internal citations come from our reference lists (Crossref DOIs and OpenAlex ids). For external Indian works,
  *_inst lists only their Indian institutions other than the IIT on the other side; works whose only Indian
  institution is our own IIT are not external (they are our institute's papers missing from the dataset) and are
  left out. Works without a DOI keep a blank DOI and their OpenAlex id.

out/authorship_network.csv - undirected co-authorship edges, one row per (pair, paper)
  required: author_a, author_b, paper_doi, inst_a, inst_b, year
  extra:    author_a_id, author_b_id, a_is_faculty, b_is_faculty, cross_inst, n_authors
  Every pair on a paper in which at least one author is one of our faculty (the 'faculty' links of faculty.py);
  the faculty member's entry in the author list is found by ORCID, else by compatible name.
  Faculty nodes: roster name / roster id. Other authors: OpenAlex author id and name, institutions from OpenAlex.
  Papers with more than MAX_AUTHORS authors are skipped (one 2,000-author collaboration paper would add ~2M edges);
  their number is printed. Papers without OpenAlex author data use the Crossref author list (names only).
  cross_inst = TRUE when the two authors share no institution.

out/indian_connections.csv - one row per (our institute, Indian partner institution)
  required: your_inst, partner_inst, shared_papers, total_citations
  extra:    citations_from_partner, citations_to_partner, partner_kind, partner_openalex
  shared_papers          our submission papers with a co-author from the partner (OpenAlex institutions)
  total_citations        citations received by those shared papers (our dataset's citation counts)
  citations_from_partner citing works by the partner -> our papers (in-flow, citation edges)
  citations_to_partner   our papers -> works by the partner (out-flow, citation edges)
  partner_kind           from the institution name: IIT / NIT / IIIT / IISER / IISc / CSIR / DAE / AIIMS /
                         University / Other (pattern-based; used to flag cross-cluster links)
usage: python build_networks.py"""
import os, re, csv, json, collections as C
from oa import OUT, CACHE, INST, read_jsonl, norm_doi
from faculty import compatible, load_roster

MAX_AUTHORS = 50
NAMES = {k: v["name"] for k, v in INST.items()}           # iit_kharagpur -> IIT Kharagpur
OWN_OA = {v["oa"]: v["name"] for v in INST.values()}      # I145894827 -> IIT Kharagpur


def kind(name):
    n = name or ""
    for k, pat in [("IISc", r"Indian Institute of Science\b(?!.*Education)"), ("IISER", r"Science Education and Research|\bIISER\b"),
                   ("IIIT", r"Information Technology|\bIIIT"), ("IIT", r"Indian Institute of Technology|\bIIT\b"),
                   ("NIT", r"National Institute of Technology|\bNIT\b"), ("CSIR", r"\bCSIR\b|Council of Scientific"),
                   ("DAE", r"Bhabha|Atomic|Indira Gandhi Centre|Raja Ramanna|Tata Institute of Fundamental|Saha Institute|"
                           r"Institute of Physics, Bhubaneswar|NISER|Homi Bhabha"),
                   ("AIIMS", r"All India Institute of Medical"), ("University", r"Universit")]:
        if re.search(pat, n):
            return k
    return "Other"


def load_submission():
    papers = {}     # node key -> paper
    for inst, name in NAMES.items():
        with open(os.path.join(OUT, inst + "_enriched.json"), encoding="utf8") as fh:
            for line in fh:
                s = line.strip().rstrip(",")
                if not s.startswith('{"title"'):
                    continue
                r = json.loads(s)
                if r["affiliation_status"] != "verified" or r["sci_eng_scope"]["in_scope"] is not True:
                    continue
                doi = norm_doi(r["doi"]) if not str(r["doi"]).startswith("TODO") else None
                key = doi or r.get("openalex_id") or r["record_id"]
                p = papers.setdefault(key, {"doi": doi, "oa": r.get("openalex_id"), "insts": set(), "year": r["year"],
                                            "refs_doi": set(), "refs_oa": set(), "citations": None, "records": []})
                p["insts"].add(name)
                p["oa"] = p["oa"] or r.get("openalex_id")
                p["refs_doi"] |= {norm_doi(x) for x in (r["references"] if isinstance(r["references"], list) else [])} - {None}
                p["refs_oa"] |= set(r.get("references_openalex") or [])
                if isinstance(r["citations"], int):
                    p["citations"] = max(p["citations"] or 0, r["citations"])
                p["records"].append(r)
    return papers


def doi_url(d):
    return "https://doi.org/" + d if d else ""


ORCIDS = {}     # roster id -> that person's ORCID iDs


def main():
    for inst in NAMES:
        for q in load_roster(inst):
            ORCIDS.setdefault(q["rid"], set()).update(q["orcids"])
    papers = load_submission()
    by_doi = {p["doi"]: k for k, p in papers.items() if p["doi"]}
    by_oa = {p["oa"]: k for k, p in papers.items() if p["oa"]}
    inst_str = lambda p: ";".join(sorted(p["insts"]))
    own_ids = lambda p: {i for i, n in OWN_OA.items() if n in p["insts"]}
    stats = C.Counter()

    # ------------------------------------------------------------ citation network
    edges = {}
    for k, p in papers.items():
        for t in {by_doi[d] for d in p["refs_doi"] if d in by_doi} | {by_oa[w] for w in p["refs_oa"] if w in by_oa}:
            if t != k:
                q = papers[t]
                edges[(k, t)] = {"source_doi": doi_url(p["doi"]), "target_doi": doi_url(q["doi"]), "source_inst": inst_str(p),
                                 "target_inst": inst_str(q), "year": p["year"], "source_openalex": p["oa"] or "",
                                 "target_openalex": q["oa"] or "", "edge_type": "internal",
                                 "cross_inst": "TRUE" if p["insts"] != q["insts"] else "FALSE"}
    flow_in, flow_out = C.Counter(), C.Counter()      # (our inst, partner id) -> citation edges
    partner_name = {}

    def others(work, our):
        """Indian institutions of an external work other than our IIT(s): [(id, name)]"""
        return sorted({(i[0], i[1]) for i in work["institutions"] if i[2] == "IN" and i[0] not in our})

    for inst in NAMES:
        cited = {w["id"]: w for w in read_jsonl(os.path.join(CACHE, f"b_works_{inst}.jsonl"))}
        for k, p in papers.items():
            if NAMES[inst] not in p["insts"]:
                continue
            for x in p["refs_oa"]:
                w = cited.get(x)
                if not w or x in by_oa or (k, "oa:" + x) in edges:   # internal works are already edges; joint papers once
                    continue
                o = others(w, own_ids(p))
                if not o:
                    continue
                edges[(k, "oa:" + x)] = {"source_doi": doi_url(p["doi"]), "target_doi": doi_url(norm_doi(w.get("doi"))),
                                         "source_inst": inst_str(p), "target_inst": ";".join(n for _, n in o), "year": p["year"],
                                         "source_openalex": p["oa"] or "", "target_openalex": x, "edge_type": "out_to_indian",
                                         "cross_inst": "TRUE"}
                for i, n in o:
                    flow_out[(NAMES[inst], i)] += 1; partner_name[i] = n
        for y in read_jsonl(os.path.join(CACHE, f"c_works_{inst}.jsonl")):
            if y["id"] in by_oa:
                continue
            for w in y.get("referenced_works") or []:
                t = by_oa.get(w)
                if not t or NAMES[inst] not in papers[t]["insts"]:
                    continue
                q = papers[t]
                o = others(y, own_ids(q))
                if not o or ("oa:" + y["id"], t) in edges:
                    continue
                edges[("oa:" + y["id"], t)] = {"source_doi": doi_url(norm_doi(y.get("doi"))), "target_doi": doi_url(q["doi"]),
                                               "source_inst": ";".join(n for _, n in o), "target_inst": inst_str(q),
                                               "year": y.get("year") or "", "source_openalex": y["id"], "target_openalex": q["oa"] or "",
                                               "edge_type": "in_from_indian", "cross_inst": "TRUE"}
                for i, n in o:
                    for our in q["insts"]:
                        flow_in[(our, i)] += 1
                    partner_name[i] = n
    cols = ["source_doi", "target_doi", "source_inst", "target_inst", "year", "source_openalex", "target_openalex",
            "edge_type", "cross_inst"]
    with open(os.path.join(OUT, "citation_network.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(edges.values())
    stats.update("citation_" + e["edge_type"] for e in edges.values())

    # ------------------------------------------------------------ authorship network
    arows = []
    shared, shared_cites = C.defaultdict(set), C.Counter()
    for k, p in papers.items():
        r = p["records"][0]
        fac = {f["roster_id"]: f for rec in p["records"] for f in rec["faculty"]}
        oa_auth = r.get("authors_openalex") or []
        # co-author institutions (for indian_connections): each record lists the Indian co-author institutions other
        # than its own IIT, so a joint Kharagpur-Roorkee paper counts as shared for both directions
        for rec in p["records"]:
            our = NAMES[rec["record_id"].rsplit("-", 1)[0]]
            for i in rec.get("coauthor_institutions") or []:
                if i.get("country") == "IN" and k not in shared[(our, i["id"])]:
                    shared[(our, i["id"])].add(k)
                    shared_cites[(our, i["id"])] += p["citations"] or 0
                    partner_name[i["id"]] = i["name"]
        if not fac:
            continue
        if oa_auth:
            people = [{"name": a["name"], "id": a.get("openalex_author") or a["name"], "insts": set(a.get("institutions") or []),
                       "orcid": a.get("orcid")} for a in oa_auth]
        else:
            people = [{"name": a.get("name") or "", "id": a.get("name") or "", "insts": set(), "orcid": a.get("orcid")}
                      for a in (r["authors"] if isinstance(r["authors"], list) else [])]
        if len(people) > MAX_AUTHORS:
            stats["authorship_papers_skipped_over_%d_authors" % MAX_AUTHORS] += 1
            continue
        # mark which author entry is which of our faculty: by ORCID first, then by compatible name
        for f in fac.values():
            hit = next((a for a in people if "faculty" not in a and a["orcid"] and a["orcid"] in ORCIDS.get(f["roster_id"], ())), None)                 or next((a for a in people if "faculty" not in a and compatible(a["name"], f["name"])), None)
            if hit:
                hit["faculty"] = f
        for a in people:
            if "faculty" in a:
                f = a["faculty"]
                inst = NAMES[f["roster_id"].split(":")[0]]
                a.update(label=f["name"], node=f["roster_id"], inst=inst, is_fac="TRUE", inst_ids={i for i, n in OWN_OA.items() if n == inst} | a["insts"])
            else:
                names = [OWN_OA.get(i) or i for i in sorted(a["insts"])]
                a.update(label=a["name"], node=a["id"], inst=";".join(names), is_fac="FALSE", inst_ids=a["insts"])
        stats["authorship_faculty_not_located_in_author_list"] += len(fac) - sum(1 for a in people if "faculty" in a)
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                a, b = people[i], people[j]
                if a["is_fac"] == "FALSE" and b["is_fac"] == "FALSE":
                    continue
                if a["node"] == b["node"]:
                    continue
                arows.append({"author_a": a["label"], "author_b": b["label"], "paper_doi": doi_url(p["doi"]),
                              "inst_a": a["inst"], "inst_b": b["inst"], "year": p["year"], "author_a_id": a["node"],
                              "author_b_id": b["node"], "a_is_faculty": a["is_fac"], "b_is_faculty": b["is_fac"],
                              "cross_inst": "" if not (a["inst_ids"] and b["inst_ids"]) else
                              ("FALSE" if a["inst_ids"] & b["inst_ids"] else "TRUE"),
                              "n_authors": len(people)})
        stats["authorship_papers_used"] += 1
    # OpenAlex institution ids in inst_* columns -> names
    inst_names = {}
    for k, p in papers.items():
        for rec in p["records"]:
            for i in rec.get("coauthor_institutions") or []:
                inst_names[i["id"]] = i["name"]
    inst_names.update(OWN_OA)
    for row in arows:
        for c in ("inst_a", "inst_b"):
            row[c] = ";".join(inst_names.get(x, x) for x in row[c].split(";") if x)
    acols = ["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year", "author_a_id", "author_b_id",
             "a_is_faculty", "b_is_faculty", "cross_inst", "n_authors"]
    with open(os.path.join(OUT, "authorship_network.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=acols); w.writeheader(); w.writerows(arows)
    stats["authorship_edges"] = len(arows)
    stats["authorship_faculty_faculty_edges"] = sum(1 for r in arows if r["a_is_faculty"] == r["b_is_faculty"] == "TRUE")

    # ------------------------------------------------------------ indian connections
    keys = set(shared) | set(flow_in) | set(flow_out)
    crow = []
    for our, pid in sorted(keys, key=lambda x: (x[0], -len(shared.get(x, ())), -flow_in[x])):
        if OWN_OA.get(pid) == our:
            continue
        name = partner_name.get(pid) or inst_names.get(pid) or pid
        crow.append({"your_inst": our, "partner_inst": name, "shared_papers": len(shared.get((our, pid), ())),
                     "total_citations": shared_cites[(our, pid)], "citations_from_partner": flow_in[(our, pid)],
                     "citations_to_partner": flow_out[(our, pid)], "partner_kind": kind(name), "partner_openalex": pid})
    ccols = ["your_inst", "partner_inst", "shared_papers", "total_citations", "citations_from_partner",
             "citations_to_partner", "partner_kind", "partner_openalex"]
    with open(os.path.join(OUT, "indian_connections.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=ccols); w.writeheader(); w.writerows(crow)
    stats["indian_connection_rows"] = len(crow)
    for fn in ("citation_network.csv", "authorship_network.csv", "indian_connections.csv"):
        print(f"{fn}: {os.path.getsize(os.path.join(OUT, fn)) / 1e6:.1f} MB")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

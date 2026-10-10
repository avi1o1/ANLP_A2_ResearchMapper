# Enrichment — filling the TODOs, faculty links, and the submission files

Takes the scraped datasets for **IIT Kharagpur** and **IIT Roorkee** (`../WebScrape/iit_*.json`; IIT Ropar is not
assigned to Group 3 and is not used) and adds what the brief needs, from OpenAlex, Scimago, CORE and ORCID.
Nothing is guessed: a value that cannot be found stays `TODO` (original fields) or `null` (new fields), and every
filled value records its source in `record["filled"]`.

## Deliverables (in `out/`)
| File | What |
|---|---|
| `group3_data.csv` | submission CSV: the brief's 14 columns + extras, one row per (paper, faculty member); confirmed papers in field scope |
| `citation_network.csv` | directed citation edges (`source_doi, target_doi, source_inst, target_inst, year` + extras) |
| `authorship_network.csv` | co-authorship edges (`author_a, author_b, paper_doi, inst_a, inst_b, year` + extras) |
| `indian_connections.csv` | `your_inst, partner_inst, shared_papers, total_citations` + citation in/out-flow |
| `group3_data_all.csv` | every non-rejected paper with status/scope flags (for filtering differently) |
| `iit_kharagpur_enriched.json`, `iit_roorkee_enriched.json` | the enriched datasets (`{summary, records}`, one record per line) |

The two enriched JSONs and `citation_network.csv` are stored with **Git LFS** (over GitHub's 100 MB limit):
run `git lfs install` once, then clone/pull as usual.

## Field scope
`scripts/scope.py`: `SCOPE_MODE = "all"` (every research field; team decision) or `"sci_eng"` (TA clarification:
Physical + Life Sciences only). Change it and re-run `rebuild.sh` and `../Analysis/scripts/run_all.sh`.

## Pipeline
**Online steps** (only for new data; resumable, cached in `cache/`, which is git-ignored except the small files below):
1. `stage_a_fetch.py` — OpenAlex work for every DOI (100 per request, 1 credit each)
2. `stage_a2_title.py` — title search for DOI-less records (**10 credits per request**; stopped after 859 KGP records)
3. `stage_refdoi.py` — DOIs of cited works for records whose references were TODO
4. `stage_bc_indian.py b|c` — Indian works our papers cite (B) / that cite our papers (C)
5. `roster_supplement.py` — ORCID public records: extra ORCID iDs of roster faculty, faculty missing from the roster
6. `fetch_core.py` — CORE conference rankings (committed in `cache/core/`)
7. Scimago journal rankings: Cloudflare blocks scripts, so download by hand — https://www.scimagojr.com/journalrank.php,
   each year 2016–2025, *Download data*, save the CSVs in `cache/scimago/` (file names keep the year).

**OpenAlex API key:** set `OPENALEX_API_KEY`, or put the key in a file outside the repo and set `OPENALEX_KEY_FILE`
to its path. Never commit a key — `.gitignore` blocks `.openalex_key*` and `.env`.

**Offline rebuild + checks:** `sh scripts/rebuild.sh` (rule tests → `merge.py` → `faculty.py` → `verify.py` →
`eval_faculty.py` → `export_csv.py` → `build_networks.py` → `verify_networks.py`). Needs the OpenAlex caches
(`cache/a_*`, `b_*`, `c_*`, ~1 GB, not in git) — fetch them with the online steps first.
Live check of the citation flags (~40 credits per institute): `python scripts/spotcheck_flags.py <inst>`.

Committed small caches: `cache/core/` (CORE exports), `cache/roster_supplement_<inst>.json` (ORCID-verified faculty additions).

## What gets added to each record
* filled TODOs: affiliation (`verified` from affiliation text on the paper, or `rejected: …` when every author is
  elsewhere), type, venue, ISSN, authors, citations, references, DOI — listed in `record["filled"]`
* `research_area` (OpenAlex topic → subfield → field → domain), `sci_eng_scope` (field scope, see above)
* `quartile` (Scimago, ISSN + publication year), `core` (CORE rank, conference papers)
* `coauthor_institutions`, `cites_indian_inst` / `cited_by_indian_inst` (+ the institutions involved)
* `faculty`: roster people linked to the paper, with the rule used (`orcid`, `pipeline_tag`, `name`, `name+department`, `openalex_author`)
* OpenAlex ids (`openalex_id`, `references_openalex`, `authors_openalex`) for building the networks

Rules and thresholds are in the docstrings of `merge.py`, `oa_extract.py`, `scope.py`, `ranks.py`, `faculty.py`,
`export_csv.py`, `build_networks.py`.

## Known edge cases (documented, not errors)
* OpenAlex sometimes lists a paper among its own references; such self-references are ignored.
* ~200 papers are in both datasets (joint Kharagpur–Roorkee). In `group3_data.csv` each institute's flags count the other
  IIT as an Indian institution; in the network files the joint paper is one node owned by both IITs.

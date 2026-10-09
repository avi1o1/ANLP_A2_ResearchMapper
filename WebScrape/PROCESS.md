# Publication Scrape — Process & Decision Log

Project: DPCN Research Mapping 2026 (Group 3) — institutions: **IIT Ropar**, **IIT Kharagpur**, **IIT Roorkee** (added later, §13)
Window: publications dated **2016-01-01 … 2026-12-31**
Collection date: 2026-10-07 (citation counts are as of this date)
Operator: Aviral Gupta (with Claude Code as research assistant)

This file is written as a lab notebook: every step, decision and its rationale is recorded
in chronological order so the scrape can be reproduced and audited. Scripts live in
`scripts/`. Raw API dumps (`raw/`) and run logs (`logs/`) are written at run
time and are not kept in the repository. Final numbers are in [RESULTS.md](RESULTS.md).

---

## 0. Requirements (from `DPCN_Instruction_Note.pdf` + operator brief)

* Fetch *all* publications of the assigned institutions for 2016–2026.
* Per publication fields: `title, authors, year, type, journal/conference name, issn, doi,
  citations, references`.
* Anything uncertain or unretrievable is marked with the literal string `TODO` (optionally
  `TODO: <reason>`) so it can be followed up manually.
* Output: `iit_ropar.json`, `iit_kharagpur.json`.
* Goal is maximum recall ("no record missed") with documented precision controls.

## 1. Source reconnaissance (2026-10-07)

Probed every candidate source before designing the pipeline.

| Source | Status | Notes |
|---|---|---|
| OpenAlex API | **Blocked** — HTTP 429 | OpenAlex now requires an API key; the anonymous daily budget for our network IP was already exhausted (shared campus IP). Operator decided to **proceed without OpenAlex** and without other keyed APIs. We do *not* circumvent the limit. |
| Scopus / Elsevier API | Not available | No key. |
| Semantic Scholar (S2) API | Works intermittently (anonymous shared pool, 429s) | Used for enrichment (citations/references) with back-off. |
| Crossref REST API | **Works** | `query.affiliation=<rare token>` behaves like an exact filter for rare tokens (e.g. `Ropar`: 3,482 hits 2016–2026, 3,481 contain "Ropar" in an author affiliation). Limitation: only works whose publisher deposited affiliations (Elsevier largely does not). `filter=ror-id:` only 83 hits — useless. |
| Europe PMC REST | **Works** | `AFF:"…"` search. Ropar 1,232, Kharagpur 5,003 (2016–2026). Biomedical/life-science + chemistry heavy; includes Elsevier. |
| DOAJ API | **Works** | `bibjson.author.affiliation`. Ropar 447, Kharagpur 2,239 (all years). OA journals only. |
| ORCID public API | **Works** | `affiliation-org-name` search: Ropar 1,342 profiles, Kharagpur 9,141 profiles. Works lists give DOIs incl. Elsevier (Scopus sync). Person-level → needs date-window filtering. |
| DBLP | Website behind bot-wall; **SPARQL endpoint works** | CS coverage, person affiliations. |
| INSPIRE-HEP | Reachable, affiliation query returned 0 with our syntax | To revisit for HEP/physics. |
| IRINS (iitrpr/iitkgp.irins.org) | HTTP 403 to scripts | To try via browser/web fetch. |
| Institute websites | iitrpr.ac.in 200; iitkgp.ac.in timed out from our host | Rosters, golden set. |

ROR IDs: IIT Ropar `https://ror.org/02qkhhn56`, IIT Kharagpur `https://ror.org/03w5sq511`.

### 1.1 Affiliation search-string variants (Crossref hit counts, 2016–2026)

| Term | Hits | Comment |
|---|---|---|
| Ropar | 3,482 | primary |
| Rupnagar | 1,935 | official district name; overlaps Ropar; also matches other Rupnagar orgs → needs IIT check |
| Roopnagar | 42 | variant spelling |
| Rupar | 0 | |
| Kharagpur | 13,781 | primary |
| Khargpur | 11 | misspelling |
| Kgp | 43 | abbreviation (IIT KGP) |
| Kharagpure / Kharaghpur / Kharagpu | 0 / 0 / 1 | misspellings |

## 2. Strategy (multi-channel discovery → union → verification → enrichment)

Because no single open source covers everything, recall comes from the **union of
independent discovery channels**, and quality from a per-record **evidence trail**:

1. **Affiliation-string channels** (high precision): Crossref, Europe PMC, DOAJ, (INSPIRE).
2. **Person channels** (cover publishers without affiliation metadata, e.g. Elsevier):
   faculty rosters → ORCID works, DBLP, Semantic Scholar author pages, restricted to the
   person's tenure window.
3. **Golden set** built independently (web search, institute news, faculty homepages,
   annual reports) — used *only* to measure recall and diagnose misses; the search strings /
   channels are refined until the golden set is (near-)fully covered.
4. Enrichment of every DOI from Crossref (+ S2) for the required fields.
5. Every field that cannot be established is set to `TODO`.

(Sections below are appended as work proceeds.)

## 3. Affiliation-string search design & classification

### 3.1 How the search strings were chosen
* Crossref `query.affiliation` is a relevance (OR-of-tokens) search: multi-word queries such as
  `"IIT RPR"` or `"IIT KGP"` return ~21k mostly irrelevant hits (they match any "IIT" or "RPR").
  **Decision:** search only on *rare single tokens* (place names, PIN codes, institutional
  abbreviations) and do all precision filtering locally. Verified empirically: for `Ropar`,
  3,481/3,482 returned records contain "Ropar" in an author affiliation.
* Token list was grown iteratively by probing spelling variants and inspecting real strings
  (§1.1). Final tokens:
  * IIT Ropar: `Ropar, Rupnagar, Roopnagar, 140001` (+ broad sweep `Punjab`)
  * IIT Kharagpur: `Kharagpur, 721302, Khargpur, Kgp, Kharagapur, Kharagur, Kharapur, Khragpur,
    Karagpur, Kharagpu, IITKGP` (+ broad sweep `West Bengal`)
  * Tried, 0 hits: `Rupar, Ropad, Rupnager, IITRPR, iitrpr, Kharagpure, Kharaghpur, Kharakpur,
    Kharagpour, Kharaqpur, Kharghpur, Kharagpar, Kharagpuri, Kharagpr`.
  * `Roper` (170) rejected: only "Roper St Francis" (US hospital) etc.
* Broad sweeps (`Punjab` 65,860 and `West Bengal` 277,583 records, light fields only) catch
  strings that name the IIT without the city (e.g. "Indian Institute of Technology, Punjab").
* **Performance decision:** full-record affiliation queries ran at ~100 records / 40 s; switching to
  `select=DOI,author,title,type,issued` (light) gives 1,000 / 50 s. So discovery uses light sweeps
  and full metadata is fetched afterwards per DOI (`filter=doi:…` batches of 40, ~2 s each).

### 3.2 Classifier (`scripts/affil.py`)
Each author's affiliation strings are joined and classified as `iit | other | uncertain | None`:
1. `None` if no city/PIN/e-mail-domain token appears.
2. `iit` if a fuzzy "Indian Institute of Technology"/IIT pattern or an institute-specific unit name
   is present. Fuzzy because real strings contain typos: *Indian Institue / Institite / Insitute /
   Tnstitute / Tehcnology / Instituteof / "Indi | an Institute" / IIT1 / E&ECEIIT /
   "Indian Institute of Ropar" / "India Institute of Technology"*.
3. `other` if a known other organisation in the same city is named (Ropar: pharmacy colleges, IET
   Bhaddal, NIELIT, Shivalik, Lamrin, Rayat, InfraRed Vision Pvt Ltd, the Rupnagar locality of
   Guwahati, 140001 PIN collisions in Beijing/Hanoi, "AgroParisTech" substring; Kharagpur:
   Kharagpur/Hijli/Bhatter colleges, Govt. General Degree College Kharagpur-II, SE Railway, IIM,
   IIEST, ICT-IOC Bhubaneswar "Kharagpur extension", KGP Bremerhaven (German clinic), Kazakh "KGP"
   health centres, Tata Metaliks, Hijli Co-operative (residential) …).
4. `iit` if the string names a department/school/centre + the city and no other organisation
   (the IIT is the only multi-department research institution in Kharagpur 721302 / Rupnagar 140001).
5. otherwise `uncertain` (kept, flagged TODO).

Every distinct non-`iit` string containing the city token was printed and reviewed by hand
(Ropar: 42 → 4 uncertain; Kharagpur: 78 → 11 uncertain after rule refinement). Remaining
uncertain strings are bare locations ("Rupnagar/IN", "Kharagpur, West Bengal, India",
"Research Scholar, Ropar") — genuinely undecidable, therefore TODO.
Bug found & fixed during review: the pattern added for "Indi | an Institute" was initially too
loose and matched any "Indian Institute…" (e.g. "Indian Institute of Science, Kharagpur").

## 4. Discovery channels

| Id | Channel | Script | Evidence tag |
|---|---|---|---|
| A1 | Crossref affiliation-token sweeps | `crossref_aff.py` | `aff:crossref` |
| A2 | Europe PMC `AFF:` search (all tokens OR'ed, PUB_YEAR 2016–2026) | `europepmc_aff.py` | `aff:europepmc` |
| A3 | DOAJ `bibjson.author.affiliation` per token × year | `doaj_aff.py` | `aff:doaj` |
| B1 | ORCID profiles with an affiliation to the IIT (name token or ROR) → works within tenure | `orcid_people.py` | `orcid_tenure` / `orcid_untimed` |
| B2 | DBLP persons whose DBLP affiliation is the IIT → publications | `dblp_people.py` | `dblp_person` |
| B3–B5 | Faculty roster → Crossref author search with disambiguation; roster ORCID works; roster DBLP pid | `roster_channels.py` | `roster_crossref_author`, `roster_orcid`, `roster_dblp` |
| M2 | Missing DOIs resolved by exact-title Crossref bibliographic match (±1 yr) | `doi_resolve.py` | (metadata) |

ORCID tenure rule: a work counts if its year ∈ [start, end+1] of any matching affiliation
(employment, education, qualification, invited position; open end → 2026). The +1 year allows
for publication lag. Profiles whose matching affiliation has no start year → `orcid_untimed`.

DBLP: the website is bot-walled, so the public SPARQL endpoint (`sparql.dblp.org`) is used.
DBLP affiliations are undated, so these are weak evidence.

## 5. Merge, verification and field rules (`build_candidates.py`, `finalize.py`)

**Union key:** normalised DOI; else normalised title + year. DOI-less records are later merged
into DOI records with an identical normalised title (±1 year).

**Metadata sources:** Crossref full record (canonical) → DataCite for non-Crossref DOIs (arXiv
10.48550, Zenodo, LIPIcs…; `datacite_enrich.py`) → channel metadata (Europe PMC/DOAJ/ORCID/DBLP).

**Affiliation verification** (`affiliation_status`):
* `verified` — at least one affiliation-string evidence, or the Crossref record's deposited
  affiliations classify as the IIT.
* *rejected (contradicted)* — found only via a person channel, but Crossref has deposited
  affiliations and the channel person's affiliation on that paper is another organisation (or all
  authors have affiliations and none is the IIT). Logged at run time in `logs/rejected_<inst>.jsonl.gz`.
* `TODO: unverified-likely …` — person channel only, no affiliation metadata exists (typical for
  Elsevier), and the year lies within [min−1, max+1] of years in which the *same person* has an
  affiliation-verified paper (data-driven tenure, more reliable than self-reported ORCID dates).
* `TODO: unverified-possible …` — person channel only, outside that observed range.
* `TODO: ambiguous affiliation string only (…)`.

Audit of the first Ropar pass motivated the likely/possible split: unverified records were 32%
Elsevier, 13% Springer journals (publishers that do not deposit affiliations to Crossref), and a
random sample showed both genuine papers (e.g. PhD students' Elsevier papers) and pre-joining
papers of faculty.

**Excluded record types:** Crossref `peer-review, component, dataset, database, grant,
journal-issue, journal, proceedings, proceedings-series, book-series, report-component, standard`.
Preprints (`posted-content`, arXiv) that Crossref links to a published version in the set, or that
share an identical normalised title with a published record, are merged into the published record
(`preprint_versions`).

**Field rules**
| Field | Rule |
|---|---|
| title | Crossref/DataCite title, HTML stripped; else channel title; else `TODO` |
| authors | ordered list `{name, orcid, affiliations, institute_author}`; `institute_author` true/false/null (null = no affiliation deposited); else Europe PMC/DOAJ author names; else `TODO` |
| year | Crossref `issued` (earliest of print/online); must be 2016–2026 |
| type | `journal` (journal-article), `conference` (proceedings-article; or journal-article/book-chapter whose venue says Proceedings/Conference/Symposium/Workshop…, or has a Crossref `event`), `book-chapter`, `book`, `preprint`, `thesis`, `report`, `other`; raw type kept in `type_raw`; `TODO` if unknown |
| venue | container title (journal / proceedings / book series) → event name → channel venue; else `TODO` |
| issn | all ISSNs (print+electronic) from Crossref / Europe PMC / DOAJ; journals without ISSN → `TODO`; non-journal types without ISSN → `"N/A (not a journal)"` |
| doi | `https://doi.org/<doi>`; else `TODO` |
| citations | Crossref `is-referenced-by-count` at collection date (single consistent source); Europe PMC / OpenCitations counts kept in `citations_by_source`; `TODO` if no DOI and no other count |
| references | list of DOIs of referenced works from the Crossref deposited reference list; fallback OpenCitations Index v2; else `TODO` (`references_meta` records deposited count vs. DOI-resolved count) |

Extra audit fields per record: `affiliation_status, institute_affiliations_matched, evidence,
found_via_person, type_raw, publisher, isbn, citations_by_source, references_meta, pmid, arxiv,
todo_fields, record_id`.

## 6. Faculty rosters (`rosters/`)

Built by sub-agents from the institute websites (details, URLs and per-department counts in
the roster agents' notes; only the roster CSVs are kept):

* **IIT Ropar** — 273 people (202 current, 55 former, 15 adjunct, 1 visiting). Cross-checked
  against the institute's JSON endpoint `api/get-all-faculty` (205 entries, all covered). Former
  faculty from Wayback snapshots of department pages (2016–2025) and the joined/left tables of annual
  reports 2016-17…2023-24. Identifiers: ORCID 122, Scholar 128, DBLP 3, joining year 186.
* **IIT Kharagpur** — 1,144 people (834 current, 14 emeritus, 10 visiting, 286 former who left
  ≥2016). Lists from the site's POST endpoint `Departments/showPeopleFormerStaff` for all 65 unit
  codes; former lists carry the tenure range (used as an end bound, +1 year publication lag).
  458 archived profile pages checked: no additional former faculty found. ORCID 474 (360 by
  name-search, accepted only when the ORCID record shows IIT KGP employment), joining year 614.
* Not reachable: IRINS (Cloudflare challenge, 403/402), DBLP search (bot wall). Not circumvented.

## 7. Golden sets (`golden/`) — independent recall benchmark

Built by separate sub-agents **without** any bibliographic API for discovery (web search, institute
news, annual reports, faculty pages, arXiv PDFs with visible affiliation). Notes files list every
search string, result counts, results visited and yields.

* IIT Ropar: 339 papers (faculty pages 137, annual reports 112, arXiv 47, digest pages 39,
  web search 3, news 1). 47 % carry a DOI printed on the source.
* IIT Kharagpur: 637 papers (faculty pages 391, arXiv 102, dept pages 58, news 41, web search 24,
  annual reports 21). Generic web-search strings were unproductive (mostly aggregator pages); the
  institute news site and lab pages were productive.
* Caveat found during evaluation: faculty publication lists include papers written *before/after*
  the person's tenure. Golden entries whose publisher-deposited affiliation for that author is
  another institution (e.g. NREL, IIT Bombay, IIM Visakhapatnam) are reported as golden-set errors.

Recall evaluation (`eval_recall.py`): match by DOI, else normalised title, else token-Jaccard ≥ 0.8
(±1 year); each miss diagnosed (not discovered / dropped / rejected). Results in
summarised in [RESULTS.md](RESULTS.md) (the per-run recall reports are regenerated by `eval_recall.py`).

## 8. Iterative refinement log (recall against golden sets)

| Iter | Change | Ropar recall | KGP recall |
|---|---|---|---|
| 0 | Affiliation channels + ORCID + DBLP persons | 77.9 % | 63.9 % |
| 1 | + DataCite enrichment, preprint de-dup, INSPIRE-HEP, bare-"IIT" no longer counts as contradiction | 79.6 % | 64.2 % |
| 2 | + roster channels round 1 (Crossref author search w/ disambiguation, roster ORCID, roster DBLP) | 82.3 % | 70.2 % |
| 3 | + graded "full-name" rule + one snowball iteration + ORCID-mismatch / bare-IIT no longer hard rejects | 91.4 % (DOI 93.1 %) | 75.4 % (DOI 91.6 %) |
| 4 | precision audit → co-author keys use full first names; "full-name" rule removed; main/unconfirmed split | 85.5 % | — |
| 5 | + data-driven common-surname rule (no initial-only matches for 114/410 common surnames), name-ambiguity guard, Europe PMC DOI verification | 85.5 % | — |
| 6 | snowball removed from main-file profiles (drift); loose pass feeds the unconfirmed file only | 76.1 % | 62.6 % |
| 7 (final) | + arXiv pass, Springer-page + Europe PMC verification complete, OpenCitations fallback | **78.2 %** (DOI 83.8 %; 84.4 % incl. unconfirmed file) | **66.9 %** (DOI 80.8 %; 73.0 % incl. unconfirmed file) |

Recall in iterations ≥4 is measured on the **main file only**; the evaluator also reports recall
if the unconfirmed-candidates file were included and how many golden misses sit there.

Diagnostics that drove each change:
* Iter 0 misses were dominated by faculty without ORCID publishing in Elsevier/APS/Springer/LNCS
  venues (no deposited affiliations) → roster-driven author search.
* Broad sweeps (`Punjab`, `West Bengal`) initially "found" 650 extra KGP records: inspection showed
  these were false positives from *generic* unit names ("School of Energy Science and Engineering"
  matched Harbin/Tianjin…; "awadh" matched Awadh Dental College). Fix: generic unit names now count
  only with the city token; added the state rule (IIT + "West Bengal"/"Punjab", no other IIT city →
  this IIT). After the fix the broad sweeps add **0** (Ropar) and **3** (KGP) records beyond the
  targeted tokens → evidence that the targeted token list is complete for Crossref.
* arXiv API returned HTTP 429 when two processes queried concurrently; arXiv was split into a
  separate single-threaded pass at ≤1 request / 5 s.
* Malformed DOIs from ORCID ("1-25", "doi 10.…", "doi.org/10.…") broke Crossref batch filters →
  `norm_doi` now extracts the `10.xxxx/…` pattern and drops anything else.
* Known unrecoverable gaps: faculty with no verified seed papers and no joining year (e.g. one
  Ropar CSE faculty) cannot be safely disambiguated; papers with no DOI in Crossref/DataCite and no
  ORCID/DBLP listing (old conference papers, book chapters in small presses).

## 9. Precision audits and the resulting design (iterations 4–6)

Recall alone rewards over-inclusion, so a **precision audit** was run: a seeded stratified random
sample per institute (`precision_sample.py`, seed 20261007: 25 verified, 40 likely, 40 possible
records) was checked by a separate agent against the affiliation printed on the paper (Crossref,
Europe PMC, Springer citation meta tags, open-access PDFs, arXiv PDFs; no bot challenge bypassed).
Files: `golden/precision_audit_<inst>.csv`.

| Tier (iteration-3 data) | Ropar yes/no/unknown | precision | KGP yes/no/unknown | precision |
|---|---|---|---|---|
| verified | 25/0/0 | 1.00 | 24/1/0 | 0.96 |
| likely | 8/8/24 | 0.50 | 15/8/17 | 0.65 |
| possible | 5/18/17 | 0.22 | 3/23/14 | 0.12 |

Precision by evidence channel (both audits, unverified rows): `dblp_person` 0/6, `orcid_untimed`
3/12, `orcid_tenure` 20/7, `roster_orcid` 10/3, `roster_crossref_author` 21/32, round-2
"full-name" rule 0/3. Failure patterns: namesakes with common Indian names (Kumar, Sharma, Singh,
Das, Ghosh…), papers from before the person joined / after they left, ORCID/DBLP profiles of a
different person.

Decisions taken from the audit:
1. **Main file vs. unconfirmed file.** `<inst>.json` keeps verified records, records with
   an ambiguous affiliation string, and `unverified-likely` records that have dated/specific person
   evidence (`orcid_tenure, roster_orcid, roster_crossref_author, roster_arxiv, roster_dblp`).
   Everything else (tier *possible*; undated DBLP/ORCID-only; loose-pass-only) goes to
   `candidates_unconfirmed_<inst>.json` with an `unconfirmed_reason` — nothing is thrown
   away, but low-precision material does not pollute the dataset.
2. **Co-author identity keys** use surname + full first name (surname + initial collided massively).
3. **Common surnames** (data-driven: surname carried by ≥8 distinct first names in the institute's own
   verified papers — 114 at Ropar, 410 at KGP): initial-only author forms ("N. Kumar") are not
   matched to roster persons.
4. **Name-ambiguity guard:** `amb = Crossref works with this exact name / (verified seeds/0.35 + 5)`;
   if `amb > 2` only ORCID/affiliation evidence or (≥2 shared full-name co-authors AND shared venue)
   is accepted.
5. **Snowball removed** from main-file profiles: in iteration 5 one prolific-common-name profile grew
   from 325 to 424 seed papers by absorbing its own (partly wrong) acceptances. A separate *loose*
   pass that keeps the snowball writes only to the unconfirmed file (`roster_crossref_author_loose`).
6. **Verification channels** (confirm or refute unverified records with real affiliation text):
   * V2 Europe PMC by DOI (batched): 3,622 of 45,861 DOIs found with affiliations; e.g. 376 Ropar
     person-channel records refuted.
   * V1 Springer landing pages (`citation_author_institution` meta tags), honest User-Agent, paths
     allowed by robots.txt, 3 workers ≤1 req/s each. Browser-like User-Agents get a challenge page;
     an honestly declared bot gets the normal page — nothing is bypassed. Slow (~15 pages/min);
     re-run `finalize.py` when it completes (see §11).
   * Tested and abandoned: ScienceDirect (403), IEEE Xplore (202 challenge), Wiley/T&F/AIP/ACS (403).

Trade-off recorded honestly: removing the snowball lowered main-file recall on the Ropar golden set
from 85.5 % to 76.1 % (the difference sits largely in the unconfirmed file) in exchange for removing
a large volume of namesake errors.

## 10. Operational incidents (for reproducibility)
* Usage-limit interruption killed all sub-agents once; they were resumed from their scratch state.
* `pkill -f <pattern>` matched the invoking shell itself twice (pattern appeared in the command line);
  switched to anchored `pgrep -f "^python3 …"` + kill by PID.
* Two OpenCitations writers appended to one gzip file → corruption; caches that are appended to
  across runs (`opencitations/oc.jsonl`, `landing/springer.jsonl`) are now plain JSONL; readers
  tolerate a truncated tail; `scripts/check_shards.py` verifies gzip caches.
* A machine suspend left HTTP calls hung for ~3 h; jobs were restarted (all caches resume).
* arXiv API returned 429 under two concurrent processes → single-threaded pass at 1 req / 5 s.

## 11. Final results

See [RESULTS.md](RESULTS.md) (dataset size, per-year/type counts, TODO counts, recall, precision audits,
validation).

## 12. Confirmatory pass (2026-10-08/09): validation + TODO resolution

`scripts/validate.py` (report regenerated at run time; summary in [RESULTS.md](RESULTS.md)). Checks: schema/required fields, year range, DOI
format/lower-case/uniqueness, main∩unconfirmed overlap, ISSN format, citation values, references are
DOIs, no self-reference, type values, `todo_fields` consistency, re-classification of every verified
record's matched affiliation, near-duplicate titles, **live re-fetch of 200 random records per institute
from Crossref** (title/year/venue), cross-source citation agreement, joint papers between institutes.

Defects found by the check and fixed in the pipeline (not patched in the output):
1. ~300 records had lost their Crossref metadata (an early failed batch + DataCite "missing" rows
   blocking the Crossref retry) → retry logic fixed; also single-DOI retry for batch false negatives.
2. Duplicate registrations of the same work (ASME twin DOIs, Angewandte German-edition `ange.` DOIs,
   Inderscience twins, IOP `/meta` URL suffixes, multiple preprint versions) → merged, other DOIs kept
   in `duplicate_dois`; conference vs journal versions stay separate publications.
3. Self-references in publisher reference lists → removed.
4. INSPIRE hits without any author affiliation of the IIT (audit found one) → demoted to weak evidence
   (`inspire_unmatched`); INSPIRE matched strings now stored.
5. Year delivered as a string by CSL/DataCite → coerced.
6. ISSNs from the journal-title lookup unhyphenated / comma-joined → normalised to `XXXX-XXXX`.
7. Supplementary-material DOIs (`…-supplement`) → excluded.

TODO resolution (`scripts/resolve_todos.py`): R1 Crossref single-DOI retry; R2 doi.org content
negotiation (CSL-JSON, any registration agency); R3 DOI-less records → title search in Crossref,
DataCite and Semantic Scholar (accepted only if title-token Jaccard ≥ 0.9, |Δyear| ≤ 1 and a shared
author surname when authors are known; 23 / 314 / 175 DOIs found); R4 ISSN via Crossref journal-title
registry (exact title match); R5 Semantic Scholar reference lists / citation counts (fallback only).
Preprint venues are now filled from the preprint server (Crossref `institution` / `group-title`).
Example effect (Kharagpur): venue TODO 1,356 → 118, references 5,205 → 3,929, DOI 1,072 → 928.

Final validation: **0 violations on every check for all three institutes**; live re-check matched
title 99–100 %, year 99.5–100 %, venue 99.5–100 %; Crossref vs OpenCitations citations Spearman
ρ = 0.83 / 0.87 / 0.88 (median |diff| 0). Semantic Scholar counts agree less (ρ 0.32–0.67) and are used
only when Crossref has no count. Remaining near-duplicate titles (22 / 80 / 48 groups) are mostly a
conference paper and its later journal version.

## 13. IIT Roorkee (added 2026-10-08 on request)

Same pipeline and rules; institute-specific decisions:
* ROR `https://ror.org/00582g326`. Crossref tokens: `Roorkee` (11,833), `247667` (3,490), `Roorke` (12),
  `Rorkee` (9), `Saharanpur` (778) and `247001` (179) for the **Saharanpur campus** (Polymer & Process
  Engg, Paper Technology, Applied Science & Engg), broad sweep `Uttarakhand` (18,267). `IITR` alone was
  rejected as a token: it collides with CSIR-IITR (Indian Institute of Toxicology Research, Lucknow).
* Classifier additions after reviewing 293 distinct uncertain strings: other organisations in Roorkee /
  Saharanpur (National Institute of Hydrology, CSIR-CBRI, COER, Quantum, Motherhood, Haridwar University,
  Patanjali, CPPRI, Shobhit, medical colleges…); `IITR`+Roorkee and Saharanpur "Polymer & Process
  Engineering" count as IIT Roorkee; the department-only rule is **not** applied to Saharanpur strings
  (many unrelated institutions there). After review: 49 distinct uncertain strings (67 author slots).
* INSPIRE normalised name is `IIT, Roorkee` (357 records).
* Roster: 849 people (573 current, 227 former, 25 visiting, 18 adjunct, 6 emeritus); ORCID 371
  (322 by unique-name search accepted only with IIT Roorkee employment), joining year 482. Former-faculty
  end years are lower bounds (archive gaps) → end-of-tenure allowance +4 years for Roorkee (+1 elsewhere).
* Golden set: 562 papers (faculty pages 380, dept pages 111, arXiv 51, web search 8, news 6, annual
  reports 6); 82 % with DOI (354 looked up by exact title afterwards).

## 14. Files and how to reproduce

| Path | Content |
|---|---|
| `<inst>.json` | **Dataset** `{summary, records[]}`: pretty summary, one record per line (fields: [README](README.md)) |
| `rosters/<inst>_faculty.csv` | Faculty rosters (input to the person channels) |
| `golden/` | Golden sets (recall benchmark) and precision-audit sheets |
| `scripts/` | All scripts |

**Reproduce:** discovery harvests (`crossref_aff.py <token> --light` for every token in §3.1 / §13,
`europepmc_aff.py`, `doaj_aff.py`, `inspire_aff.py`, `orcid_people.py`, `dblp_people.py` per institute),
then `sh scripts/run_final.sh`; verification `verify_epmc.py`, `verify_springer.py`, `resolve_todos.py`;
finally `sh scripts/refresh_all.sh` (rebuild + recall + TODO sheets + validation). Crossref/ORCID/DataCite
content changes over time; citation counts are as of the collection date.

**Submission note (2026-10-09):** `candidates_unconfirmed_<inst>.json` (low-confidence person-channel
candidates, audit precision 12–22 %) is written by `finalize.py` for follow-up work but is git-ignored
and not part of the submission; likewise `todo_followup_<inst>.csv` (regenerate with
`scripts/export_todo.py`). Output JSON is written with a pretty-printed summary and one record per
line (valid JSON; fully pretty-printing would push the Kharagpur file past GitHub's 100 MB limit).

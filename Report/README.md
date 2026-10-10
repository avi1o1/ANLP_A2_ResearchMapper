# Report — what to write and where every number comes from

The brief (`DPCN_Instruction_Note.pdf`, section 8; checklist in section 11) asks for **a statistics report of at most
10 slides or 5 pages**, covering IIT Kharagpur and IIT Roorkee at **faculty, department and institution level**, due
**Week 3**. Everything is already computed. The report only needs choosing, framing and explaining.

* Tables: `Analysis/results/*.csv`. Ready-made charts: `Analysis/figures/*.png`, in the same colours as the
  dashboard (KGP blue, Roorkee orange).
* Definitions: `Analysis/README.md` and the docstrings in `Analysis/scripts/*.py`. Data collection and quality:
  `WebScrape/PROCESS.md`, `WebScrape/RESULTS.md`, `Enrichment/README.md`.
* Network concepts explained simply (PageRank, Louvain, Jaccard): `docs/network_concepts.html`.

## 1. Required content (brief §8) → source

| Must cover | Table | Figure |
|---|---|---|
| Publication trend 2016–2026 (total + per year) | `trend.csv` | `trend.png` |
| Q1 fraction per institution | `quartiles.csv` (`q1_fraction_of_ranked`, `ranked_share`) | `quartiles.png` |
| h-index distribution of faculty | `faculty.csv` (`h_index`) | `h_index_hist.png` |
| Top 5 journals per institution | `top_journals.csv` | (table) |
| Most-cited papers (top 10) | `most_cited.csv` | (table) |
| Research area breakdown | `research_areas.csv` | `research_areas.png` |
| **Citation network**: PageRank top 10, in-degree distribution, cross-institute flow | `pagerank_top10.csv`, `indegree_distribution.csv`, `citation_network_summary.csv`, `citation_flow_summary.csv`, `citation_flow_partners.csv`, `citation_flow_yearly.csv` | `indegree_ccdf.png`, `citation_flow_yearly.png`, `top_citing_institutes.png` |
| **Authorship network**: degree & betweenness centrality, community structure | `top_collaborators.csv`, `top_brokers.csv`, `faculty_centrality.csv`, `communities.csv`, `community_stability.csv`, `authorship_summary.csv` | `faculty_network.png`, `community_sizes.png` |
| Department level | `departments.csv` | (table) |
| Indian connections (§7, recommended) | `partners.csv`, `cluster_summary.csv`, `jaccard_topics.csv`, `null_model_comparison.csv` | `top_partners.png`, `jaccard_vs_shared.png`, `coauthor_degree_ccdf.png` |

## 2. Suggested 10-slide outline

1. **Title + data at a glance**: the two institutes, 2016–2026, number of papers and faculty, sources (Crossref,
   Europe PMC, DOAJ, ORCID, DBLP scrape + OpenAlex, Scimago, CORE enrichment).
2. **Data & method** (one slide, honest): multi-source scrape → affiliation confirmed on the paper (OpenAlex
   affiliation text, checked against hand-labelled samples) → faculty matching (ORCID / name / department, no
   guessing). Coverage: ~85 % of papers linked to a faculty member. Scope: all fields (see section 4).
3. **Output over time**: `trend.png`. Both grow roughly 2× from 2016 to 2025. Note that 2026 is partial.
4. **Journal quality**: `quartiles.png` + top-5 journals table + one line on CORE ranks.
5. **Faculty**: `h_index_hist.png` + top 5 faculty by h-index (`faculty.csv`) + a department table (`departments.csv`).
6. **Research areas & most-cited papers**: `research_areas.png` + top 3–5 papers (`most_cited.csv`). Note that some
   top papers are large consortium papers.
7. **Citation network**: `indegree_ccdf.png` (heavy tail) + PageRank top 5 vs in-degree rank (`pagerank_top10.csv`).
   Point out papers with modest in-degree but high PageRank, and the age bias (ρ ≈ −0.39 with year).
8. **Indian citation flow**: in-flow vs out-flow and the impact ratio (`citation_flow_summary.csv`),
   `citation_flow_yearly.png`, `top_citing_institutes.png`.
9. **Collaboration network**: `faculty_network.png` + communities + null-model table (`null_model_comparison.csv`).
   The network is far more clustered and modular than random graphs with the same size or degrees.
10. **Partners & conclusions**: `top_partners.png`, cross-cluster summary, `jaccard_vs_shared.png` (do we
    collaborate with similar or complementary institutes?), 3–4 takeaways.

For a 5-page document instead: one page each for (1–2) data & method, (3–6) institution/faculty/department
stats, (7–8) citation network & flow, (9) collaboration network, (10) connectivity & conclusions.

## 3. Headline numbers (current data: commit `f781f90`, scope = all fields)

Re-check these against the CSVs if the pipeline is re-run.

| | IIT Kharagpur | IIT Roorkee | Source |
|---|---|---|---|
| Papers 2016–2026 (confirmed) | 30,019 | 22,844 | `trend.csv` |
| Papers 2016 → 2025 | 1,782 → 3,429 | 1,335 → 2,932 | `trend.csv` |
| Journal papers / Q1 share of ranked | 21,988 / 64.4 % | 16,970 / 59.5 % | `quartiles.csv` |
| CORE-ranked conference papers (A* / A / B / C) | 118 / 97 / 246 / 142 | 11 / 37 / 156 / 103 | `core_ranks.csv` |
| Faculty with papers / median h-index / max | 934 / 7 / 63 | 704 / 7 / 42 | `faculty.csv` |
| Top field | Engineering 31.6 % | Engineering 38.6 % | `research_areas.csv` |
| Top journal | Physics of Fluids (330) | Scientific Reports (133) | `top_journals.csv` |
| Internal citation edges (own corpus) | 53,798 | 38,648 | `citation_network_summary.csv` |
| Indian in-flow / out-flow / impact ratio | 114,443 / 129,758 / 0.88 | 96,963 / 117,255 / 0.83 | `citation_flow_summary.csv` |
| Top Indian citer | IIT Roorkee (3,105) | VIT University (2,565) | `citation_flow_partners.csv` |
| Top co-authoring partner | Jadavpur University (361) | IIT Delhi (333) | `partners.csv` |

Collaboration network of both IITs' faculty (`authorship_summary.csv`, `null_model_comparison.csv`):
* 1,638 faculty, 3,329 collaborating pairs, of which 90 are Kharagpur–Roorkee pairs; 324 faculty have no faculty co-author.
* Louvain: 27 communities with ≥ 5 members, modularity Q = 0.76, stable across 10 seeds (mean ARI 0.83).
  23 of the 27 are ≥ 90 % one IIT. They are interdisciplinary groups around a core department: the largest
  department is typically ~44 % of a community (`communities.csv`, `top_department_share`).
* Clustering 0.17 vs 0.002 for an ER graph and 0.010 for a degree-preserving rewiring. Mean path 5.3 vs 5.4 (ER),
  which is "small world". Assortativity +0.19 vs ≈ 0 for both null models.

Citation network (`pagerank_top10.csv`): Kharagpur's PageRank #1 has only 20 internal citations (in-degree rank
109). It ranks high because influential papers cite it, which is the point of PageRank. PageRank correlates with
publication year at ρ ≈ −0.39, because older papers accumulate citations.

## 4. Caveats and decisions to state (method slide or footnotes)

* **Scope.** The TAs clarified "science and engineering papers only". The team chose to include **all fields**
  (Health and Social Sciences too). This is a one-line switch (`SCOPE_MODE` in `Enrichment/scripts/scope.py`).
  If the TAs insist, switch it, re-run `sh Enrichment/scripts/rebuild.sh` and `sh Analysis/scripts/run_all.sh`,
  and refresh the numbers above. Under science & engineering only, the results are very similar.
* **Affiliation.** Only papers whose IIT affiliation is confirmed on the paper are counted. ~1,000 papers per IIT
  were rejected because every author was elsewhere (namesakes, or papers from before joining).
* **h-index** is computed over 2016–2026 papers in this dataset only, with citations as of October 2026, so it is
  lower than a Google Scholar h-index.
* **No imputation.** Unknown values (e.g. a missing citation count) are left out, never set to 0.
* **2026** is a partial year.
* Brief says "analyse networks within your assigned institutions". The citation and faculty networks are restricted
  to our two IITs; links to other institutes appear only in the flow / partner statistics.

## 5. Checklist (brief §11)
- [ ] ≤ 10 slides or ≤ 5 pages
- [ ] Covers every row of section 1, including both network summaries
- [ ] Faculty, department and institution levels all present
- [ ] Caveats / scope decision stated
- [ ] Numbers match the CSVs in `Analysis/results/` (re-check after any re-run)

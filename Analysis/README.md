# analysis — statistics for the Group 3 report and dashboard

Reads the enriched data and network files in `../Enrichment/out/` (never modifies them) and writes tables to
`results/` and charts to `figures/`. Re-run everything with `sh scripts/run_all.sh`.

**Analysis set:** papers whose IIT affiliation is confirmed on the paper, in every research field (team decision
2026-10-10; the TA rule "science & engineering only" can be restored with `SCOPE_MODE = "sci_eng"` in
`../Enrichment/scripts/scope.py`) — the same papers as `group3_data.csv`. A joint Kharagpur–Roorkee paper counts for both institutes.

| Script | Brief section | Tables (`results/`) | Charts (`figures/`) |
|---|---|---|---|
| `stats_bibliometric.py` | 8: trend, Q1, h-index, top journals, most cited, research areas; dashboard faculty / department tables | `trend`, `quartiles`, `core_ranks`, `top_journals`, `most_cited`, `research_areas`, `faculty`, `departments` | `trend`, `quartiles`, `research_areas`, `h_index_hist` |
| `stats_citation.py` | 6a, 7a: in-degree, PageRank, citation flow, top citing institutes, impact ratio, year-wise flow | `citation_network_summary`, `pagerank_top10`, `paper_citation_metrics`, `indegree_distribution`, `citation_flow_summary`, `citation_flow_partners`, `citation_flow_yearly` | `indegree_ccdf`, `citation_flow_yearly`, `top_citing_institutes` |
| `stats_authorship.py` | 6b: degree & betweenness centrality, Louvain communities; null models (ER, degree-preserving) | `authorship_summary`, `faculty_centrality`, `top_collaborators`, `top_brokers`, `communities`, `community_stability`, `null_model_comparison`, `bridging_faculty` | `coauthor_degree_ccdf`, `community_sizes`, `faculty_network` |
| `stats_connectivity.py` | 7b: partner ranking, co-authorship strength, cross-cluster links, Jaccard topic similarity | `partners`, `cluster_summary`, `jaccard_topics` | `top_partners`, `jaccard_vs_shared` |

Definitions and caveats are in each script's docstring. The main ones:
* **h-index** is computed over the faculty member's papers in this dataset (2016–2026, citations at collection
  date), so it is lower than a career h-index. Papers with an unknown citation count are skipped, never counted as 0.
* **PageRank** favours older papers in a citation network (Spearman ρ ≈ −0.39 with publication year here).
* **Authorship network** = faculty of both IITs; edge weight = joint papers. Louvain is randomised: 10 seeds,
  seed 42 reported, stability measured by adjusted Rand index.
* **Jaccard** compares top-20 OpenAlex subfields (2016–2026 works in the same field scope), computed the same way
  for every institution (one OpenAlex request each, cached in `cache/topic_profiles_<scope>.json`).
* 2026 is a partial year (data collected October 2026).

Charts use a colour-blind-checked palette: IIT Kharagpur blue, IIT Roorkee orange in every chart.

# Notebook — code with outputs for the submission

The course portal asks for the analysis as a **Jupyter notebook with outputs**:

> In the event that the submission limit is above 20MB, please upload the code (no cell outputs) on the portal along
> with a link to the notebook with cell outputs accessible. Please ensure your notebook contains your name and roll
> number to help us identify your work.

So the notebook is the readable, runnable record of *how* the statistics were computed. The data collection and
enrichment are long, online, multi-day jobs. The notebook should **not** re-run them. It starts from the finished
data in `Enrichment/out/` and does the analysis.

## 1. Setup

```
git lfs install && git pull        # citation_network.csv and the enriched JSONs are in Git LFS
pip install pandas numpy networkx scipy scikit-learn matplotlib jupyter
jupyter notebook Notebook/analysis.ipynb
```
No API key is needed. The notebook must not call OpenAlex or ORCID.

## 2. Inputs

| File | Size | Used for |
|---|---|---|
| `Enrichment/out/group3_data.csv` | 32 MB | the submission dataset (one row per paper × faculty member): trends, quartiles, journals, fields |
| `Enrichment/out/citation_network.csv` | 108 MB (LFS) | citation graph (`edge_type == "internal"`), citation flow (`in_from_indian`, `out_to_indian`) |
| `Enrichment/out/authorship_network.csv` | 27 MB | faculty co-authorship graph (rows with `a_is_faculty == b_is_faculty == "TRUE"`) |
| `Enrichment/out/indian_connections.csv` | 0.5 MB | partner institutions |
| `Analysis/results/*.csv` | small | the reference numbers: the notebook's results should match these |
| `Analysis/figures/*.png` | small | report-quality charts (can be shown with `IPython.display.Image`) |

`group3_data.csv` has one row per (paper, faculty member), so **de-duplicate papers before counting them**:
`df.drop_duplicates(["institution", "record_id"])`. Papers with no identified faculty have `author` = the institute
name and `faculty_match` = `none (institute)`.

## 3. Recommended structure

Keep the long bibliometric bookkeeping in the existing scripts, and **show the network analysis step by step in the
notebook**. That's what the course is about, and what graders will read.

1. **Title cell (markdown)**: course, Group 3, members' **names and roll numbers**, institutes, data date (Oct 2026).
2. **Data & method (markdown)**: 6–8 lines, copied from `Report/README.md` section 4: sources, affiliation
   confirmation, faculty matching, field scope (all fields; TA rule switchable), no imputation.
3. **Load data**: read the four CSVs with pandas; show `df.shape` and `df.head()` (keep the outputs small).
4. **Institution-level stats**, recomputed from `group3_data.csv`: papers per year (de-duplicated), Q1 fraction of
   ranked journal papers (`quartile` in Q1–Q4), top 5 `journal_name`, top 10 by `citations`, `research_field`
   shares. Plot with matplotlib, in KGP blue `#2a78d6` and Roorkee orange `#eb6834`.
5. **Faculty & department level**: h-index per faculty member. Group by (`institution`, `author`, `department`),
   not by name alone, because different people can share a name (e.g. two Santanu Chattopadhyays at Kharagpur in
   different departments). Use rows where `faculty_match` is not `none (institute)`; h = the largest h with h papers
   of ≥ h citations; skip blank citations. Show a histogram and the top 10, and compare with
   `Analysis/results/faculty.csv` (computed per `roster_id`).
6. **Citation network** with networkx:
   ```python
   cit = pd.read_csv("../Enrichment/out/citation_network.csv", low_memory=False)
   internal = cit[cit.edge_type == "internal"]
   src = internal.source_openalex.fillna(internal.source_doi)
   dst = internal.target_openalex.fillna(internal.target_doi)
   G = nx.DiGraph(); G.add_edges_from(zip(src, dst))
   papers = pd.read_csv("../Analysis/results/paper_citation_metrics.csv")   # every analysed paper (node ids)
   G.add_nodes_from(papers.node)        # include papers with no internal citations - needed to match exactly
   pr = nx.pagerank(G, alpha=0.85)
   ```
   This reproduces `pagerank_top10.csv` exactly (52,584 nodes). Leaving out the isolated papers (38,512 nodes)
   changes the normalisation and the top 10 order: only 9/10 overlap. That's worth a sentence in the notebook.
   Show the in-degree distribution (log-log CCDF), PageRank top 10 next to in-degree rank, and the Spearman
   correlation of PageRank with year.
7. **Citation flow**: count `in_from_indian` / `out_to_indian` edges per institute (`target_inst` / `source_inst`),
   the impact ratio in/out, the top 10 citing institutes (split `source_inst` on `;`), and a yearly line chart.
   Also count the internal edges between the two IITs (`cross_inst == "TRUE"`), as `stats_citation.py` does.
8. **Authorship network**: faculty-only graph with weight = number of distinct papers; `nx.degree_centrality`,
   `nx.betweenness_centrality`, `nx.community.louvain_communities(G, weight="weight", seed=42)`, modularity, and
   community sizes by institute.
9. **Null models** (course topic): compare clustering, path length, assortativity and Louvain Q with
   `nx.gnm_random_graph(n, m)` and a degree-preserving rewiring (`nx.double_edge_swap`). Code to copy:
   `Analysis/scripts/stats_authorship.py` (`graph_stats`, the loop over 10 samples).
10. **Connectivity**: partners from `indian_connections.csv` (top 10 by `shared_papers`, `partner_kind`), and Jaccard
   from `Analysis/results/jaccard_topics.csv` (the topic profiles came from OpenAlex, so just load the result and
   explain the formula).
11. **Cross-check cell**: assert that the notebook's key numbers equal the CSVs in `Analysis/results/` (papers per
    year, Q1 share, PageRank top 10, modularity within ±0.01, since Louvain is randomised).
12. **Conclusions (markdown)**: the same 3–4 takeaways as the report.

Reusing code is fine: `Analysis/scripts/stats_*.py` already implement every step with comments. You can copy
their functions into cells, or `import` them after `sys.path.insert(0, "../Analysis/scripts")`.

## 4. Keeping it under 20 MB, and how to hand it in

* Don't print whole DataFrames; use `.head()` or small summaries.
* Use matplotlib (static PNG) inside the notebook, not interactive Plotly, which can add several MB per chart.
  The interactive version is the dashboard.
* Draw the full citation network only as statistics. To draw something, use the faculty network or a small subgraph.
* Check the size after running: `ls -lh Notebook/analysis.ipynb`.
* If it's over 20 MB: upload a copy with outputs cleared
  (`jupyter nbconvert --clear-output --to notebook --output analysis_no_outputs.ipynb Notebook/analysis.ipynb`)
  and give a link to the version with outputs (the GitHub repo page renders notebooks).

## 5. Checklist
- [ ] Names and roll numbers in the first cell
- [ ] Runs top-to-bottom on a fresh clone (after `git lfs install && git pull`), with no API keys
- [ ] Covers institution, faculty and department stats, the citation network + flow, and the authorship network + communities
- [ ] Cross-check cell passes against `Analysis/results/`
- [ ] Size checked; no-output copy + link if over 20 MB

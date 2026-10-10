# Dashboard — what to build and where the data is

The brief (`DPCN_Instruction_Note.pdf`, section 4) asks for **an interactive dashboard for IIT Kharagpur and IIT
Roorkee**, shown to the class, due **Week 3**. All the numbers it needs are already computed. Building the dashboard
is a presentation job: read the CSVs below, draw them, and make them filterable. You don't need to touch the
scraping or enrichment code.

## 1. Before you start

```
git lfs install          # once per machine, needed for the 3 big files (see below)
git pull
pip install pandas plotly streamlit networkx pyvis      # for the recommended stack (section 3)
```

* **Use only `Analysis/results/` plus one small prepared network file (section 5).** These are all small files
  (the largest is 5 MB), so the dashboard loads fast and needs no Git LFS when deployed.
* **Don't load** `Enrichment/out/citation_network.csv` (108 MB) or the two `*_enriched.json` files (155–200 MB) in
  the dashboard itself. Use them only in the offline preparation step (section 5).
* If the statistics ever change, regenerate them with `sh Analysis/scripts/run_all.sh` (no API key needed).
  The dashboard then picks them up automatically.

## 2. Required panels → file → columns

All files are in `Analysis/results/` unless marked otherwise. Every table has an `institution` column
(`IIT Kharagpur` / `IIT Roorkee`) to filter on.

| # | Panel (brief §4) | File | Columns to use | Chart |
|---|---|---|---|---|
| 1 | **Publication trend** 2016–2026 | `trend.csv` | `year`, `total` (also `journal`, `conference`, `book-chapter`, `preprint`, `other`), `partial_year` | line chart, one line per institute; dash the 2026 segment (partial year) |
| 2 | **Faculty list**: name, department, h-index, total papers | `faculty.csv` | `faculty`, `department`, `h_index`, `papers` | searchable table |
| 3 | **Journal quartile distribution** | `quartiles.csv` | `Q1`–`Q4`, `not_in_scimago`, `q1_fraction_of_ranked` | 100 % stacked bar per institute (or two donuts) |
| 4 | **Faculty performance table** (sortable): papers, citations, top journal, h-index | `faculty.csv` (+ `faculty_centrality.csv`, join on `roster_id`) | `papers`, `citations`, `top_journal`, `h_index`, `q1_papers`; optional `faculty_coauthors`, `betweenness` | sortable, filterable table |
| 5 | **Top journals** (top 5 per institute) | `top_journals.csv` | `rank`, `journal`, `papers`, `most_common_quartile` | horizontal bars |
| 6 | **h-index distribution** | `faculty.csv` | `h_index` | histogram, one per institute (or overlaid) |
| 7 | **Research area breakdown** | `research_areas.csv` | `field`, `share`, `papers` | horizontal bars (top 12 fields) or treemap |
| 8 | **Most-cited papers** (top 10) | `most_cited.csv` | filter `scope` = institute (or `Both`); `title`, `journal`, `year`, `citations`, `doi` | table; make the DOI a link |
| 9 | **Conference rank** (CORE A*/A/B/C) | `core_ranks.csv` | `A*`, `A`, `B`, `C`, `not_core_ranked` | bars. Most conferences are not CORE-ranked (CORE only ranks computing venues), so say so |
| 10 | **Citation network** (interactive, directed; nodes = papers) | prepared file, section 5 | — | interactive graph |
| 11 | **Authorship network** (interactive, undirected; nodes = faculty) | prepared file, section 5 | — | interactive graph |

### Recommended extra panels (brief §7, Indian connectivity)

| Panel | File | Columns |
|---|---|---|
| Citation flow per year (in / out, 2016–2026) | `citation_flow_yearly.csv` | `year`, `in_flow`, `out_flow` |
| In-flow, out-flow, impact ratio (headline tiles) | `citation_flow_summary.csv` | `in_flow`, `out_flow`, `impact_ratio_in_over_out` |
| Top 10 Indian institutes citing us | `citation_flow_partners.csv` | `rank_by_in_flow` ≤ 10, `partner`, `citations_from_partner` |
| Partner institutes (co-authorship strength) | `partners.csv` | `partner`, `shared_papers`, `citations_from_partner`, `citations_to_partner`, `cluster`, `cross_cluster`, `jaccard_top20` |
| Cross-cluster links (IIT ↔ CSIR, IIT ↔ IISER, …) | `cluster_summary.csv` | `cluster`, `cross_cluster`, `partners`, `shared_papers` |
| Topic similarity vs collaboration | `jaccard_topics.csv` | `partner`, `shared_papers`, `jaccard_top20` (scatter) |
| PageRank top 10 vs in-degree | `pagerank_top10.csv` | `scope`, `rank`, `title`, `pagerank`, `in_degree`, `in_degree_rank`, `year` |
| Departments | `departments.csv` | `department`, `faculty_with_papers`, `papers`, `citations`, `q1_fraction_of_ranked`, `median_h_index` |
| Most collaborative / bridging faculty | `top_collaborators.csv`, `top_brokers.csv`, `bridging_faculty.csv` | names, `degree_centrality`, `betweenness`, `indian_partner_institutions` |
| Communities | `communities.csv` | `community`, `faculty`, `top_department`, `IIT Kharagpur`, `IIT Roorkee` |
| Network vs random graphs | `null_model_comparison.csv` | one small table |

The static PNG versions of most of these are in `Analysis/figures/` if you need a quick reference for what each
chart should look like.

## 3. How to make it interactive — recommended stack

**Streamlit + Plotly + pyvis.** It's all Python, it reads the CSVs directly, and it deploys free.

* Layout: one sidebar with the **filters** (institute: Kharagpur / Roorkee / both; year range; department), and
  tabs for **Overview** (panels 1, 3, 5, 7, 9), **Faculty** (2, 4, 6 + departments), **Papers** (8, PageRank),
  **Citation network** (10 + citation flow), **Collaboration** (11 + partners, communities).
* Charts: `plotly.express` (`px.line`, `px.bar`, `px.histogram`, `px.scatter`) gives hover tooltips and zoom
  for free. Tables: `st.dataframe(df)` is already sortable and searchable.
* Networks: build a `pyvis.network.Network`, add the nodes and edges from the prepared JSON, save it to HTML,
  and embed it with `streamlit.components.v1.html(html, height=700)`. pyvis gives drag, zoom, hover and click to
  highlight neighbours. Turn physics **off** and use the precomputed `x`, `y` positions, so the layout is stable and fast.
* Run locally: `streamlit run Dashboard/app.py`. Deploy: Streamlit Community Cloud (free), pointing at the repo.
  This works without LFS because the app only reads small files.

**Alternative (no server):** a single static HTML page with Plotly.js for the charts and Cytoscape.js or vis-network
for the graphs, loading CSV/JSON exported next to it. It can be hosted on GitHub Pages. This is more JavaScript work,
but it can be opened anywhere.

**Conventions to keep everything consistent with the report figures:**
* Colours: **IIT Kharagpur `#2a78d6` (blue), IIT Roorkee `#eb6834` (orange)** in every chart. Ordered categories
  such as Q1→Q4 use one blue from dark to light: `#0d366b`, `#1c5cab`, `#3987e5`, `#86b6ef`.
* Never put two different units on one chart (no dual y-axes). Label the 2026 points as partial.
* Show the caveats in section 6 as small notes under the relevant panels.

## 3b. Design: simple, clean, readable (Apple-website feel)

The dashboard must look **calm and easy to read**, not like a dense analytics console. The target is the feel of
Apple's product pages: lots of white space, one idea per section, big clear numbers, short plain sentences, and very
few colours. Take the *style*, not the brand: no Apple logo, product names or imagery.

> **Note for an AI coding assistant (e.g. Claude Code) building this:** treat the rules below as requirements. Prefer
> removing an element to adding one. After building, open the app, take a screenshot of every tab at desktop and phone
> width, and fix anything that looks crowded, misaligned or hard to read before calling it done.

**Layout**
* One centred column, **max width ~1100 px**, generous padding (≥ 48 px between sections, ≥ 24 px inside them).
* Each tab opens with a **hero row**: a short headline sentence that states the takeaway (e.g. "Kharagpur publishes
  more; both doubled since 2016"), and 2–4 big numbers below it (e.g. papers, Q1 share, median h-index), with a
  small grey label under each number.
* Then **at most 2–3 charts per screen**, stacked vertically or two side by side. No grids of 6+ small charts.
* Long tables: show the **top 10** by default, with an expander or "Show all" for the rest. Wrap long titles.
* Filters live in one place (the sidebar, or one row at the top) and nowhere else.
* Must work at phone width: columns stack, nothing scrolls sideways.

**Typography**
* System font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif`.
* Clear scale: page title ~40 px bold; section headline ~28 px semibold; big numbers ~44 px semibold; body 16–17 px;
  captions 13 px grey.
* Text colour near-black `#1d1d1f`; secondary text grey `#6e6e73`. Line length under ~75 characters for paragraphs.
* Sentence-case titles that say what the chart shows ("Papers per year", not "PUBLICATION_TREND_CHART").

**Colour**
* Background white `#ffffff`; subtle section background `#f5f5f7`; hairlines `#e8e8ed`.
* Data colours are only the two institutes: **Kharagpur `#2a78d6`, Roorkee `#eb6834`**, plus the one-blue ramp for
  ordered categories (section 3). Everything else is grey. No gradients, no shadows heavier than a soft 1–2 px blur,
  and no emoji icons.

**Charts (Plotly)**
* White background, no chart border, light horizontal gridlines only, thin lines (2 px), small markers.
* Label lines directly at their end instead of a legend box where possible. Round numbers (`12.4k`, `64 %`).
* Hover tooltips on; the Plotly toolbar (modebar) off.
* No 3-D, no pie charts with more than 4 slices, no dual y-axes.

**Copy**
* Every chart gets a one-line caption in plain English saying what to notice, plus any caveat in small grey text
  (section 6). Write for a classmate, not a statistician. Explain "PageRank" or "modularity" in one short phrase
  the first time they appear (`docs/network_concepts.html` has simple wording).

**Starter config (copy these)**

`Dashboard/.streamlit/config.toml`:
```toml
[theme]
base = "light"
primaryColor = "#1d1d1f"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f5f5f7"
textColor = "#1d1d1f"
font = "sans serif"

[client]
toolbarMode = "minimal"
```

Plotly defaults (put in `app.py` once):
```python
import plotly.io as pio, plotly.graph_objects as go
pio.templates["clean"] = go.layout.Template(layout=dict(
    font=dict(family='-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif', size=14, color="#1d1d1f"),
    paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", margin=dict(l=40, r=24, t=48, b=40),
    xaxis=dict(showgrid=False, linecolor="#e8e8ed", ticks=""),
    yaxis=dict(gridcolor="#e8e8ed", zeroline=False, ticks=""),
    colorway=["#2a78d6", "#eb6834"], hoverlabel=dict(bgcolor="#ffffff", font_size=13),
    legend=dict(orientation="h", y=1.08, x=0),
))
pio.templates.default = "clean"
CHART_CONFIG = {"displayModeBar": False}      # st.plotly_chart(fig, config=CHART_CONFIG, use_container_width=True)
```

A little CSS for spacing and the big numbers (inject once with `st.markdown(..., unsafe_allow_html=True)`):
```css
.block-container { max-width: 1100px; padding-top: 3rem; padding-bottom: 4rem; }
h1 { font-size: 2.5rem; font-weight: 700; letter-spacing: -0.02em; }
h2 { font-size: 1.75rem; font-weight: 600; letter-spacing: -0.01em; margin-top: 3rem; }
[data-testid="stMetricValue"] { font-size: 2.75rem; font-weight: 600; }
[data-testid="stMetricLabel"] { color: #6e6e73; }
#MainMenu, footer { visibility: hidden; }
```

The network panels follow the same rules: white background, thin grey edges, nodes in the two institute colours,
labels only on hover or for the top ~10 nodes, and a one-line caption explaining what to look at.

## 4. Suggested file layout (create these)

```
Dashboard/
  README.md            (this file)
  prepare_data.py      offline step: builds data/*.json from Analysis/results + Enrichment/out (section 5)
  data/                small prepared files the app reads (commit these)
  .streamlit/config.toml   theme (section 3b)
  app.py               the Streamlit app
  requirements.txt     pandas, plotly, streamlit, pyvis, networkx
```

## 5. Network panels — prepare the data first (`prepare_data.py`)

The full citation network has **52,584 papers and 96,030 internal citation edges**. That is far too many to draw
in a browser, so draw a meaningful subset and precompute the positions offline with networkx.

### 5a. Citation network → `Dashboard/data/citation_graph.json`
1. Nodes: the **top 300–500 papers by PageRank** from `Analysis/results/paper_citation_metrics.csv`
   (`pagerank_cluster`). Its columns are `node` (OpenAlex id or DOI), `doi`, `year`, `institutions`,
   `global_citations`, `in_degree_cluster`, `pagerank_cluster`, `in_degree_kharagpur`, `in_degree_roorkee`.
2. Titles and journals: join on `doi` (or on `node` = `openalex_id`) with `Enrichment/out/group3_data.csv`
   (`title`, `journal_name`; take one row per paper).
3. Edges: from `Enrichment/out/citation_network.csv`, keep `edge_type == "internal"` rows whose two ends
   (`source_openalex`/`source_doi`, `target_openalex`/`target_doi`) are both in the chosen node set.
   Edge = "source cites target" (draw an arrow to the target).
4. Positions: `nx.spring_layout(G, seed=3)` (or `nx.kamada_kawai_layout`), stored as `x`, `y` per node.
5. Node attributes for the app: `label` (short title), `title` (hover: full title, journal, year, citations,
   PageRank, in-degree), `size` ∝ PageRank, `color` = institute colour (purple-grey for joint papers).
6. Useful toggles: size by **PageRank vs in-degree** (the explainer `docs/network_concepts.html` shows why they
   differ); filter by institute; filter by year.

Alternative view, if the class wants "everything": an ego network. The user picks a paper, and the app shows it
with its direct citers and cited papers, read from a pre-filtered subset.

### 5b. Authorship network → `Dashboard/data/faculty_graph.json`
This one is small enough to show whole: **1,638 faculty and 3,329 faculty–faculty edges**.
1. Nodes: `Analysis/results/faculty_centrality.csv`, with columns `roster_id` (node id), `faculty`, `institution`,
   `department`, `faculty_coauthors` (degree), `joint_papers_with_faculty`, `degree_centrality`, `betweenness`,
   `community`. Join `faculty.csv` on `roster_id` for `h_index`, `papers` and `citations` for the hover text.
2. Edges: `Enrichment/out/authorship_network.csv` rows with `a_is_faculty == b_is_faculty == "TRUE"`. Group by
   (`author_a_id`, `author_b_id`), and weight = number of distinct `paper_doi`. Mark an edge as **cross-IIT** when
   `inst_a != inst_b`; there are only 90 such pairs, which makes for a nice highlight.
3. Positions: `nx.spring_layout(G, seed=3, weight=None)` on the largest component. Put isolated faculty
   (324 of them) in a ring or hide them by default.
4. Toggles: colour by **institute** or **community**. For community colouring, give the 7 largest communities
   distinct colours and grey out the rest. Size by degree or betweenness. Filter by department. Clicking a node
   lists that person's co-authors.

### 5c. Optional: Indian collaboration map
`Enrichment/out/indian_connections.csv` (`your_inst`, `partner_inst`, `shared_papers`, `total_citations`,
`citations_from_partner`, `citations_to_partner`, `partner_kind`, `partner_openalex`) can drive a star graph:
our two IITs in the middle, the top 30 partners around them, edge width = shared papers.

## 6. Caveats to show on the dashboard (one line each)
* Data collected October 2026: **2026 is a partial year**, and citation counts are as of the collection date.
* **h-index** is computed over the faculty member's 2016–2026 papers in this dataset only, so it is lower than a
  Google Scholar career h-index.
* Papers are those whose IIT affiliation is **confirmed on the paper**. The field scope is currently **all fields**;
  the TAs' clarification said science & engineering only, and that can be restored with `SCOPE_MODE = "sci_eng"`
  in `Enrichment/scripts/scope.py`, after which you re-run the pipeline and the stats.
* About 15 % of papers have no identified faculty author. They count for the institute but not for any faculty member.
* PageRank favours older papers (Spearman ρ ≈ −0.39 with publication year).

## 7. Still to compute (small)
Slide 12 of the PPT lists **"Top 10 most-cited papers citing your institute"**. We have the citing works
(`edge_type == "in_from_indian"` in `citation_network.csv`), but not *their* citation counts. Getting them takes one
OpenAlex request per 100 works (`/works?filter=openalex:W1|W2|…&select=id,doi,display_name,cited_by_count`), using
`Enrichment/scripts/oa.py` and an API key (`OPENALEX_API_KEY`). There are 140,823 distinct citing works, so about
1,410 requests (1 credit each). Add it as a script in `Analysis/scripts/` and a table in `results/`.

## 8. Checklist before showing it
- [ ] All 11 required panels present (section 2), for both institutes, with an institute filter
- [ ] Both network panels are interactive (zoom, drag, hover)
- [ ] Same colours as the report (KGP blue, Roorkee orange); 2026 marked partial
- [ ] Looks clean and calm (section 3b): white space, ≤ 3 charts per screen, hero numbers, plain-English captions,
      readable at phone width (checked with screenshots of every tab)
- [ ] Caveats visible (section 6)
- [ ] Runs from a fresh clone: `pip install -r Dashboard/requirements.txt && streamlit run Dashboard/app.py`

# Indian Research Mapper

Mapping the research output of Indian institutes (2016–2026): publications, journal quality, and the citation and co-authorship networks that connect them.

Course project for **DPCN** (Instructor: Prof. Chittaranjan Hens), IIIT Hyderabad, 2026.

## What it does

- **Data collection**: pulls faculty publications for our assigned institutes from OpenAlex (with IRINS/Scopus as backup), matching institutes by ROR ID
- **Stats**: publication trends, Q1 share, h-index distribution, top journals, most-cited papers, research areas
- **Networks**:
  - a citation graph (directed), analysed with in-degree and PageRank
  - a co-authorship graph (undirected), analysed with degree and betweenness centrality and Louvain communities
- **Indian connections**: citation flow in and out of the institutes, plus the partner institutes they collaborate with
- **Dashboard**: an interactive view of all of the above, including network visualisations

## Repository contents

- **[WebScrape/](WebScrape/README.md)**: publication datasets for IIT Ropar, IIT Kharagpur and IIT Roorkee (2016–2026), the scraping pipeline, and the [process](WebScrape/PROCESS.md) and [results](WebScrape/RESULTS.md) write-ups
- **[Enrichment/](Enrichment/README.md)**: fills the scraped data's TODOs (OpenAlex, Scimago, CORE, ORCID), links papers to faculty, and builds the submission CSV and network files
- **[Analysis/](Analysis/README.md)**: statistics for the report and dashboard (tables in `results/`, charts in `figures/`)
- [docs/network_concepts.html](docs/network_concepts.html): explainer for the network concepts used
- `DPCN_Instruction_Note.pdf`: assignment brief
- Submission files are in [Enrichment/out/](Enrichment/out): `group3_data.csv` (brief's column format) and the three network files. The large files there use Git LFS: run `git lfs install` once before cloning/pulling

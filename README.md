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
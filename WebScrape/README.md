# WebScrape

Publications (2016–2026) of **IIT Ropar**, **IIT Kharagpur** and **IIT Roorkee**, collected from open
sources (Crossref, Europe PMC, DOAJ, INSPIRE-HEP, ORCID, DBLP, arXiv, DataCite, OpenCitations,
Semantic Scholar).

| Path | Content |
|---|---|
| `iit_ropar.json`, `iit_kharagpur.json`, `iit_roorkee.json` | Datasets: `{summary, records[]}`, one record per line |
| `rosters/` | Faculty lists (input to the person-based search) |
| `golden/` | Independent test sets and hand-checked audit samples |
| `scripts/` | Pipeline code |
| [PROCESS.md](PROCESS.md) | How the data was collected; every rule and decision |
| [RESULTS.md](RESULTS.md) | Counts, recall, precision, validation |

**Record fields:** `title, authors, year, type, venue, issn, doi, citations, references`, plus
`affiliation_status` (`verified` or `TODO: …`), `evidence` and `todo_fields`. Anything that could not be
established is `TODO`.

**Reproduce:** see [PROCESS.md §14](PROCESS.md#14-files-and-how-to-reproduce). The final rebuild is
`sh scripts/refresh_all.sh`. Run-time caches go to `raw/` and `logs/` (git-ignored).

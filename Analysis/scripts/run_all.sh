#!/bin/sh
# Re-run every statistic (tables -> ../results, charts -> ../figures) from Enrichment/out.
# Online steps, cached in ../cache after the first run (set OPENALEX_API_KEY or OPENALEX_KEY_FILE for new data):
#   fetch_openalex_extra.py  yearly citation counts, journal IF, faculty OpenAlex profiles (~200-600 credits)
#   stats_connectivity.py    topic profiles of new partners (1 credit each)
#   stats_citing_top.py      citation counts of citing works (~1,410 requests, no key needed)
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
python fetch_openalex_extra.py     # only fetches ids missing from the cache
python stats_bibliometric.py       # writes faculty.csv, used by the next three
python stats_faculty.py
python stats_journals.py
python stats_areas.py
python stats_citation.py           # writes citation_flow_partners.csv, used by stats_connectivity.py
python stats_authorship.py
python stats_connectivity.py
python stats_citing_top.py
python stats_rosters.py            # yearly faculty lists (needs WebScrape/scripts/wayback_rosters.py output)
echo STATS-DONE

#!/bin/sh
# Re-run every statistic (tables -> ../results, charts -> ../figures) from Enrichment/out.
# stats_connectivity.py needs OpenAlex only for topic profiles not yet in ../cache/topic_profiles.json (1 credit each);
# set OPENALEX_API_KEY or OPENALEX_KEY_FILE if new partners appear.
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
python stats_bibliometric.py
python stats_citation.py           # writes citation_flow_partners.csv, used by stats_connectivity.py
python stats_authorship.py
python stats_connectivity.py
echo STATS-DONE

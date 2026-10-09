#!/bin/sh
# Merge stage for one institute: union -> DOI resolution -> enrichment -> finalize -> recall.
# usage: sh run_merge.sh <inst_key>
# (OpenCitations fallback is run once at the very end: python3 opencitations.py <inst>; python3 finalize.py <inst>)
set -e
cd "$(dirname "$0")"
I=$1
L=../logs
python3 build_candidates.py $I
python3 doi_resolve.py $I | tail -1
python3 build_candidates.py $I
python3 -c "
from common import read_jsonl_gz
open('../raw/dois_$I.txt','w').write('\n'.join(c['doi'] for c in read_jsonl_gz('../raw/candidates_$I.jsonl.gz') if c['doi']))"
python3 crossref_enrich.py ../raw/dois_$I.txt | tail -1
python3 datacite_enrich.py $I | tail -1
python3 finalize.py $I > $L/finalize_$I.json
python3 eval_recall.py $I > /dev/null

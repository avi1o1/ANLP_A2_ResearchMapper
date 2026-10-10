#!/bin/sh
# Rebuild everything from cached data (no network access): enriched datasets, group3_data.csv, the three
# network files, with tests and checks along the way.
# Order matters: merge.py rewrites out/<inst>_enriched.json from ../WebScrape/<inst>.json; faculty.py then adds the faculty links
# (it reads cache/roster_supplement_<inst>.json, written by the online step roster_supplement.py).
# Online steps (only for new data): stage_a_fetch, stage_a2_title, stage_refdoi, stage_bc_indian, roster_supplement.
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
python test_rules.py > /dev/null && echo "rule tests passed"
python merge.py iit_kharagpur iit_roorkee
python faculty.py iit_kharagpur iit_roorkee
python verify.py iit_kharagpur iit_roorkee
python eval_faculty.py iit_kharagpur iit_roorkee
python export_csv.py
python build_networks.py
python verify_networks.py
echo REBUILD-DONE

#!/bin/sh
# Consistent final rebuild of all institutes from the existing caches (no new discovery):
# union -> enrichment of new DOIs -> finalize -> OpenCitations fallback -> finalize -> recall -> TODO sheet,
# then cross-institute validation. Re-run after verify_*.py / resolve_todos.py add evidence.
set -e
cd "$(dirname "$0")"
for I in iit_ropar iit_kharagpur iit_roorkee; do
  sh run_merge.sh $I
  python3 opencitations.py $I
  python3 finalize.py $I > ../logs/finalize_$I.json
  python3 eval_recall.py $I > /dev/null
  python3 export_todo.py $I
done
python3 validate.py iit_ropar iit_kharagpur iit_roorkee
echo REFRESH-DONE

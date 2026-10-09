#!/bin/sh
# Final ordered run (after discovery harvests A1-A4, B1-B2 and enrichment caches exist).
# Strict roster pass -> loose roster pass (unconfirmed only) -> arXiv pass -> merge -> OpenCitations
# fallback -> finalize -> recall. Sequential on purpose: shared caches must have a single writer.
set -e
cd "$(dirname "$0")"
for I in iit_ropar iit_kharagpur iit_roorkee; do
  if [ "$I" = "iit_ropar" ] && [ "$SKIP_ROPAR_STRICT" = 1 ]; then echo "reuse strict roster output for $I"; else python3 roster_channels.py $I; fi
  sh run_merge.sh $I
done
for I in iit_ropar iit_kharagpur iit_roorkee; do python3 roster_channels.py $I --loose; done
for I in iit_ropar iit_kharagpur iit_roorkee; do python3 roster_channels.py $I --arxiv-only; done
for I in iit_ropar iit_kharagpur iit_roorkee; do
  sh run_merge.sh $I
  python3 opencitations.py $I
  python3 finalize.py $I > ../logs/finalize_$I.json
  python3 eval_recall.py $I > /dev/null
  python3 export_todo.py $I
done
echo FINAL-DONE

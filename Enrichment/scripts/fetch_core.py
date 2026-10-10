"""Download the CORE conference rankings (portal.core.edu.au CSV export) used by ranks.py.
Editions: CORE2018, CORE2020, CORE2021, CORE2023, CORE2026 (ICORE2026) -> cache/core/<edition>.csv
The files used for the current outputs are committed in cache/core/; re-run only to refresh.
usage: python fetch_core.py"""
import os, time, requests
from oa import CACHE

D = os.path.join(CACHE, "core")
os.makedirs(D, exist_ok=True)
for ed in ("CORE2018", "CORE2020", "CORE2021", "CORE2023", "CORE2026"):
    r = requests.get("https://portal.core.edu.au/conf-ranks/",
                     params={"search": "", "by": "all", "source": ed, "sort": "arank", "page": 1, "do": "Export"},
                     headers={"User-Agent": "DPCN course project (research script)"}, timeout=120)
    r.raise_for_status()
    open(os.path.join(D, ed + ".csv"), "wb").write(r.content)
    print(ed, len(r.content), "bytes")
    time.sleep(2)

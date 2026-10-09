"""Verify every gzip cache shard decompresses fully; report rows + any corruption offset."""
import glob, gzip, zlib, sys, os
from common import RAW
bad = 0
for fn in sorted(glob.glob(os.path.join(RAW, "**", "*.jsonl.gz"), recursive=True)):
    n = 0
    try:
        with gzip.open(fn, "rt") as f:
            for _ in f:
                n += 1
    except (EOFError, zlib.error, OSError) as e:
        bad += 1
        print("CORRUPT", fn, "rows_before_error", n, type(e).__name__)
print("checked; corrupt shards:", bad)

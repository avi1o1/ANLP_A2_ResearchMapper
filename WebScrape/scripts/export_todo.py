"""Export a manual follow-up sheet: one row per record that has any TODO field.
usage: python3 export_todo.py <inst_key> -> WebScrape/todo_followup_<inst>.csv (sorted: most-cited first)"""
import os, sys, csv, json
from common import OUT
inst = sys.argv[1]
R = json.load(open(os.path.join(OUT, inst + ".json")))["records"]
rows = []
for r in R:
    if not r["todo_fields"]:
        continue
    rows.append({"record_id": r["record_id"], "todo_fields": ";".join(r["todo_fields"]), "affiliation_status": r["affiliation_status"],
                 "year": r["year"], "title": r["title"], "doi": r["doi"], "venue": r["venue"],
                 "citations": r["citations"], "found_via_person": "; ".join(r["found_via_person"])})
rows.sort(key=lambda x: -(x["citations"] if isinstance(x["citations"], int) else -1))
fn = os.path.join(OUT, f"todo_followup_{inst}.csv")
with open(fn, "w") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(fn, len(rows), "of", len(R))

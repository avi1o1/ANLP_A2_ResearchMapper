"""Recall evaluation against the independent golden set.

Match rule: same normalised DOI, else normalised-title equality, else token-Jaccard >= 0.8 with
|year diff| <= 1. Each miss is diagnosed: in final output? in candidates (then why dropped)? in rejected log?
Writes WebScrape/golden/recall_<inst>.md and misses_<inst>.csv.

usage: python3 eval_recall.py <inst_key>
"""
import os, re, sys, csv, json, html, unicodedata, collections
from common import OUT, RAW, read_jsonl_gz, norm_doi

inst = sys.argv[1]


def toks(t):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", t)


def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / max(1, len(a | b))


def nd(d):
    d = norm_doi(d)
    if d and d.startswith("arxiv:"):
        d = "10.48550/arxiv." + d[6:]
    return d


recs = json.load(open(os.path.join(OUT, inst + ".json")))["records"]
_ufn = os.path.join(OUT, f"candidates_unconfirmed_{inst}.json")
unconf = json.load(open(_ufn))["records"] if os.path.exists(_ufn) else []
cands = list(read_jsonl_gz(os.path.join(RAW, f"candidates_{inst}.jsonl.gz")))
rej = list(read_jsonl_gz(os.path.join(OUT, "logs", f"rejected_{inst}.jsonl.gz")))


def index(items, doi_f, title_f, year_f):
    by_doi, by_t, lst = {}, {}, []
    for it in items:
        d = doi_f(it)
        if d:
            by_doi[d] = it
        tk = toks(title_f(it) if isinstance(title_f(it), str) else "")
        by_t.setdefault("".join(tk), it)
        lst.append((set(tk), year_f(it), it))
    return by_doi, by_t, lst


def find(ix, doi, title, year):
    by_doi, by_t, lst = ix
    if doi and doi in by_doi:
        return by_doi[doi], "doi"
    tk = toks(title)
    if "".join(tk) in by_t:
        return by_t["".join(tk)], "title"
    st = set(tk)
    if len(st) >= 4:
        for s, y, it in lst:
            if (not year or not y or abs(int(y) - int(year)) <= 1) and jacc(st, s) >= 0.8:
                return it, "fuzzy"
    return None, None


def recdoi(r):
    ds = [nd(r["doi"])] if r["doi"] != "TODO" else []
    return ds[0] if ds else None


ix_rec = index(recs, recdoi, lambda r: r["title"], lambda r: r["year"])
# also index preprint versions merged into published records
for r in recs:
    for p in r.get("preprint_versions", []) or []:
        ix_rec[0][nd(p)] = r
ix_unc = index(unconf, recdoi, lambda r: r["title"], lambda r: r["year"])
ix_cand = index(cands, lambda c: c["doi"], lambda c: c["title"], lambda c: c["year"])
ix_rej = index(rej, lambda c: c["key"] if not c["key"].startswith("t:") else None, lambda c: c["title"], lambda c: c["year"])

gold = list(csv.DictReader(open(os.path.join(OUT, "golden", f"golden_{inst}.csv"))))
res = []
for g in gold:
    y = g.get("year")
    y = int(y) if y and y.isdigit() else None
    r, how = find(ix_rec, nd(g.get("doi")), g["title"], y)
    diag = "found"
    status = r["affiliation_status"][:30] if r else ""
    if not r:
        c, _ = find(ix_cand, nd(g.get("doi")), g["title"], y)
        rj, _ = find(ix_rej, nd(g.get("doi")), g["title"], y)
        uc, _ = find(ix_unc, nd(g.get("doi")), g["title"], y)
        diag = ("in_unconfirmed_file" if uc else "rejected_contradicted" if rj else
                ("in_candidates_but_dropped" if c else "not_discovered"))
    res.append({**g, "match": how or "", "diagnosis": diag, "status": status})
n = len(res); f = sum(r["diagnosis"] == "found" for r in res)
gerr = sum(r["diagnosis"] == "rejected_contradicted" for r in res)
wd = [r for r in res if nd(r.get("doi"))]
fd = sum(r["diagnosis"] == "found" for r in wd)
lines = [f"# Recall vs golden set — {inst}", "", f"Golden papers: {n}; found: {f}; **recall = {f / n:.1%}**",
         f"Golden papers with a DOI (i.e. registered/indexable): {len(wd)}; found: {fd}; **DOI recall = {fd / max(1, len(wd)):.1%}**",
         f"Golden entries refuted by publisher-deposited affiliations (paper carries another institution for the listed author; "
         f"i.e. golden-set errors): {gerr}; recall excluding them = {f / max(1, n - gerr):.1%}", ""]
for dim in ("evidence_source", "type", "year", "confidence"):
    c = collections.defaultdict(lambda: [0, 0])
    for r in res:
        c[r.get(dim, "")][0] += 1; c[r.get(dim, "")][1] += r["diagnosis"] == "found"
    lines += [f"## by {dim}", "", "| value | n | found | recall |", "|---|---|---|---|"]
    lines += [f"| {k} | {a} | {b} | {b / a:.0%} |" for k, (a, b) in sorted(c.items())] + [""]
lines += [f"Recall if the unconfirmed-candidates file were included: {(f + sum(r['diagnosis'] == 'in_unconfirmed_file' for r in res)) / n:.1%}", ""]
lines += ["## miss diagnosis", ""] + [f"* {k}: {v}" for k, v in collections.Counter(r["diagnosis"] for r in res if r["diagnosis"] != "found").items()]
lines += ["", "## found: affiliation status of matched records", ""] + [f"* {k}: {v}" for k, v in collections.Counter(r["status"] for r in res if r["diagnosis"] == "found").items()]
open(os.path.join(OUT, "golden", f"recall_{inst}.md"), "w").write("\n".join(lines) + "\n")
with open(os.path.join(OUT, "golden", f"misses_{inst}.csv"), "w") as fh:
    w = csv.DictWriter(fh, fieldnames=list(res[0].keys())); w.writeheader(); [w.writerow(r) for r in res if r["diagnosis"] != "found"]
print("\n".join(lines))

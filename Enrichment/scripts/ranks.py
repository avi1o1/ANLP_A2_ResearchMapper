"""Journal quartile (Scimago SJR) and conference rank (CORE) lookups. No network access.
Journals:  exact ISSN join against Scimago's yearly CSV for the publication year (2026 -> latest file available).
           'SJR Best Quartile' is used (a journal listed in several categories gets its best one).
Conferences: CORE edition in force at publication: <=2019 CORE2018, 2020 CORE2020, 2021-22 CORE2021,
           2023-25 CORE2023, 2026 ICORE2026. A venue matches a CORE entry only if
           (a) the cleaned names are identical, or
           (b) the CORE acronym appears in the venue as a separate upper-case token AND the name tokens overlap
               (Jaccard >= 0.5).  Anything else stays blank.
Scimago files: put the CSVs downloaded from https://www.scimagojr.com/journalrank.php (one per year,
           'Download data') into cache/scimago/ ; the year is read from the file name."""
import os, re, csv, glob
from oa import CACHE

STOP = {"of", "the", "on", "and", "in", "for", "a", "an", "&", "to"}


def issn_key(s):
    s = re.sub(r"[^0-9Xx]", "", s or "").upper()
    return s if len(s) == 8 else None


# ---------------- Scimago
SJR = {}   # year -> {issn: (quartile, title, areas)}
for fn in glob.glob(os.path.join(CACHE, "scimago", "*.csv")):
    m = re.search(r"(20\d\d)", os.path.basename(fn))
    if not m:
        continue
    raw = open(fn, encoding="utf8", errors="replace").read()
    if raw.lstrip().startswith("<"):
        continue   # an HTML challenge page, not data
    rows = csv.DictReader(raw.splitlines(), delimiter=";")
    tab = {}
    for r in rows:
        q = (r.get("SJR Best Quartile") or "").strip()
        if q not in ("Q1", "Q2", "Q3", "Q4"):
            continue
        for part in (r.get("Issn") or "").split(","):
            k = issn_key(part)
            if k:
                tab[k] = (q, r.get("Title"), r.get("Areas"))
    SJR[int(m.group(1))] = tab


def quartile(issns, year):
    if not SJR or not isinstance(issns, list) or not isinstance(year, int):
        return None
    y = year if year in SJR else max(SJR)          # 2026 (partial year) -> latest file
    if year < min(SJR):
        y = min(SJR)
    for s in issns:
        k = issn_key(s)
        if k and k in SJR[y]:
            q, title, areas = SJR[y][k]
            return {"quartile": q, "sjr_year": y, "sjr_title": title, "sjr_areas": areas}
    return None


# ---------------- CORE
def clean(name):
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b(19|20)\d\d\b", " ", s)
    s = re.sub(r"\b\d+(st|nd|rd|th)\b", " ", s)
    s = re.sub(r"\bproceedings\b|\bproc\.", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in STOP and w != "annual")


CORE = {}
for fn in glob.glob(os.path.join(CACHE, "core", "*.csv")):
    ed = os.path.basename(fn)[:-4]
    ents = []
    for row in csv.reader(open(fn, encoding="utf8", errors="replace")):
        if len(row) >= 5 and row[4] in ("A*", "A", "B", "C"):
            ents.append({"title": row[1], "acr": row[2].strip(), "rank": row[4], "clean": clean(row[1]),
                         "toks": set(clean(row[1]).split())})
    CORE[ed] = ents


def core_edition(year):
    if year <= 2019: return "CORE2018"
    if year == 2020: return "CORE2020"
    if year <= 2022: return "CORE2021"
    if year <= 2025: return "CORE2023"
    return "CORE2026"


# Satellite tracks are not the main conference: never give them the main conference's rank.
NOT_MAIN = re.compile(r"workshop|findings of|extended abstract|companion|adjunct|doctoral|poster|demo|tutorial|student research", re.I)
# Exact venue names whose wording defeats the generic rule (checked by hand against the CORE files).
ALIAS = {"aaai conference artificial intelligence": "AAAI",
         "international aaai conference web social media": "ICWSM"}


def core_rank(venue, year):
    if not isinstance(venue, str) or not isinstance(year, int) or NOT_MAIN.search(venue):
        return None
    ed = core_edition(year)
    c = clean(venue)
    if c in ALIAS:
        for e in CORE.get(ed, []):
            if e["acr"] == ALIAS[c]:
                return {"core_rank": e["rank"], "core_edition": ed, "core_title": e["title"], "core_match": "alias"}
        return None
    vt = set(c.split())
    upper = set(re.findall(r"\b[A-Z][A-Za-z0-9\-]*[A-Z0-9]\b", venue))
    for e in CORE.get(ed, []):
        if e["clean"] and c == e["clean"]:
            return {"core_rank": e["rank"], "core_edition": ed, "core_title": e["title"], "core_match": "name"}
    for e in CORE.get(ed, []):
        if len(e["acr"]) >= 3 and e["acr"] in upper:
            jac = len(vt & e["toks"]) / max(1, len(vt | e["toks"]))
            if jac >= 0.5:
                return {"core_rank": e["rank"], "core_edition": ed, "core_title": e["title"], "core_match": "acronym+name"}
    return None

"""Shared loading, definitions and chart style for the Group 3 statistics (IIT Kharagpur, IIT Roorkee).
Inputs (read-only): ../../Enrichment/out/  (enriched datasets + network files built by Enrichment/scripts).
Analysis set = the submission set: affiliation 'verified' AND in field scope (Enrichment/scripts/scope.py; currently
all fields) - the same papers as group3_data.csv.
Citations = the dataset's citation count at collection date (Crossref; OpenAlex where Crossref had none);
papers whose count is unknown are left out of citation statistics (never counted as 0)."""
import os, sys, csv, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # Analysis/
A2 = os.path.dirname(ROOT)
ENRICH = os.path.join(A2, "Enrichment")
DATA = os.path.join(ENRICH, "out")
RES = os.path.join(ROOT, "results")
FIG = os.path.join(ROOT, "figures")
CACHE = os.path.join(ROOT, "cache")
for d in (RES, FIG, CACHE):
    os.makedirs(d, exist_ok=True)
sys.path.insert(0, os.path.join(ENRICH, "scripts"))           # reuse oa.py (OpenAlex client) where needed
csv.field_size_limit(10 ** 8)

INSTS = {"iit_kharagpur": "IIT Kharagpur", "iit_roorkee": "IIT Roorkee"}
YEARS = list(range(2016, 2027))
PARTIAL_YEAR = 2026                                            # collected in October 2026

# ---------------------------------------------------------------- data
def load_records(inst, analysis_set=True):
    """Records of one institute (dicts as in enriched JSON); by default only the analysis (submission) set."""
    out = []
    with open(os.path.join(DATA, inst + "_enriched.json"), encoding="utf8") as fh:
        for line in fh:
            s = line.strip().rstrip(",")
            if not s.startswith('{"title"'):
                continue
            r = json.loads(s)
            if analysis_set and (r["affiliation_status"] != "verified" or r["sci_eng_scope"]["in_scope"] is not True):
                continue
            out.append(r)
    return out


def paper_key(r):
    d = r["doi"]
    if isinstance(d, str) and not d.startswith("TODO"):
        return d.lower()
    return r.get("openalex_id") or r["record_id"]


def cites(r):
    return r["citations"] if isinstance(r["citations"], int) else None


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(name, rows, cols=None):
    path = os.path.join(RES, name)
    cols = cols or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def h_index(citation_counts):
    c = sorted((x for x in citation_counts if x is not None), reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


# ---------------------------------------------------------------- chart style (validated palette, light surface)
SURFACE = "#fcfcfb"
TEXT, TEXT2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
COLOR = {"IIT Kharagpur": "#2a78d6", "IIT Roorkee": "#eb6834"}   # entity colours: fixed, never by rank
ORDINAL = ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef"]          # dark -> light (Q1 darkest, Q4 lightest)


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": TEXT2, "axes.titlecolor": TEXT, "axes.titlesize": 12,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.8, "axes.axisbelow": True, "xtick.color": TEXT2, "ytick.color": TEXT2,
        "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.labelsize": 10, "legend.frameon": False,
        "legend.fontsize": 9, "font.family": "DejaVu Sans", "lines.linewidth": 2, "figure.dpi": 110,
    })


def save(fig, name):
    path = os.path.join(FIG, name)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


SHORT = {"Academy of Scientific and Innovative Research": "AcSIR (CSIR academy)",
         "Vellore Institute of Technology University": "VIT University",
         "University of Petroleum and Energy Studies": "UPES Dehradun",
         "SRM Institute of Science and Technology": "SRM IST",
         "Council of Scientific and Industrial Research": "CSIR",
         "Birla Institute of Technology, Mesra": "BIT Mesra",
         "Indian Institute of Engineering Science and Technology, Shibpur": "IIEST Shibpur",
         "Central Building Research Institute": "CSIR-CBRI Roorkee",
         "S.N. Bose National Centre for Basic Sciences": "S.N. Bose Centre",
         "Homi Bhabha National Institute": "HBNI"}


def short_name(name, width=34):
    """Readable label for an institution: known abbreviations, then common prefixes, then an ellipsis."""
    n = SHORT.get(name, name)
    for a, b in (("Indian Institute of Technology", "IIT"), ("National Institute of Technology", "NIT"),
                 ("Indian Institute of Science Education and Research", "IISER"), ("Indian Institute of Science", "IISc"),
                 ("Indian Institute of Information Technology", "IIIT")):
        n = n.replace(a, b)
    return n if len(n) <= width else n[:width - 1].rstrip() + "…"

"""Unit tests for the name and department rules in faculty.py (no data or network needed).
Every case is a real situation met in the data. usage: python test_rules.py   (exit code 1 on any failure)"""
import sys
from faculty import compatible, dept_in, named_depts

NAME_CASES = [
    ("Sudhakar Reddy Kusam", "Kusam Sudhakar Reddy", True),     # family name written first on the roster
    ("P. Gopinath", "Gopinath Packirisamy", True),               # family name as an initial
    ("Tungala Raja Sekhar", "T. Raja Sekhar", True),             # paper fuller than roster
    ("Brajesh Kumar Kaushik", "B. K. Kaushik", True),
    ("Suman Maity", "Suman Kalyan Maity", True),                 # middle name omitted
    ("K. Biswas", "Koushik Biswas", True),
    ("Maity, Suman K.", "Suman Kalyan Maity", True),             # "Surname, Given" format
    ("P. C. Ashok Kumar", "P. C. Ashwin Kumar", False),          # different person
    ("Anil Kumar", "Ajay Kumar", False),
    ("Kalyan Maity", "Suman Kalyan Maity", False),               # first names differ
    ("Amit Ghosh", "Amitava Ghosh", False),
]
DEPT_CASES = [
    ("Chemistry", "Department of Chemistry, Indian Institute of Technology Roorkee, Roorkee 247667, India", True),
    ("Chemistry", "Department of Chemical Engineering, IIT Roorkee", False),
    ("Electronics and Electrical Communication Engg.", "Dept. of Electronics & Electrical Communication Engineering, IIT Kharagpur", True),
    ("Centre for Ocean, River, Atmosphere and Land Sciences (CORAL)", "CORAL, Indian Institute of Technology Kharagpur", True),
    ("Applied Mathematics and Scientific Computing (Saharanpur)", "Department of Mathematics, IIT Roorkee", False),
    ("Biosciences and Bioengineering", "Department of Biotechnology, IIT Roorkee", False),
    ("Mechanical and Industrial Engineering", "Department of Mechanical Engineering, IIT Kharagpur", False),
]
D = ["Electrical Engineering", "Electronics and Electrical Communication Engg.", "Mechanical Engineering", "Chemistry"]
SPECIFIC_CASES = [
    ("Department of Electronics and Electrical Communication Engineering, IIT Kharagpur", {"Electronics and Electrical Communication Engg."}),
    ("Department of Electrical Engineering, IIT Kharagpur", {"Electrical Engineering"}),
]

fails = 0
for a, b, want in NAME_CASES:
    got = compatible(a, b)
    fails += got != want
    print("OK  " if got == want else "FAIL", "name", a, "~", b, "->", got)
for d, a, want in DEPT_CASES:
    got = dept_in(d, [a])
    fails += got != want
    print("OK  " if got == want else "FAIL", "dept", d, "<-", a[:60], "->", got)
for a, want in SPECIFIC_CASES:
    got = named_depts([a], D)
    fails += got != want
    print("OK  " if got == want else "FAIL", "most specific", a[:60], "->", sorted(got))
# common-family-name guard in fits(): needs a roster context with >= 3 people sharing the family name
from faculty import fits
P = lambda n, i: {"rid": str(i), "name": n, "orcids": set()}
kumars = [P("P. C. Ashwin Kumar", 1), P("Ashok Kumar", 2), P("Vinod Kumar", 3)]
by_s = {"kumar": kumars}
for paper, person, want in [("Piyush Kumar", kumars[0], False), ("Ashok Kumar", kumars[1], True),
                            ("P. C. Ashwin Kumar", kumars[0], True)]:
    got = fits(paper, None, person, {}, by_s)
    fails += got != want
    print("OK  " if got == want else "FAIL", "common surname", paper, "->", person["name"], got)
print("failures:", fails)
sys.exit(1 if fails else 0)

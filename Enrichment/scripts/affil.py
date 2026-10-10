"""Affiliation-string classifier.  classify(inst, s) -> 'iit' | 'other' | 'uncertain' | None
None  = string does not mention the institute's city/PIN at all.
Rules were derived empirically by inspecting every distinct affiliation string that contains the
city token (see METHODOLOGY.md §3). Manual decisions for 'uncertain' strings live in
WebScrape/logs/affil_manual_<inst>.tsv (string<TAB>iit|other) and override the rules.
"""
import re, os, csv
LOGS = "__no_manual_overrides__"  # logs/ is not in the repo; manual overrides unavailable

WS = re.compile(r"\s+")
# fuzzy "Indian Institute of Technology" (covers Institue/Institite/Instituteof/Inst./missing 'of')
IIT = re.compile(r"indi\w*\s*ins\w*\.?\s*(of\s*)?(te[ch]\w*|ropar|rupnagar|kharagpur|roorkee)|indian\s+intitute\s+of\s+tech|\biit\b|\bi\s*\.\s*i\s*\.\s*t\b|iit\s*-?\s*(rpr|ropar|kgp|kharagpur)"
                 r"|iitkgp|iitrpr|indian\s+institute\s+technology|indi\s*\|\s*an\s+institute|[it]nstitute of technology,?\s*(\(iit\)\s*)?(kharagpur|ropar|rupnagar)"
                 r"|\biit\d|e\s*(&|&amp;|&#x0026;)\s*eceiit|@iitrpr\.ac\.in|@iitkgp\.ac\.in|iitkgp\.ac\.in|iitrpr\.ac\.in", re.I)
CITY = {
    "iit_ropar": re.compile(r"\b(ropar|rupnagar|roopnagar)\b|\b140001\b|iitrpr", re.I),
    "iit_kharagpur": re.compile(r"\b(kharagpur|kharagapur|kharagur|kharapur|khragpur|karagpur|khargpur|kharagpu|kgp|iitkgp)\b|\b721302\b", re.I),
    # Saharanpur (247001) = IIT Roorkee's Saharanpur campus; only counts together with an IIT pattern (see DEPT_CITY)
    "iit_roorkee": re.compile(r"\b(roorkee|roorke|rorkee|roorkie|iitr\.ac\.in|saharanpur)\b|\b247667\b|\b247001\b", re.I),
}
# Unit names that only exist at the given IIT (used when the string omits "IIT")
# Unit names unique to the given IIT (count even without the city token)
UNITS = {
    "iit_ropar": re.compile(r"school of mechanical,?\s*(\||,)?\s*materials\s*(&|and)\s*energy\s*engg?\w*.*(ropar|rupnagar|punjab)|indian institute of ropar|iit\s*ropar|ihub.?awadh", re.I),
    "iit_kharagpur": re.compile(r"vinod gupta school|rajiv gandhi school of intellectual|rajendra mishra school|g\.?\s*s\.?\s*sanyal school|ranbir (and|&) chitra gupta|"
                                r"b\.?\s*c\.?\s*roy (multi|technology)|p\.?\s*k\.?\s*sinha cent|kalpana chawla space|subir chowdhury school|deysarkar cent", re.I),
    "iit_roorkee": re.compile(r"iit\s*roorkee|mehta family school|saharanpur campus.*(iit|indian institute)|"
                              r"\biitr\b.*\broorkee\b|\broorkee\b.*\biitr\b|"   # "IITR" only with Roorkee (CSIR-IITR is in Lucknow)
                              r"polymer (and|&) process engineering.*(saharanpur|247001)|(saharanpur|247001).*polymer (and|&) process engineering", re.I),
}
# Generic unit names: count only together with the city token (rule 4 below handles them)
# State-level rule: IIT pattern + the state, with no other IIT city, -> this IIT (only IIT in that state)
STATE = {"iit_ropar": re.compile(r"\bpunjab\b", re.I), "iit_kharagpur": re.compile(r"west\s*bengal|\bw\.?\s*b\.?\b", re.I),
         "iit_roorkee": re.compile(r"uttarakhand|uttaranchal", re.I)}
# city tokens that may support the department-only rule (Saharanpur excluded: many unrelated institutions)
DEPT_CITY = {"iit_ropar": None, "iit_kharagpur": None,
             "iit_roorkee": re.compile(r"\b(roorkee|roorke|rorkee)\b|\b247667\b", re.I)}
OTHER_IIT_CITY = re.compile(r"bombay|mumbai|madras|chennai|delhi|kanpur|roorkee|guwahati|hyderabad|gandhinagar|jodhpur|patna|bhu|varanasi|indore|mandi|"
                            r"bhubaneswar|tirupati|jammu|goa|palakkad|dharwad|bhilai|dhanbad|ism|ropar|rupnagar|kharagpur|engineering science and technology|"
                            r"information technology|science education|drishti", re.I)

# Other organisations located in the same city/district (never this IIT)
OTHER = {
    "iit_ropar": re.compile(r"pharmacy|shivalik|lamrin|global college|saraswati nursing|aimil|bangladesh|nano science and technology\b.*mohali|"
                            r"govt\.?|government|college|nursing|polytechnic|hospital|school of education|university(?!.*indian institute)|"
                            r"agroparistech|ropar wetland|forest|kendriya|army|bhaddal|infrared vision|nielit|electronics and information technology|"
                            r"beijing|hanoi|vietnam|china|assam|guwahati|gcet|rayat|path lab|dental|polyclinic|medical officer|"
                            r"institute of engineering and technology|ch nangal", re.I),
    "iit_kharagpur": re.compile(r"kharagpur college|hijli college|railway|south eastern|midnapore|medinipur|vidyasagar|prabhat kumar|"
                                r"silda|ramakrishna|kgp\s*hospital|sub-?divisional|nursing|polytechnic|government|govt|"
                                r"west bengal state|kendriya|airforce|air force station|\bgdc\b|bremerhaven|kazakh|phthisio|almaty|bern\b|poland|forensic|"
                                r"tata steel|tata metaliks|dental|institute of chemical technology|bhubaneswar|bhatter|jadavpur|"
                                r"institute of management|national institute of technology|engineering science and technology|"
                                r"munger|koneru|berhmpur|berhampur|massey|kangsabati|hijli co|homoeopathic|bhawanipur|edutainment|"
                                r"independent researcher|institute for clarity|college", re.I),
    "iit_roorkee": re.compile(r"national institute of hydrology|\bnih\b|central building research|\bcbri\b|college of engineering roorkee|\bcoer\b|"
                              r"roorkee institute of technology|roorkee college|quantum university|\bb\.?s\.?m\.?\b|bengal engineer|"
                              r"toxicology research|csir-iitr|cdri|government|govt|medical college|hospital|polytechnic|nursing|pharmacy|"
                              r"maa shakumbhari|glocal university|j\.?\s*v\.?\s*jain|munna lal|tula|college|uttar pradesh technical|"
                              r"irrigation research institute|\bciet\b|army|cantonment|motherhood|motherwood|haridwar university|patanjali|arogyam|"
                              r"shobhit|adarsh vijendra|pulp (and|&|&amp;) paper research|cppri|tarawati|pritam|suraksha|parenterals|green grahi|"
                              r"private practice|east china|forest research institute|galgotias|\brims\b|pvt|ltd|universit|research institute|"
                              r"national institutt?e of technology|paramedical|foundation", re.I),
}
DEPT = re.compile(r"\b(department|dept\.?|school|centre|center|coe\w*)\b", re.I)
ORGWORD = re.compile(r"universit|college|institute of science|institute of biomedical|corporate|hospital|ltd|pvt|inc\b|gmbh|abb\b", re.I)
_manual = {}


def manual(inst):
    if inst not in _manual:
        m = {}
        fn = os.path.join(LOGS, f"affil_manual_{inst}.tsv")
        if os.path.exists(fn):
            for row in csv.reader(open(fn), delimiter="\t"):
                if len(row) >= 2:
                    m[row[0]] = row[1]
        _manual[inst] = m
    return _manual[inst]


def norm(s):
    return WS.sub(" ", s or "").strip()


def classify(inst, s):
    s = norm(s)
    if not CITY[inst].search(s) and not UNITS[inst].search(s):
        if IIT.search(s) and STATE[inst].search(s):
            other = OTHER_IIT_CITY.sub("", s) != s
            return None if other else "iit"
        return None
    m = manual(inst).get(s)
    if m:
        return m
    if IIT.search(s) or UNITS[inst].search(s):
        # an IIT mention plus the city is decisive (even if a college is also named in the same string,
        # because Crossref sometimes concatenates multiple affiliations of one author)
        return "iit"
    if OTHER[inst].search(s):
        return "other"
    # department/school/centre named, city present, no other organisation -> this IIT (the IITs are
    # the only multi-department research institutions in Kharagpur 721302 / Rupnagar 140001)
    if DEPT.search(s) and not ORGWORD.search(s) and (DEPT_CITY[inst] is None or DEPT_CITY[inst].search(s)):
        return "iit"
    return "uncertain"

"""Check the faculty profile links shown on the dashboard, so dead ones can be left out.
Checks the institute profile, homepage, DBLP and IRINS links of the faculty in Analysis/results/faculty.csv.
Google Scholar, ORCID and Scopus links are not checked: they are stable IDs, and Scholar blocks automated requests.
Output: link_status.json ({url: HTTP status, or "dns" / "error"}). build_data.py drops links with 404, 410 or "dns";
any other result (403, timeouts, ...) keeps the link, because many institute sites refuse scripts but work in a browser.
Online step, about 2,000 requests. usage: python Dashboard/site/check_links.py   then   python Dashboard/site/build_data.py"""
import json, socket, concurrent.futures as cf
import requests
import build_data as bd

CHECKED = ("profile", "home", "dblp", "irins")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DPCN-dashboard-link-check"}


def status(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True, stream=True)
        r.close()
        return r.status_code
    except requests.exceptions.ConnectionError as e:
        cause = e
        while cause is not None:                          # unwrap to see if the host name does not resolve
            if isinstance(cause, socket.gaierror):
                return "dns"
            cause = cause.__cause__ or cause.__context__
        return "error"
    except requests.RequestException:
        return "error"


def main():
    ids = {r["roster_id"] for r in bd.rd("faculty.csv")}
    links = bd.faculty_links(drop_dead=False)
    urls = sorted({L[k] for rid, L in links.items() if rid in ids for k in CHECKED if k in L})
    print(len(urls), "links to check")
    with cf.ThreadPoolExecutor(16) as ex:
        res = dict(zip(urls, ex.map(status, urls)))
    for u in [u for u, s in res.items() if s in (404, 410, "dns", "error")]:   # retry failures one by one
        res[u] = status(u)
    bad = sum(1 for s in res.values() if s in (404, 410, "dns"))
    if bad > 0.1 * len(res):     # this many dead links means the network failed, not the links: keep the old file
        raise SystemExit(f"{bad} of {len(res)} links failed; looks like a network problem, {bd.LINK_STATUS} not written")
    with open(bd.LINK_STATUS, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=0, sort_keys=True)
    summary = {}
    for s in res.values():
        summary[str(s)] = summary.get(str(s), 0) + 1
    print("results:", dict(sorted(summary.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()

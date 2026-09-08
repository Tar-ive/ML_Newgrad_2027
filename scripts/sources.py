"""Fetch new-grad postings from the community tracker repos.

Phase 1 of this project aggregates the repos that already do the scraping.
Each fetcher returns a list of records in one common shape so aggregate.py
never has to know where a posting came from.
"""
import json
import re
import time
import urllib.request

UA = {"User-Agent": "ML_Newgrad_2027/1.0 (+https://github.com/Tar-ive/ML_Newgrad_2027)"}
TIMEOUT = 60

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}
US_HINTS = re.compile(r"\b(usa|united states|remote in usa|u\.s\.)\b", re.I)

# Postings sometimes arrive with no location field at all; these tokens in the
# title are enough to keep them off the US page.
NON_US = re.compile(
    r"\b(india|hyderabad|bangalore|bengaluru|chennai|pune|gurgaon|noida|mumbai|"
    r"china|beijing|shanghai|shenzhen|singapore|tokyo|japan|korea|seoul|taiwan|"
    r"london|\buk\b|united kingdom|ireland|dublin|germany|munich|berlin|zurich|"
    r"switzerland|france|paris|amsterdam|netherlands|poland|warsaw|krakow|"
    r"israel|tel aviv|australia|sydney|canada|toronto|vancouver|montreal|"
    r"mexico|brazil|emea|apac)\b", re.I)


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _json(url):
    return json.loads(_get(url))


def _text(url):
    return _get(url).decode("utf-8", "replace")


def is_usa(locations, title=""):
    """True unless something looks non-US. Ambiguous postings count as US."""
    if not locations:
        return not NON_US.search(title or "")
    for loc in locations:
        loc = (loc or "").strip()
        if US_HINTS.search(loc):
            return True
        tail = loc.split(",")[-1].strip().upper()
        if tail in US_STATES:
            return True
        if "REMOTE" in loc.upper() and "," not in loc:
            return True
    return False


def record(company, title, url, locations, posted, source,
           company_url=None, category=None, salary=None):
    return {
        "company": (company or "").strip(),
        "title": re.sub(r"\s+", " ", (title or "")).strip(),
        "url": (url or "").strip(),
        "locations": [l.strip() for l in (locations or []) if l and l.strip()],
        # Day granularity: speedyapply exposes only a relative age, so a
        # finer timestamp would churn on every refresh without meaning.
        "date_posted": (int(posted) // 86400) * 86400 if posted else None,
        "source": source,
        "company_url": company_url or None,
        "category": category,
        "salary": salary,
    }


def from_listings_json(url, source, branches=("dev", "main")):
    """SimplifyJobs / vanshb03 style listings.json (identical schema)."""
    data = None
    for branch in branches:
        try:
            data = _json(url.format(branch=branch))
            break
        except Exception:
            continue
    if data is None:
        return []
    out = []
    for x in data:
        if not x.get("active") or not x.get("is_visible", True):
            continue
        out.append(record(
            x.get("company_name"), x.get("title"), x.get("url"),
            x.get("locations"), x.get("date_posted"), source,
            company_url=x.get("company_url") or None,
            category=x.get("category"),
        ))
    return out


ROW = re.compile(r"^\|(.+)\|$")
HREF = re.compile(r'href="([^"]+)"')
STRONG = re.compile(r"<strong>(.*?)</strong>")
AGE = re.compile(r"(\d+)d")
SALARY = re.compile(r"\$(\d+)k?/(yr|hr)")


def from_speedyapply(md_url, source):
    """Parse speedyapply's rendered markdown tables back into records.

    Their columns are: Company | Position | Location | [Salary] | Posting | Age.
    Age is relative, so date_posted is reconstructed from today.
    """
    try:
        md = _text(md_url)
    except Exception:
        return []
    now = int(time.time())
    out = []
    for line in md.splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split(" | ")]
        if len(cells) < 5 or cells[0].startswith("---") or cells[0] == "Company":
            continue
        company_m = STRONG.search(cells[0])
        if not company_m:
            continue
        company_href = HREF.search(cells[0])
        apply_cell = cells[-2]
        job_href = HREF.search(apply_cell)
        if not job_href:
            continue
        age_m = AGE.search(cells[-1])
        posted = now - int(age_m.group(1)) * 86400 if age_m else None
        salary = None
        if len(cells) >= 6:
            s = SALARY.search(cells[3])
            if s:
                salary = f"${s.group(1)}k/{s.group(2)}" if "k" in cells[3] else cells[3]
        out.append(record(
            company_m.group(1), cells[1], job_href.group(1),
            [l.strip() for l in cells[2].split(",")] and [cells[2]],
            posted, source,
            company_url=company_href.group(1) if company_href else None,
            category="AI/ML",
            salary=salary,
        ))
    return out


SOURCES = [
    ("simplify", lambda: from_listings_json(
        "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/{branch}/.github/scripts/listings.json",
        "simplify")),
    ("vanshb03", lambda: from_listings_json(
        "https://raw.githubusercontent.com/vanshb03/New-Grad-2027/{branch}/.github/scripts/listings.json",
        "vanshb03")),
    ("speedyapply-usa", lambda: from_speedyapply(
        "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main/NEW_GRAD_USA.md",
        "speedyapply")),
    ("speedyapply-intl", lambda: from_speedyapply(
        "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main/NEW_GRAD_INTL.md",
        "speedyapply")),
]


def fetch_all():
    """Fetch every source, tolerating individual failures."""
    records, report = [], []
    for name, fn in SOURCES:
        try:
            rows = fn()
            records.extend(rows)
            report.append((name, len(rows), None))
        except Exception as e:
            report.append((name, 0, str(e)))
    return records, report


if __name__ == "__main__":
    recs, rep = fetch_all()
    for name, n, err in rep:
        print(f"{name:20} {n:6}  {err or ''}")
    print(f"{'TOTAL':20} {len(recs):6}")

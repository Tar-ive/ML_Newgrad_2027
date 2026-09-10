"""Fetch new-grad postings from the community tracker repos.

Phase 1 of this project aggregates the repos that already do the scraping.
Each fetcher returns a list of records in one common shape so aggregate.py
never has to know where a posting came from.
"""
import concurrent.futures as futures
import datetime
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
           company_url=None, category=None, salary=None, experience=None,
           description=None):
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
        # Years of experience required, when a source states it. None = unknown.
        "experience": experience,
        # Full job text where a source ships it. Used by the classifier to
        # promote a software engineering title, then dropped before the record
        # is stored -- descriptions are megabytes and nothing renders them.
        "description": description,
    }


def parse_date(value):
    """Epoch seconds from the date shapes the trackers use, or None.

    Sources spell the same day as "2026-09-10" and as
    "2026-09-09T12:26:41.000Z"; a few already hand over epoch seconds.
    """
    if value in (None, "", "Unknown"):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace("Z", "+00:00")
    for shape in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            return int(datetime.datetime.strptime(text, shape)
                       .replace(tzinfo=datetime.timezone.utc).timestamp())
        except ValueError:
            continue
    return None


def _pick(row, field):
    """Read a mapped field, which may be a key name or a function of the row."""
    if field is None:
        return None
    return field(row) if callable(field) else row.get(field)


def from_json_repo(url, source, spec, branches=("main", "master", "dev")):
    """Read any tracker that publishes a JSON array of postings.

    Every repo invents its own field names, so `spec` maps ours onto theirs.
    A spec value is either a key name or a function of the row, and `keep`
    filters out the rows that are not full-time new-grad postings on that
    repo's own terms (its "type", "role_type", "track" or "status" column).
    Adding a tracker is then a table entry rather than a parser.
    """
    data = None
    for branch in branches:
        try:
            data = _json(url.format(branch=branch))
            break
        except Exception:
            continue
    if data is None:
        return []
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [])

    keep = spec.get("keep")
    out = []
    for row in data:
        if not isinstance(row, dict) or (keep and not keep(row)):
            continue
        link = (_pick(row, spec.get("url")) or "").strip()
        if not link:
            continue  # a posting with no link is not applyable
        locations = _pick(row, spec.get("locations"))
        if isinstance(locations, str):
            locations = [l for l in re.split(r"\s*[;|]\s*", locations) if l]
        out.append(record(
            _pick(row, spec.get("company")), _pick(row, spec.get("title")), link,
            locations or [], parse_date(_pick(row, spec.get("posted"))), source,
            category=_pick(row, spec.get("category")),
            salary=_pick(row, spec.get("salary")),
            description=_pick(row, spec.get("description")),
        ))
    return out


MD_LINK = re.compile(r"\((https?://[^)\s]+)\)")
MD_BOLD = re.compile(r"\*\*(.*?)\*\*")
MD_AGE = re.compile(r"^(\d+)([dhm])$")


def from_markdown_table(md_url, source, category=None):
    """Parse a `Company | Role | Location | Posted | Visa | Apply` table.

    The zapplyjobs lists refresh every few minutes and link straight to the
    employer's ATS rather than through a redirect, which makes them the
    freshest markdown source worth reading.
    """
    try:
        md = _text(md_url)
    except Exception:
        return []
    now = int(time.time())
    out = []
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6 or cells[0].startswith("---") or "Company" in cells[0]:
            continue
        company = MD_BOLD.search(cells[0])
        link = MD_LINK.search(cells[-1])
        if not company or not link:
            continue
        # "7m" is seven minutes here, not seven months: these tables measure
        # freshness in minutes and hours far more often than in days.
        age = MD_AGE.match(cells[3])
        unit = {"d": 86400, "h": 3600, "m": 60}
        posted = now - int(age.group(1)) * unit[age.group(2)] if age else None
        out.append(record(
            company.group(1), cells[1], link.group(1), [cells[2]],
            posted, source, category=category))
    return out


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


def from_speedyapply(md_url, source, category=None):
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
            # No per-role category: speedyapply labels a whole repo "AI", and
            # that label is loose enough to carry "Research Scientist - College
            # of Aviation". Treating it as evidence would promote every weak
            # title on the list.
            category=category,
            salary=salary,
        ))
    return out


RAW = "https://raw.githubusercontent.com/{repo}/{{branch}}/{path}"


def _gh(repo, path):
    return RAW.format(repo=repo, path=path)


# Every tracker we read. The first three are the originals; the rest were added
# to widen coverage beyond the AI-labelled lists, because a genuine ML role is
# often filed under "Software Engineering" on a general new-grad tracker and
# would never appear on an AI-only one.
#
# Deliberately not here:
#   coderQuad/New-Grad-Positions   byte-identical mirror of SimplifyJobs
#   SuryaHarikrishnan/2027-...     10 MB, 96% of it re-published from Simplify
#   jobright-ai/*                  links go through a redirect rather than to
#                                  the employer, and rows use a "continuation"
#                                  syntax that hides the company name
SOURCES = [
    ("simplify", lambda: from_listings_json(
        _gh("SimplifyJobs/New-Grad-Positions", ".github/scripts/listings.json"),
        "simplify")),
    ("vanshb03", lambda: from_listings_json(
        _gh("vanshb03/New-Grad-2027", ".github/scripts/listings.json"),
        "vanshb03")),
    ("speedyapply-ai-usa", lambda: from_speedyapply(
        _gh("speedyapply/2027-AI-College-Jobs", "NEW_GRAD_USA.md").format(branch="main"),
        "speedyapply")),
    ("speedyapply-ai-intl", lambda: from_speedyapply(
        _gh("speedyapply/2027-AI-College-Jobs", "NEW_GRAD_INTL.md").format(branch="main"),
        "speedyapply")),
    # The SWE list carries the ML roles whose titles read as software
    # engineering; the classifier decides which of those qualify.
    ("speedyapply-swe-usa", lambda: from_speedyapply(
        _gh("speedyapply/2027-SWE-College-Jobs", "NEW_GRAD_USA.md").format(branch="main"),
        "speedyapply")),

    ("aprameyak", lambda: from_json_repo(
        _gh("aprameyak/2027-tech-jobs", "listings.json"), "aprameyak", {
            "keep": lambda r: r.get("type") == "newgrad",
            "company": "company", "title": "role", "url": "url",
            "locations": "location", "posted": "date_added",
        })),
    ("wonofakind", lambda: from_json_repo(
        _gh("WonOfAKind/New-Grad-And-Internships-2027", "data/roles.json"),
        "wonofakind", {
            "keep": lambda r: r.get("role_type") == "New Grad",
            "company": "company", "title": "title", "url": "url",
            "locations": "location", "posted": "posted_at",
            "category": "discipline", "salary": "compensation",
            # Their qualification text is the requirements section, which is
            # exactly the part that says whether a role is really about ML.
            "description": "qualification_text",
        })),
    ("coconight", lambda: from_json_repo(
        _gh("coconight01/2027-North-America-New-Grad-Jobs", "data/jobs.json"),
        "coconight", {
            "keep": lambda r: r.get("status") == "Open",
            "company": "company", "title": "role", "url": "url",
            "locations": "location", "posted": "posted_date",
            "category": "category", "salary": "salary",
        })),
    ("harrycodingnow", lambda: from_json_repo(
        _gh("harrycodingnow/new-grad-2027-tracker", "data/active_jobs.json"),
        "harrycodingnow", {
            "keep": lambda r: not r.get("disqualified"),
            "company": "company", "title": "title",
            "url": lambda r: r.get("application_url") or r.get("source_url"),
            "locations": "location", "posted": "date_posted",
            # The only tracker that ships full job text.
            "description": lambda r: f"{r.get('description') or ''} {r.get('requirements') or ''}",
        })),
    ("ricsign", lambda: from_json_repo(
        _gh("ricsign/Ricsign-New-Grads-Jobs-2027", "data/v1/jobs.json"), "ricsign", {
            "keep": lambda r: r.get("active") and r.get("track") != "internship",
            "company": "company_name", "title": "title", "url": "apply_url",
            "locations": "locations", "posted": "posted_at",
            "category": "track", "salary": "compensation",
        })),
    ("applyguy", lambda: from_json_repo(
        _gh("ApplyGuy/2027-New-Grad-Jobs", "data/new-grad-jobs.json"), "applyguy", {
            # listingUrl is the employer's own board; url is a tracked redirect.
            "url": lambda r: r.get("listingUrl") or r.get("url"),
            "company": "company", "title": "title",
            "locations": "location", "posted": "posted",
        })),
    ("dreamworkhq", lambda: from_json_repo(
        _gh("dreamworkhq/New-Grad-Software-Engineer-Jobs", "data/listings.json"),
        "dreamworkhq", {
            "company": "company", "title": "title", "url": "url",
            "locations": "location", "posted": "postedAt",
            "category": "aiRoleKind",
        })),
    ("zapply-ds", lambda: from_markdown_table(
        _gh("zapplyjobs/New-Grad-Data-Science-Jobs-2027", "README.md").format(branch="main"),
        "zapply")),
    ("zapply-swe", lambda: from_markdown_table(
        _gh("zapplyjobs/New-Grad-Software-Engineering-Jobs-2027", "README.md").format(branch="main"),
        "zapply")),
]


def _fetch_one(entry):
    name, fn = entry
    try:
        return name, fn(), None
    except Exception as e:  # one dead tracker must not fail the run
        return name, [], str(e)


def fetch_all():
    """Fetch every source in parallel, tolerating individual failures.

    Sequentially this is about six seconds, which is cheap but not free when
    the hourly job runs it. In parallel it is under two, which is what makes
    reading the trackers hourly rather than daily worth doing: several of them
    now rebuild every few minutes.
    """
    records, report = [], []
    with futures.ThreadPoolExecutor(len(SOURCES)) as ex:
        for name, rows, err in ex.map(_fetch_one, SOURCES):
            records.extend(rows)
            report.append((name, len(rows), err))
    return records, report


if __name__ == "__main__":
    recs, rep = fetch_all()
    for name, n, err in rep:
        print(f"{name:20} {n:6}  {err or ''}")
    print(f"{'TOTAL':20} {len(recs):6}")

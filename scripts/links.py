"""Resolve posting links to the employer, and fetch them without raising.

Trackers link through redirectors (zapply.jobs), aggregator pages
(dreamworkhq, jobright.ai) and tracking parameters. Verification only means
something against the employer's own system, so every link is first turned
back into the employer's URL here. The HTTP helpers live here too because
resolution needs the network for the redirectors that cannot be decoded
offline.
"""
import datetime
import html as html_mod
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TIMEOUT = 15
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
API_HEADERS = {"User-Agent": "ML_Newgrad_2027/1.0 (+https://github.com/Tar-ive/ML_Newgrad_2027)",
               "Accept": "application/json"}
PAGE_HEADERS = {"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}


class HttpResult:
    def __init__(self, status, body=b"", final_url=None, error=None):
        self.status, self.body, self.final_url, self.error = status, body, final_url, error

    def json(self):
        try:
            return json.loads(self.body)
        except ValueError:
            return None

    def text(self, limit=400_000):
        return self.body[:limit].decode("utf-8", "replace")


def http(url, headers=API_HEADERS, data=None, limit=2_000_000):
    """GET (or POST JSON) without raising. Status is an int, or None on error."""
    body = json.dumps(data).encode() if data is not None else None
    h = dict(headers, **({"Content-Type": "application/json"} if body else {}))
    try:
        req = urllib.request.Request(url, headers=h, data=body)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return HttpResult(r.status, r.read(limit), r.geturl())
    except urllib.error.HTTPError as e:
        return HttpResult(e.code, b"", url)
    except Exception as e:  # timeouts, TLS, DNS: all "could not tell"
        return HttpResult(None, b"", url, error=type(e).__name__)


# Statuses that mean "you may not look", not "this is gone".
BLOCKED = {401, 403, 405, 407, 429, 451}


def epoch(value):
    """Epoch seconds from ISO strings, epoch millis, or Amazon's "September 5, 2026"."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 10**11 else int(value)
    text = str(value).strip()
    for shape in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return int(datetime.datetime.strptime(text, shape)
                       .replace(tzinfo=datetime.timezone.utc).timestamp())
        except ValueError:
            pass
    try:
        return int(datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Link resolution: turn redirectors and tracking URLs into employer URLs.
# ---------------------------------------------------------------------------

TRACKING_PARAMS = re.compile(r"^(utm_\w+|gh_src|lever-source.*|fbclid|gclid|mc_cid|mc_eid)$", re.I)

# Aggregators whose pages hide the employer link behind JavaScript. A posting
# known only through one of these cannot be verified or applied to directly.
OPAQUE_HOSTS = ("jobright.ai", "linkedin.com", "indeed.com", "glassdoor.com",
                "simplify.jobs", "joinhandshake.com", "ripplematch.com",
                "wayup.com", "bit.ly", "tinyurl.com")

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

# zapplyjobs links go through a redirector that, as of September 2026, sends
# every visitor to its generic job index -- including for jobs that are still
# open. Its slugs encode the real requisition, so they are decoded here instead
# of followed.
ZAPPLY_SLUGS = [
    (re.compile(rf"ashby-(.+)-({UUID})$"), "https://jobs.ashbyhq.com/{0}/{1}"),
    (re.compile(rf"lever-(.+)-({UUID})$"), "https://jobs.lever.co/{0}/{1}"),
    (re.compile(r"(?:greenhouse|gh)-(.+)-(\d+)$"), "https://job-boards.greenhouse.io/{0}/jobs/{1}"),
    (re.compile(r"sr-(.+)-(\d+)$"), "https://jobs.smartrecruiters.com/{0}/{1}"),
    (re.compile(r"google-(\d+)$"), "https://www.google.com/about/careers/applications/jobs/results/{0}"),
    (re.compile(r"apple-(\d+)$"), "https://jobs.apple.com/en-us/details/{0}"),
    (re.compile(r"bytedance-(\d+)$"), "https://joinbytedance.com/search/{0}"),
    (re.compile(r"tiktok-(\d+)$"), "https://lifeattiktok.com/search/{0}"),
    # Workday slugs lack the wdN shard and the job path; verify resolves them.
    (re.compile(r"(workday-.+)$"), "workday-slug:{0}"),
]


def strip_tracking(url):
    try:
        s = urlsplit(url)
    except ValueError:
        return url
    query = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True)
             if not TRACKING_PARAMS.match(k)]
    return urlunsplit((s.scheme, s.netloc, s.path, urlencode(query), ""))


def employer_url(url):
    """Rewrite a known redirector link to the employer URL, without network.

    Returns the URL unchanged when there is nothing to rewrite, and None when
    the link is a redirector whose target cannot be recovered offline.
    """
    if not url:
        return None
    host = urlsplit(url).netloc.lower()
    if host.endswith("zapply.jobs"):
        m = re.search(r"/l/d/([^/?#]+)", url)
        if not m:
            return None
        for pattern, template in ZAPPLY_SLUGS:
            hit = pattern.match(m.group(1))
            if hit:
                return template.format(*hit.groups())
        return None
    return strip_tracking(url)


def is_opaque(url):
    host = urlsplit(url or "").netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OPAQUE_HOSTS)


EMBEDDED_ATS = re.compile(
    r"https?://[^\s\"'<>\\]*(?:greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|"
    r"myworkdaysite\.com|smartrecruiters\.com|workable\.com|icims\.com|oraclecloud\.com|"
    r"amazon\.jobs|jobs\.apple\.com|google\.com/about/careers|lifeattiktok\.com|"
    r"joinbytedance\.com|eightfold\.ai)[^\s\"'<>\\]*", re.I)


NOT_EMPLOYER = re.compile(r"dreamworkhq|facebook|twitter|linkedin|instagram|youtube|tiktok\.com/@|x\.com/|"
                          r"safelinks|google\.com/(?!about/careers)|apple\.com/app|play\.google|"
                          r"\.(png|jpe?g|svg|css|js)(\?|$)", re.I)
JOB_LIKE = re.compile(r"job|career|opportunit|position|requisition|vacanc|apply|posting", re.I)


def resolve_dreamwork(url):
    """dreamworkhq pages embed the employer's link in their HTML.

    A known ATS link wins. Otherwise the first outbound link that looks like a
    specific posting -- a job-ish path carrying an id -- on the employer's own
    career site (jobs.dish.com, recruiting.ultipro.com, ...).
    """
    r = http(url, headers=PAGE_HEADERS, limit=600_000)
    if r.status != 200:
        return None
    page = r.text()
    for hit in EMBEDDED_ATS.findall(page):
        return html_mod.unescape(hit)
    for href in re.findall(r'href="(https?://[^"]+)"', page):
        href = html_mod.unescape(href)
        if not NOT_EMPLOYER.search(href) and JOB_LIKE.search(href) and JOB_ID.search(href):
            return href
    return None


JOB_ID = re.compile(rf"({UUID}|[A-Z]{{1,4}}[-_]?\d{{4,}}|\d{{5,}})", re.I)

def resolve_workday_slug(slug):
    """Find the job page for a zapply "workday-{tenant}-{site}-{req}" slug.

    The slug drops the wdN shard and the job path, hyphenates the site name,
    and joins it to a requisition id that often has hyphens of its own
    ("JR-0109848"). So every split of the tail into site and requisition is
    tried against the board's own search endpoint, across the common shards.
    """
    m = re.match(r"workday-([a-z0-9]+)-(.+)$", slug)
    if not m:
        return None
    tenant, tail = m.groups()
    pieces = tail.split("-")
    splits = [("-".join(pieces[:i]), "-".join(pieces[i:])) for i in range(1, len(pieces))]
    splits = [(site, req) for site, req in splits if re.search(r"\d", req)][-3:]
    for shard in ("wd1", "wd5", "wd3", "wd12", "wd2", "wd10"):
        answered = False
        for site, req in reversed(splits):
            for site_name in dict.fromkeys((site.replace("-", "_"), site)):
                r = http(f"https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site_name}/jobs",
                         data={"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": req})
                if r.status != 200 or not r.json():
                    continue
                answered = True
                for posting in r.json().get("jobPostings") or []:
                    path = posting.get("externalPath") or ""
                    if path.endswith(req):
                        return f"https://{tenant}.{shard}.myworkdayjobs.com/{site_name}{path}"
        if answered:
            return None  # the board answered on this shard; the requisition is not on it
    return None


# Career sites with no per-job signal. Their status comes from membership in the
# full board scrape that ats_live.py already performs, when that ran this cycle.
BOARD_ID = [
    ("tiktok", re.compile(r"lifeattiktok\.com.*?(\d{15,20})")),
    ("bytedance", re.compile(r"joinbytedance\.com.*?(\d{15,20})")),
    ("google", re.compile(r"google\.com/about/careers/.*?(\d{15,20})")),
    ("apple", re.compile(r"jobs\.apple\.com/.*?details/(\d{6,})")),
    ("tesla", re.compile(r"tesla\.com/careers/.*?(\d{5,})")),
    ("uber", re.compile(r"uber\.com/(?:.*?careers/list|[a-z-]*/?jobs)/(\d{5,})")),
]


def board_key(url):
    """(board, job id) for a career site verified by board membership."""
    for board, pattern in BOARD_ID:
        m = pattern.search(url or "")
        if m:
            return board, m.group(1)
    return None


def link_rank(url):
    """Lower is better: ATS APIs, then board sites, then pages, redirectors, opaque."""
    resolved = employer_url(url) or ""
    host = urlsplit(resolved).netloc
    if not resolved or is_opaque(resolved):
        return 5
    if resolved.startswith("workday-slug:") or "dreamworkhq.com" in host:
        return 4
    if re.search(r"greenhouse\.io|lever\.co|ashbyhq\.com|myworkday(jobs|site)\.com|smartrecruiters\.com|"
                 r"workable\.com|amazon\.jobs", host) or "gh_jid=" in resolved:
        return 0
    return 1 if board_key(resolved) else 2


WORKDAY_HOST = re.compile(r"^([\w-]+)\.(wd\d+)\.myworkdayjobs\.com$")
WORKDAY_SITE_HOST = re.compile(r"^(wd\d+)\.myworkdaysite\.com$")
LOCALE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def workday_cxs(url):
    """The CXS JSON URL behind a Workday job page, or None."""
    s = urlsplit(url)
    parts = [p for p in s.path.split("/") if p]
    if parts and LOCALE.match(parts[0]):
        parts = parts[1:]
    host = WORKDAY_HOST.match(s.netloc)
    if host and len(parts) >= 3 and parts[1] == "job":
        return f"https://{s.netloc}/wday/cxs/{host.group(1)}/{parts[0]}/{'/'.join(parts[1:])}"
    site_host = WORKDAY_SITE_HOST.match(s.netloc)
    if site_host and len(parts) >= 5 and parts[0] == "recruiting" and parts[3] == "job":
        return f"https://{s.netloc}/wday/cxs/{parts[1]}/{parts[2]}/{'/'.join(parts[3:])}"
    return None


def workday_posted(text, now=None):
    """Workday reports age as text: "Posted Today", "Posted 12 Days Ago", "30+ Days"."""
    now = now or time.time()
    t = (text or "").lower()
    if "today" in t:
        return int(now)
    if "yesterday" in t:
        return int(now - 86400)
    m = re.search(r"(\d+)\s*days", t)
    if m and "+" not in t:
        return int(now - int(m.group(1)) * 86400)
    return None  # "30+ Days Ago" is a lower bound, not a date

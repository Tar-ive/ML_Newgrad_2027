"""Ask the employer, not the tracker, whether a posting is still open.

A tracker's README is a snapshot of somebody else's scrape. Rows go stale,
links route through redirectors that break, and "new grad" is a label rather
than a fact. So every link is resolved to the employer's own applicant tracking
system and checked there, through the ATS's public API wherever one exists.

Each check returns one of three verdicts, and the difference between the last
two is the whole design:

  live     the employer's system lists the job right now.
  closed   the employer's system says it is gone.
  unknown  we could not tell: a bot wall, a timeout, a board slug we cannot
           read, a career site with no per-job signal.

"unknown" never closes a job. Every mature tracker studied while building this
converged on that rule, because the alternative -- treating a 403 or a timeout
as closure -- empties the list whenever an ATS has a bad hour.

A "closed" verdict is also marked authoritative or not. Greenhouse returning
404 for a job id is proof. Lever returning 404 is not: confidential postings
404 from its API while their page is live. A non-authoritative closure has to
be seen twice before verify.py acts on it.
"""
import html as html_mod
import json
import re
import threading
import time
from urllib.parse import parse_qsl, quote, urlsplit

from links import (  # noqa: F401  (link_rank and friends are re-exported for verify.py)
    BLOCKED, JOB_ID, PAGE_HEADERS, UUID, board_key, employer_url, epoch, http, is_opaque,
    link_rank, resolve_dreamwork, resolve_workday_slug, strip_tracking, workday_cxs,
    workday_posted,
)


def verdict(status, via, reason="", authoritative=True, description=None,
            posted=None, apply_url=None):
    return {"status": status, "via": via, "reason": reason,
            "authoritative": authoritative, "description": description,
            "posted": posted, "apply_url": apply_url}


def unknown(via, reason):
    return verdict("unknown", via, reason, authoritative=False)


def _inconclusive(r, via):
    if r.status is None:
        return unknown(via, f"network error: {r.error}")
    if r.status in BLOCKED:
        return unknown(via, f"blocked: HTTP {r.status}")
    return unknown(via, f"HTTP {r.status}")


# ---------------------------------------------------------------------------
# Per-ATS checks. Each takes a URL and returns a verdict, or None if the URL
# does not belong to that ATS.
# ---------------------------------------------------------------------------

def check_greenhouse(url):
    s = urlsplit(url)
    q = dict(parse_qsl(s.query))
    if not re.search(r"(?:^|\.)greenhouse\.io$", s.netloc):
        # Company career sites embed Greenhouse and expose only gh_jid. The
        # embed endpoint finds the board from the job id alone while the job
        # is open, and 404s once it is not.
        if not re.fullmatch(r"\d{5,}", q.get("gh_jid", "")):
            return None
        r = http(f"https://boards.greenhouse.io/embed/job_app?token={q['gh_jid']}", headers=PAGE_HEADERS,
                 limit=50_000)
        if r.status == 404:
            return verdict("closed", "greenhouse", "gh_jid unknown to Greenhouse", authoritative=False)
        board = dict(parse_qsl(urlsplit(r.final_url or "").query)).get("for")
        if r.status != 200 or not board:
            return _inconclusive(r, "greenhouse")
        q = {"for": board, "token": q["gh_jid"]}
    path = re.search(r"^/([^/]+)/jobs/(\d+)", s.path)
    if path:
        board, job = path.groups()
    elif q.get("for") and (q.get("token") or q.get("gh_jid")):
        board, job = q["for"], q.get("token") or q.get("gh_jid")
    else:
        return None
    # EU boards live at job-boards.eu.greenhouse.io but are served by the same
    # API host; boards-api.eu.greenhouse.io does not resolve.
    r = http(f"https://boards-api.greenhouse.io/v1/boards/{quote(board)}/jobs/{job}")
    if r.status == 404:
        return verdict("closed", "greenhouse", "job id not on board")
    if r.status != 200 or not r.json():
        return _inconclusive(r, "greenhouse")
    j = r.json()
    return verdict("live", "greenhouse", description=j.get("content"),
                   posted=epoch(j.get("first_published") or j.get("updated_at")))


def check_lever(url):
    s = urlsplit(url)
    m = re.match(rf"^/([^/]+)/({UUID})", s.path)
    if not s.netloc.endswith("lever.co") or not m:
        return None
    api = "api.eu.lever.co" if ".eu." in s.netloc else "api.lever.co"
    r = http(f"https://{api}/v0/postings/{m.group(1)}/{m.group(2)}")
    if r.status == 404:
        # Confidential postings 404 here while their page is live.
        return verdict("closed", "lever", "API 404", authoritative=False)
    if r.status != 200 or not r.json():
        return _inconclusive(r, "lever")
    j = r.json()
    parts = [j.get("descriptionPlain") or ""]
    for block in j.get("lists") or []:
        parts.append(f"{block.get('text', '')}:\n{block.get('content', '')}")
    parts.append(j.get("additionalPlain") or "")
    return verdict("live", "lever", description="\n".join(parts), posted=epoch(j.get("createdAt")))


_ashby_boards = {}
_ashby_locks = {}
_ashby_guard = threading.Lock()


def _ashby_board(org):
    """One board fetch per org per run, however many of its postings we hold."""
    with _ashby_guard:
        lock = _ashby_locks.setdefault(org, threading.Lock())
    with lock:
        if org not in _ashby_boards:
            _ashby_boards[org] = http(f"https://api.ashbyhq.com/posting-api/job-board/{quote(org)}",
                                      limit=30_000_000)
        return _ashby_boards[org]


def check_ashby(url):
    s = urlsplit(url)
    m = re.match(rf"^/([^/]+)/({UUID})", s.path)
    if not s.netloc.endswith("ashbyhq.com") or not m:
        return None
    r = _ashby_board(m.group(1))
    board = r.json() if r.status == 200 else None
    jobs = (board or {}).get("jobs")
    if not jobs:
        # A renamed slug 404s, and an empty board proves nothing either.
        return _inconclusive(r, "ashby") if r.status != 200 else unknown("ashby", "empty board")
    job = next((x for x in jobs if x.get("id") == m.group(2)), None)
    if job is None or job.get("isListed") is False:
        return verdict("closed", "ashby", "not listed on a board that loaded")
    return verdict("live", "ashby", description=job.get("descriptionHtml") or job.get("descriptionPlain"),
                   posted=epoch(job.get("publishedAt")))


def check_workday(url):
    cxs = workday_cxs(url)
    if not cxs:
        return None
    r = http(cxs)
    if r.status in (404, 410):
        return verdict("closed", "workday", f"HTTP {r.status}")
    if r.status in BLOCKED:
        # Some tenants refuse per-job reads from non-browsers but still answer
        # the board's own search, which is enough to tell open from gone.
        return _workday_search(cxs) or _inconclusive(r, "workday")
    if r.status != 200 or not r.json():
        return _inconclusive(r, "workday")
    info = r.json().get("jobPostingInfo") or {}
    if info.get("canApply") is False:
        return verdict("closed", "workday", "applications closed")
    end = epoch(info.get("endDate"))
    if end and end + 86400 < time.time():
        return verdict("closed", "workday", "posting end date has passed")
    return verdict("live", "workday", description=info.get("jobDescription"),
                   posted=epoch(info.get("startDate")) or workday_posted(info.get("postedOn")))


def _workday_search(cxs):
    m = re.match(r"^(https://[^/]+/wday/cxs/[^/]+/[^/]+)/job/.*_([A-Za-z]*[-_]?\d[\w-]*)$", cxs)
    if not m:
        return None
    base, req = m.groups()
    r = http(f"{base}/jobs", data={"appliedFacets": {}, "limit": 10, "offset": 0, "searchText": req})
    if r.status != 200 or r.json() is None:
        return None
    for posting in r.json().get("jobPostings") or []:
        if (posting.get("externalPath") or "").endswith(req):
            return verdict("live", "workday", "found by board search", posted=workday_posted(posting.get("postedOn")))
    return verdict("closed", "workday", "requisition not in board search", authoritative=False)


def check_smartrecruiters(url):
    s = urlsplit(url)
    m = re.match(r"^/([^/]+)/(\d+)", s.path)
    if s.netloc != "jobs.smartrecruiters.com" or not m:
        return None
    r = http(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
    if r.status == 404:
        return verdict("closed", "smartrecruiters", "HTTP 404")
    if r.status != 200 or not r.json():
        return _inconclusive(r, "smartrecruiters")
    j = r.json()
    if j.get("active") is False:
        return verdict("closed", "smartrecruiters", "inactive")
    sections = ((j.get("jobAd") or {}).get("sections") or {})
    text = "\n".join(f"{v.get('title', '')}:\n{v.get('text', '')}" for v in sections.values()
                     if isinstance(v, dict))
    return verdict("live", "smartrecruiters", description=text, posted=epoch(j.get("releasedDate")))


def check_workable(url):
    s = urlsplit(url)
    m = re.match(r"^/([^/]+)/j/([A-Z0-9]+)", s.path)
    if s.netloc != "apply.workable.com" or not m:
        return None
    r = http(f"https://apply.workable.com/api/v2/accounts/{m.group(1)}/jobs/{m.group(2)}")
    if r.status == 404:
        return verdict("closed", "workable", "HTTP 404")
    if r.status != 200 or not r.json():
        return _inconclusive(r, "workable")
    j = r.json()
    if (j.get("state") or "published") in ("closed", "archived"):
        return verdict("closed", "workable", j["state"])
    text = "\n".join(filter(None, [j.get("description"), "Requirements:", j.get("requirements")]))
    return verdict("live", "workable", description=text, posted=epoch(j.get("published")))


def check_amazon(url):
    s = urlsplit(url)
    m = re.search(r"/jobs/(\d+)", s.path)
    if not s.netloc.endswith("amazon.jobs") or not m:
        return None
    r = http(f"https://www.amazon.jobs/en/search.json?base_query={m.group(1)}&result_limit=10")
    if r.status != 200 or r.json() is None:
        return _inconclusive(r, "amazon")
    job = next((x for x in r.json().get("jobs") or [] if str(x.get("id_icims")) == m.group(1)), None)
    if job is None:
        # Search indexes lag, so absence needs a second sighting.
        return verdict("closed", "amazon", "not in search", authoritative=False)
    text = "\n".join([job.get("description") or "", "Basic Qualifications:",
                      job.get("basic_qualifications") or "", "Preferred Qualifications:",
                      job.get("preferred_qualifications") or ""])
    return verdict("live", "amazon", description=text, posted=epoch(job.get("posted_date")))


def check_board_member(url, boards):
    key = board_key(url)
    if not key:
        return None
    board, job = key
    ids = (boards or {}).get(board)
    if ids is None and board in TITLE_RENDERING_BOARDS:
        return check_rendered_title(url, board)
    if ids is None:
        return unknown(board, "board not scraped this run")
    if job in ids:
        return verdict("live", board, "on the employer's board")
    # Custom scrapers paginate and filter, and their job counts swing run to run
    # (Apple returned 6,090 jobs one run and 4,862 the next), so a miss needs
    # more sightings than other soft closures.
    result = verdict("closed", board, "absent from board scrape", authoritative=False)
    result["strikes_needed"] = BOARD_STRIKES
    return result


# Boards whose pages server-render the job title when the job exists and render
# no title at all for an id that does not, which is a usable per-job signal
# when the full board was not scraped this cycle.
TITLE_RENDERING_BOARDS = {"tiktok", "bytedance"}
BOARD_STRIKES = 3


def check_rendered_title(url, board):
    r = http(url, headers=PAGE_HEADERS, limit=600_000)
    if r.status != 200:
        return _inconclusive(r, board)
    page = r.text()
    if any(p.findall(page) for p in TITLE_CANDIDATES[:3]):
        return verdict("live", board, "posting page renders its title", authoritative=False)
    return verdict("closed", board, "posting page renders no job", authoritative=False)


# ---------------------------------------------------------------------------
# Generic page check, for everything else.
# ---------------------------------------------------------------------------

CLOSED_TEXT = re.compile(
    r"no longer accepting applications|we are no longer accepting|"
    r"this (?:job|position|role|posting|requisition|vacancy) (?:has been|is) (?:closed|filled|expired)|"
    r"this (?:job|position|role|posting) is no longer (?:available|open|active)|"
    r"(?:job|position|posting) (?:you(?:'| a)re looking for )?(?:has expired|is unavailable|was removed|no longer exists)|"
    r"this posting has expired|job posting not found|sorry, this job has expired|"
    r"applications? (?:are |is )?(?:now )?closed", re.I)
SOFT_404_URL = re.compile(r"/(?:404|not[-_]?found|error)(?:[./?#]|$)|[?&](?:error=(?:true|404)|rr_message=job_not_found)", re.I)
LANDING_PATH = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:careers?|jobs?|jobs/search|search|opportunities|openings)?/?$", re.I)
TITLE_CANDIDATES = [
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S),
    re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S),
    re.compile(r'"title"\s*:\s*"([^"]{4,160})"'),
]
JSON_LD = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.I | re.S)


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower())) - {
        "the", "and", "of", "a", "an", "to", "in", "for", "at", "job", "jobs", "careers", "-"}


def titles_match(expected, page_html):
    want = _tokens(expected)
    if not want:
        return False
    for pattern in TITLE_CANDIDATES:
        for hit in pattern.findall(page_html)[:3]:
            got = _tokens(html_mod.unescape(re.sub(r"<[^>]+>", " ", hit)))
            if got and len(want & got) / len(want) >= 0.65:
                return True
    return False


def _json_ld_posting(page_html):
    for block in JSON_LD.findall(page_html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def check_page(url, title):
    r = http(url, headers=PAGE_HEADERS, limit=600_000)
    if r.status in (404, 410):
        return verdict("closed", "page", f"HTTP {r.status}", authoritative=False)
    if r.status != 200:
        return _inconclusive(r, "page")
    final = urlsplit(r.final_url or url)
    page = r.text()
    if SOFT_404_URL.search(r.final_url or ""):
        return verdict("closed", "page", "redirected to an error page", authoritative=False)
    posting = _json_ld_posting(page)
    if posting and epoch(posting.get("validThrough")) and epoch(posting["validThrough"]) < time.time():
        return verdict("closed", "page", "validThrough has passed", authoritative=False)
    if CLOSED_TEXT.search(re.sub(r"<script.*?</script>", " ", page, flags=re.S | re.I)):
        return verdict("closed", "page", "closed-posting text", authoritative=False)
    original_ids = set(JOB_ID.findall(urlsplit(url).path + "?" + urlsplit(url).query))
    lost_id = original_ids and not any(i in (r.final_url or "") for i in original_ids)
    matched = titles_match(title, page) or bool(posting and titles_match(title, posting.get("title", "")))
    if (lost_id or LANDING_PATH.match(final.path)) and not matched:
        return verdict("closed", "page", "redirected off the posting", authoritative=False)
    if matched:
        return verdict("live", "page", "posting page renders", authoritative=False,
                       description=(posting or {}).get("description"),
                       posted=epoch((posting or {}).get("datePosted")))
    return unknown("page", "page gives no signal")


API_CHECKS = [check_greenhouse, check_lever, check_ashby, check_workday,
              check_smartrecruiters, check_workable, check_amazon]


def check(url, title="", boards=None):
    """Verify one posting. Returns a verdict dict; apply_url is the resolved link."""
    resolved = employer_url(url)
    if resolved and resolved.startswith("workday-slug:"):
        resolved = resolve_workday_slug(resolved.split(":", 1)[1])
        if resolved is None:
            return verdict("unresolvable", "zapply", "workday requisition not found", authoritative=False)
    if resolved is None:
        return verdict("unresolvable", "redirector", "target cannot be recovered", authoritative=False)
    if "dreamworkhq.com" in urlsplit(resolved).netloc:
        target = resolve_dreamwork(resolved)
        if not target:
            return verdict("unresolvable", "dreamworkhq", "no employer link on page", authoritative=False)
        resolved = strip_tracking(target)
    if is_opaque(resolved):
        return verdict("unresolvable", urlsplit(resolved).netloc, "aggregator link", authoritative=False)

    result = check_board_member(resolved, boards)
    if result is None:
        for fn in API_CHECKS:
            result = fn(resolved)
            if result is not None:
                break
    if result is None:
        result = check_page(resolved, title)
    result["apply_url"] = resolved
    return result

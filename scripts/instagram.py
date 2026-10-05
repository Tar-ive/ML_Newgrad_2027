"""Fold job links shared in Instagram stories into data/instagram.json.

Some creators post new roles as story link stickers before any tracker picks
them up, and a story is gone after 24 hours. The instagram workflow polls those
accounts with instastoryhook and pipes its JSONL events here. This script keeps
only the link stickers, resolves each link to the employer's company and job
title, and merges it into a small committed store that sources.py reads like
any other tracker. Whether a link belongs on the list is not decided here: the
classifier and the verifier treat it exactly as they treat a tracker row.

Image-only stories carry no link and are skipped. A link whose title cannot be
resolved is still stored, and resolution is retried on later runs.

Run with: instastoryhook run zero2sudo --once | python3 scripts/instagram.py
"""
import html as html_mod
import json
import os
import re
import sys
import time
from urllib.parse import parse_qsl, quote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from links import PAGE_HEADERS, UUID, epoch, http, strip_tracking, workday_cxs  # noqa: E402
from verify_ats import TITLE_CANDIDATES, _json_ld_posting  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "instagram.json")

# A shared link older than this is dropped from the store. By then it has either
# reached data/listings.json, where verification owns it, or it never qualified.
KEEP_DAYS = 30
DAY = 86400


ASHBY_FORM = re.compile(r"(?<=ashbyhq\.com/)([^?#]+?)/application/?(\?embed=true)?$")


def unwrap(url):
    """The destination behind Instagram's l.instagram.com click-through link."""
    s = urlsplit(url or "")
    if s.netloc.endswith("l.instagram.com"):
        return dict(parse_qsl(s.query)).get("u") or url
    return url


def sticker_links(event):
    """Employer URLs from one instagram.story.discovered event."""
    if event.get("type") != "instagram.story.discovered":
        return []
    out = []
    for link in (event.get("story") or {}).get("links") or []:
        url = link.get("resolved_url") or unwrap(link.get("url"))
        if url and url.startswith("http"):
            # Ashby stickers often open the embedded application form; the
            # posting itself is the same path without it.
            url = ASHBY_FORM.sub(r"\1", strip_tracking(url))
            out.append(url)
    return out


def _clean(text):
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _slug_name(slug):
    return re.sub(r"[-_]+", " ", slug).strip().title()


def _workday(url):
    cxs = workday_cxs(url)
    if not cxs:
        return None
    r = http(cxs)
    if r.status != 200 or not r.json():
        return None
    j = r.json()
    info = j.get("jobPostingInfo") or {}
    # Workday prefixes the legal entity with its company code: "1000 Micron Technology, Inc."
    company = re.sub(r"^\d+\s+", "", (j.get("hiringOrganization") or {}).get("name") or "")
    return {"company": company or None,
            "title": info.get("title"),
            "locations": [info["location"]] if info.get("location") else []}


def _greenhouse(url):
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not m:
        return None
    r = http(f"https://boards-api.greenhouse.io/v1/boards/{quote(m.group(1))}/jobs/{m.group(2)}")
    if r.status != 200 or not r.json():
        return None
    j = r.json()
    location = (j.get("location") or {}).get("name")
    return {"company": j.get("company_name") or _slug_name(m.group(1)),
            "title": j.get("title"), "locations": [location] if location else []}


def _lever(url):
    s = urlsplit(url)
    m = re.match(rf"^/([^/]+)/({UUID})", s.path)
    if not s.netloc.endswith("lever.co") or not m:
        return None
    api = "api.eu.lever.co" if ".eu." in s.netloc else "api.lever.co"
    r = http(f"https://{api}/v0/postings/{m.group(1)}/{m.group(2)}")
    if r.status != 200 or not r.json():
        return None
    j = r.json()
    location = (j.get("categories") or {}).get("location")
    return {"company": _slug_name(m.group(1)), "title": j.get("text"),
            "locations": [location] if location else []}


def _ashby(url):
    s = urlsplit(url)
    m = re.match(rf"^/([^/]+)/({UUID})", s.path)
    if not s.netloc.endswith("ashbyhq.com") or not m:
        return None
    r = http(f"https://api.ashbyhq.com/posting-api/job-board/{quote(m.group(1))}",
             limit=30_000_000)
    jobs = (r.json() or {}).get("jobs") if r.status == 200 else None
    job = next((x for x in jobs or [] if x.get("id") == m.group(2)), None)
    if not job:
        return None
    return {"company": _slug_name(m.group(1)), "title": job.get("title"),
            "locations": [job["location"]] if job.get("location") else []}


def _page(url):
    """Any other career site: JSON-LD JobPosting first, then the page title."""
    r = http(url, headers=PAGE_HEADERS, limit=600_000)
    if r.status != 200:
        return None
    page = r.text()
    posting = _json_ld_posting(page)
    if posting and posting.get("title"):
        org = posting.get("hiringOrganization")
        places = posting.get("jobLocation") or []
        places = places if isinstance(places, list) else [places]
        locations = []
        for place in places:
            address = (place or {}).get("address") if isinstance(place, dict) else None
            if isinstance(address, dict):
                parts = [address.get("addressLocality"), address.get("addressRegion")]
                locations.append(", ".join(p for p in parts if p))
        return {"company": org.get("name") if isinstance(org, dict) else org,
                "title": posting["title"], "locations": [l for l in locations if l]}
    for pattern in TITLE_CANDIDATES[:3]:  # the last candidate matches any JSON "title"
        hit = pattern.search(page)
        if hit and _clean(hit.group(1)):
            return {"company": None, "title": _clean(hit.group(1)), "locations": []}
    return None


RESOLVERS = [_workday, _greenhouse, _lever, _ashby, _page]


def describe(url):
    """Company, title and locations for a posting URL, or None when unreadable."""
    for resolver in RESOLVERS:
        found = resolver(url)
        if found and found.get("title"):
            if not found.get("company"):
                host = urlsplit(url).netloc.lower().removeprefix("www.")
                found["company"] = _slug_name(host.split(".")[-2] if "." in host else host)
            found["title"] = _clean(found["title"])
            return found
    return None


def load():
    try:
        with open(STORE) as f:
            return {row["url"]: row for row in json.load(f)}
    except FileNotFoundError:
        return {}


def merge(store, events, now, resolve=describe):
    """Add every new sticker link to `store` and retry unresolved ones.

    Returns how many links were new. `resolve` is injectable so the tests can
    run without the network.
    """
    added = 0
    for event in events:
        story = event.get("story") or {}
        account = (event.get("account") or {}).get("username")
        for url in sticker_links(event):
            if url in store:
                continue
            store[url] = {"url": url, "account": account, "story_id": story.get("id"),
                          "posted": epoch(story.get("posted_at")) or now, "first_seen": now,
                          "company": None, "title": None, "locations": []}
            added += 1
    for row in store.values():
        if not row.get("title"):
            found = resolve(row["url"])
            if found:
                row.update(company=found["company"], title=found["title"],
                           locations=found.get("locations") or [])
    for url in [u for u, row in store.items() if now - row["first_seen"] > KEEP_DAYS * DAY]:
        del store[url]
    return added


def read_events(stream):
    """instastoryhook's stdout mixes story events with status lines; keep the stories."""
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "instagram.story.discovered":
            yield event


def main():
    now = int(time.time())
    store = load()
    added = merge(store, read_events(sys.stdin), now)
    rows = sorted(store.values(), key=lambda r: (-r["posted"], r["url"]))
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w") as f:
        json.dump(rows, f, indent=1, sort_keys=True)
        f.write("\n")
    for row in rows:
        print(f"  {row['company'] or '?':24.24} {row['title'] or '(unresolved)':60.60} {row['url']}")
    unresolved = sum(1 for r in rows if not r["title"])
    print(f"{added} new links, {len(rows)} stored, {unresolved} unresolved")


if __name__ == "__main__":
    main()

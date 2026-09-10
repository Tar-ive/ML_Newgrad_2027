"""Scrape company ATS boards directly, via the ats-scrapers adapters.

This is what makes the list fast. The community trackers refresh roughly once
a day; hitting the boards ourselves surfaces a role within the hour it goes up.

Companies are split into two tiers because their boards cost wildly different
amounts to read:

  fast   Greenhouse / Ashby / Lever / Workable JSON APIs, ~0.5s each. Safe to
         run every hour. This tier holds the AI labs and startups, where roles
         open and close fastest.
  heavy  Custom career sites (Apple, Amazon, Google, Tesla, TikTok, Uber) that
         need HTML pagination and take 30-65s each. Run on a slower cadence.
"""
import concurrent.futures as futures
import html as html_mod
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANIES = os.path.join(ROOT, "data", "companies.json")

SCRAPER_BY_ATS = {
    "greenhouse": "GreenhouseScraper",
    "ashby": "AshbyScraper",
    "lever": "LeverScraper",
    "workable": "WorkableScraper",
    "smartrecruiters": "SmartRecruitersScraper",
    "rippling": "RipplingScraper",
    "apple": "AppleScraper",
    "tesla": "TeslaScraper",
    "tiktok": "TikTokScraper",
    "uber": "UberScraper",
    "amazon": "AmazonScraper",
    "google": "GoogleScraper",
}

FAST_WORKERS = 12

# Boards whose listing payload already embeds the description. Reading it costs
# nothing extra here. On the custom career sites a description means one extra
# HTTP request *per job*, which for a 34,000-job board like Amazon is hours of
# work, so those are fetched listing-only and gated on their title instead.
DESCRIPTIONS_FREE = {"greenhouse", "ashby", "lever", "workable",
                     "smartrecruiters", "rippling"}

# Greenhouse and Ashby return descriptions inside the same payload as the
# listing, so reading them costs nothing extra and is the only place a raw ATS
# feed states how much experience a role wants.
YEARS = re.compile(
    r"(\d+)\s*(?:\+|-\s*\d+)?\s*(?:or more\s*)?years?(?:\s+of)?"
    r"(?:\s+[\w-]+){0,3}\s+experience", re.I)
NEW_GRAD_TEXT = re.compile(
    r"new grad|recent(ly)? graduat|entry[- ]level|early career|final year|"
    r"graduating (in|by)|0-2 years|no prior experience|university grad|"
    r"currently (enrolled|pursuing).{0,40}(bachelor|master|phd)", re.I)
TAGS = re.compile(r"<[^>]+>")


# Enough text for the classifier to judge a role by, without holding a whole
# board's prose in memory. Requirements sections sit well inside this.
DESCRIPTION_CHARS = 4000


def clean_description(description):
    """Strip markup from a job description and cap its length."""
    if not description:
        return None
    return html_mod.unescape(TAGS.sub(" ", str(description)))[:DESCRIPTION_CHARS]


def read_experience(text):
    """Return (min_years or None, has_new_grad_language) from a job description."""
    if not text:
        return None, False
    years = [int(y) for y in YEARS.findall(text) if int(y) <= 30]
    return (min(years) if years else None), bool(NEW_GRAD_TEXT.search(text))


def load_companies(tier=None):
    with open(COMPANIES) as f:
        companies = json.load(f)
    if tier in (None, "all"):
        return companies
    return [c for c in companies if c["tier"] == tier]


def _to_record(job, company):
    """Map an ats_scrapers Job onto our common record shape."""
    posted = getattr(job, "posted_at", None)
    locations = []
    loc = getattr(job, "location", None)
    if loc:
        locations = [str(loc)]
    description = clean_description(getattr(job, "description", None))
    years, new_grad_text = read_experience(description)
    # New-grad language in the body is worth more than a silent description, so
    # let it stand in for an explicit "0 years" figure.
    if years is None and new_grad_text:
        years = 0

    # ats_scrapers returns pydantic models, so URLs arrive as HttpUrl objects.
    url = getattr(job, "apply_url", None) or getattr(job, "url", None) or ""
    return sources.record(
        company=company,
        title=str(getattr(job, "title", "") or ""),
        url=str(url),
        locations=locations,
        posted=posted.timestamp() if posted else None,
        source="ats",
        salary=str(getattr(job, "salary_summary", None) or "") or None,
        experience=years,
        # Greenhouse and Ashby ship the description with the listing, and this
        # is where it earns its keep: an AI lab posts "Software Engineer, New
        # Grad" with a description that is entirely about training models.
        description=description,
    )


def scrape_company(entry):
    """Fetch one company's board. Returns (records, error)."""
    from ats_scrapers import scrapers as S

    cls_name = SCRAPER_BY_ATS.get(entry["ats"])
    if not cls_name or not hasattr(S, cls_name):
        return [], f"no adapter for {entry['ats']}"
    try:
        want_descriptions = entry["ats"] in DESCRIPTIONS_FREE
        scraper = getattr(S, cls_name)(
            entry["slug"], include_descriptions=want_descriptions, timeout=25)
        jobs = list(scraper.fetch())
    except Exception as e:  # one dead board must not fail the run
        return [], f"{type(e).__name__}: {str(e)[:80]}"
    return [_to_record(j, entry["company"]) for j in jobs], None


def fetch(tier="fast", verbose=True):
    companies = load_companies(tier)
    records, errors = [], []
    workers = FAST_WORKERS if tier == "fast" else 4
    with futures.ThreadPoolExecutor(workers) as ex:
        for entry, (recs, err) in zip(companies, ex.map(scrape_company, companies)):
            if err:
                errors.append((entry["company"], err))
            records.extend(recs)
    if verbose:
        print(f"  ats[{tier}]: {len(companies)} boards, {len(records)} raw postings, "
              f"{len(errors)} failed")
        for co, err in errors[:10]:
            print(f"    ! {co}: {err}")
    return records


if __name__ == "__main__":
    tier = sys.argv[1] if len(sys.argv) > 1 else "fast"
    recs = fetch(tier)
    print(f"{len(recs)} postings from tier={tier}")

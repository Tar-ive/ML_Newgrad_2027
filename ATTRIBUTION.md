# Attribution

Phase 1 of this repo does not scrape job boards directly. It aggregates,
deduplicates, and re-filters public listings from the community-maintained
trackers below, which do the upstream collection work.

| Source | License | Link |
|---|---|---|
| SimplifyJobs/New-Grad-Positions | No license file — used in good faith as factual job metadata (company, title, location, link) | https://github.com/SimplifyJobs/New-Grad-Positions |
| vanshb03/New-Grad-2027 | MIT | https://github.com/vanshb03/New-Grad-2027 |
| speedyapply/2027-AI-College-Jobs | No license file — same good-faith basis as above | https://github.com/speedyapply/2027-AI-College-Jobs |

All credit for collecting and verifying those listings goes to their
maintainers and contributors. What this repo adds is ML-specific
classification, cross-source deduplication, and `first_seen` tracking.

Only factual metadata is copied: company name, job title, location, posting
URL, and posting date. No descriptions or other prose are reproduced.

If you maintain one of these repos and have concerns about how the data is
used here, please open an issue and it will be addressed promptly.

## Live scraping

| Project | License | Use |
|---|---|---|
| [kalil0321/ats-scrapers](https://github.com/kalil0321/ats-scrapers) | MIT | ATS adapters for every board scraped in `scripts/ats_live.py` |

The company list in `data/companies.json` was seeded from a public ATS export of
AI-company job postings, then verified against the live boards — each entry's
token was confirmed to resolve before being included.

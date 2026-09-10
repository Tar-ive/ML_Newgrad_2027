# Attribution

This repo does not scrape the community lists' own upstreams. It aggregates,
deduplicates, and re-filters public listings from the trackers below, which do
that collection work.

| Source | License | Link |
|---|---|---|
| SimplifyJobs/New-Grad-Positions | No license file — used in good faith as factual job metadata (company, title, location, link) | https://github.com/SimplifyJobs/New-Grad-Positions |
| vanshb03/New-Grad-2027 | MIT | https://github.com/vanshb03/New-Grad-2027 |
| speedyapply/2027-AI-College-Jobs | No license file — same good-faith basis as above | https://github.com/speedyapply/2027-AI-College-Jobs |
| speedyapply/2027-SWE-College-Jobs | No license file — same good-faith basis as above | https://github.com/speedyapply/2027-SWE-College-Jobs |
| aprameyak/2027-tech-jobs | No license file — same good-faith basis as above | https://github.com/aprameyak/2027-tech-jobs |
| WonOfAKind/New-Grad-And-Internships-2027 | No license file — same good-faith basis as above | https://github.com/WonOfAKind/New-Grad-And-Internships-2027 |
| coconight01/2027-North-America-New-Grad-Jobs | No license file — same good-faith basis as above | https://github.com/coconight01/2027-North-America-New-Grad-Jobs |
| harrycodingnow/new-grad-2027-tracker | No license file — same good-faith basis as above | https://github.com/harrycodingnow/new-grad-2027-tracker |
| ricsign/Ricsign-New-Grads-Jobs-2027 | Declared in the feed payload | https://github.com/ricsign/Ricsign-New-Grads-Jobs-2027 |
| ApplyGuy/2027-New-Grad-Jobs | No license file — same good-faith basis as above | https://github.com/ApplyGuy/2027-New-Grad-Jobs |
| dreamworkhq/New-Grad-Software-Engineer-Jobs | No license file — same good-faith basis as above | https://github.com/dreamworkhq/New-Grad-Software-Engineer-Jobs |
| zapplyjobs/New-Grad-Data-Science-Jobs-2027 | No license file — same good-faith basis as above | https://github.com/zapplyjobs/New-Grad-Data-Science-Jobs-2027 |
| zapplyjobs/New-Grad-Software-Engineering-Jobs-2027 | No license file — same good-faith basis as above | https://github.com/zapplyjobs/New-Grad-Software-Engineering-Jobs-2027 |

Several of the newer sources are general new-grad or software-engineering
lists rather than AI ones. They are read because a genuine ML role is often
filed under "Software Engineering" upstream, and an AI-only list never
surfaces it.

All credit for collecting and verifying those listings goes to their
maintainers and contributors. What this repo adds is ML-specific
classification, cross-source deduplication, and `first_seen` tracking.

Only factual metadata is copied: company name, job title, location, posting
URL, and posting date. No descriptions or other prose are reproduced. Two
sources publish job text; it is read in memory by the classifier to decide
whether a software engineering role is really an ML role, then discarded
before anything is written to disk.

If you maintain one of these repos and have concerns about how the data is
used here, please open an issue and it will be addressed promptly.

## Live scraping

| Project | License | Use |
|---|---|---|
| [kalil0321/ats-scrapers](https://github.com/kalil0321/ats-scrapers) | MIT | ATS adapters for every board scraped in `scripts/ats_live.py` |

The company list in `data/companies.json` was seeded from a public ATS export of
AI-company job postings, then verified against the live boards — each entry's
token was confirmed to resolve before being included.

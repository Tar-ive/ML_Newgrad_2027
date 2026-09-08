# Contributing

## Report a missing or wrong role

Open an issue with the company, title, location, and application link. Roles
are re-rendered automatically on the next refresh.

## Fix the classifier

Most quality problems are classifier problems, and those are the most valuable
contributions. Everything lives in [`scripts/classify.py`](/scripts/classify.py):

- **A real ML role is missing** → its title probably failed `CORE` / `SUPPORTING`,
  or tripped `NEGATIVE` / `SENIOR` / `DOMAIN_NOISE`.
- **A non-ML role is listed** → add the giveaway phrase to `NEGATIVE`.
- **A senior role is listed** → add the signal to `SENIOR`.
- **A company is in the wrong bucket** → add it to `AI_LAB`, `BIGTECH`, or `QUANT`.

Check your change before opening a PR:

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from classify import classify
print(classify('Your Job Title Here', 'AI/ML/Data', 'Company Name'))
"
```

Then regenerate and confirm the diff looks right:

```bash
python3 scripts/aggregate.py && python3 scripts/render.py
```

## Add a source

Add a fetcher to [`scripts/sources.py`](/scripts/sources.py) returning records
via `record(...)`, register it in `SOURCES`, and add the source to
[ATTRIBUTION.md](/ATTRIBUTION.md). Deduplication against existing sources is
automatic.

## Do not edit the tables by hand

Everything between the `<!-- TABLE_*_START -->` markers is generated and will be
overwritten on the next refresh. Edit the prose around them freely.

## Add a company to the hourly scrape

`data/companies.json` drives live scraping. Each entry needs the ATS platform and
the board token from the company's careers URL:

```json
{"company": "Anthropic", "ats": "greenhouse", "slug": "anthropic", "tier": "fast"}
```

Use `tier: "fast"` for Greenhouse / Ashby / Lever / Workable boards (JSON APIs,
scraped hourly) and `tier: "heavy"` for custom career sites (scraped 4× daily).
Verify the token resolves before opening a PR:

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from ats_live import scrape_company
recs, err = scrape_company({'company':'Anthropic','ats':'greenhouse','slug':'anthropic'})
print(err or f'{len(recs)} postings')
"
```

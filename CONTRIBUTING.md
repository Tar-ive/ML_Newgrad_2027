# Contributing

## Report a missing or wrong role

Open an issue with the company, title, location, and application link. Roles
are re-rendered automatically on the next refresh.

## Fix the classifier

Most quality problems are classifier problems, and those are the most valuable
contributions. Everything lives in [`scripts/classify.py`](/scripts/classify.py):

The gate is a whitelist of four role families (`ml`, `ds`, `de_ml`, `swe_ml`)
decided by `role_family()`, with three exclusion sets running ahead of it.

- **A real ML role is missing** → its title failed `ML_STRONG` / `ML_WEAK` /
  `DS_TITLE`, or tripped `EXCLUDE_HARDWARE` / `EXCLUDE_DOMAIN` /
  `EXCLUDE_FUNCTION` / `SENIOR` / `NOT_NEW_GRAD_ROLE`. Check which:
  `role_family(title)` returning `None` means no family claimed it;
  `is_excluded(title)` returning `True` means an exclusion set did.
- **A non-ML role is listed** → add the giveaway phrase to the exclusion set that
  fits its reason for being wrong, not whichever one is nearest.
- **A software engineering role is listed with no ML in it** → the specialization
  it matched is too loose; tighten `ML_SPECIALIZATION`.
- **A senior role is listed** → add the signal to `SENIOR`, or lower `MAX_YEARS`.
- **A company is in the wrong bucket** → add it to `AI_LAB`, `BIGTECH`, or `QUANT`.

Add a case to [`tests/test_classify.py`](/tests/test_classify.py) with every
classifier change — `KEEP`/`DROP` for a title, `FAMILIES` when the family itself
is the point, `DESCRIPTIONS` for the software-engineering promotion rule, and
`EXPERIENCE` for the level gate. CI runs the suite before each refresh.

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

Most trackers publish a JSON array of postings, so no parser is needed: add a
`from_json_repo` entry to `SOURCES` in [`scripts/sources.py`](/scripts/sources.py)
mapping our field names onto theirs, with a `keep` filter written in that repo's
own vocabulary (its `type`, `role_type`, `track` or `status` column). A spec
value is either a key name or a function of the row. For a markdown table, use
`from_markdown_table`; for anything stranger, write a fetcher that returns
records via `record(...)`.

Then add the source to [ATTRIBUTION.md](/ATTRIBUTION.md). Deduplication against
existing sources is automatic. Prefer sources that link to the employer's own
board — a redirect URL cannot be deduplicated against anything.

## Fix a verification call

Every posting in `data/listings.json` carries a `verification` block saying
why it is shown or hidden — `status`, `via`, `reason`, and for experience
calls the `evidence` sentence. Start there.

- **A dead link is still listed** → find its `via`. If it is `page`, the site
  needs a proper check in [`scripts/verify_ats.py`](/scripts/verify_ats.py):
  add a `check_<ats>` function returning `verdict(...)` and register it in
  `API_CHECKS`. Only mark a closure authoritative when the API's "gone" signal
  cannot also mean "blocked" or "renamed".
- **A live role is hidden as closed** → check `reason`. A soft signal that
  closed it too eagerly wants more strikes, not a deleted check.
- **A role is hidden as `too_senior` wrongly** → the evidence sentence shows
  what [`scripts/experience.py`](/scripts/experience.py) misread. Add the
  description to [`tests/test_experience.py`](/tests/test_experience.py) first.
- **A redirector's links do not resolve** → teach `employer_url` in
  [`scripts/links.py`](/scripts/links.py) (offline decoding), or add a
  `resolve_*` there and call it from `check` (network resolution).

When a rule changes, bump `VERSION` in [`scripts/verify.py`](/scripts/verify.py)
so the next run re-verifies every posting instead of waiting for each to come
due. Policy tests live in [`tests/test_verify.py`](/tests/test_verify.py) and
run offline.

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

## Run the classifier tests

```bash
python3 tests/test_classify.py
```

Any change to `scripts/classify.py` must keep these passing — CI runs them
before every refresh. If you are fixing a misfiled role, add it to `KEEP` or
`DROP` in that file as part of the fix, so it cannot regress later.

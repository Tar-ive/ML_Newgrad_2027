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

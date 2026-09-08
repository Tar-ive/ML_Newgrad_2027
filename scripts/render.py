"""Render data/listings.json into the markdown tables people actually read.

Only the regions between the HTML markers are rewritten, so any prose you add
to README.md survives the next refresh.
"""
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "listings.json")

NEW_WINDOW_DAYS = 7
HEADERS = ["Company", "Role", "Location", "Posted", "Apply"]

PAGES = [
    {
        "path": "README.md",
        "filter": lambda r: r["is_usa"],
        "sections": [("NEW", None), ("AI_LAB", "ai_lab"), ("BIGTECH", "bigtech"),
                     ("QUANT", "quant"), ("OTHER", "other")],
    },
    {
        "path": "INTERNATIONAL.md",
        "filter": lambda r: not r["is_usa"],
        "sections": [("NEW", None), ("AI_LAB", "ai_lab"), ("BIGTECH", "bigtech"),
                     ("QUANT", "quant"), ("OTHER", "other")],
    },
]


def age_cell(rec, now):
    ts = rec.get("date_posted") or rec.get("first_seen")
    if not ts:
        return "—"
    days = max(0, int((now - ts) // 86400))
    if days == 0:
        return "**today**"
    if days <= NEW_WINDOW_DAYS:
        return f"**{days}d**"
    return f"{days}d"


def locations_cell(rec):
    locs = rec.get("locations") or []
    if not locs:
        return "—"
    if len(locs) > 2:
        return f"{locs[0]} +{len(locs) - 1}"
    return " / ".join(locs)


def esc(text):
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def row(rec, now):
    company = esc(rec["company"])
    if rec.get("company_url"):
        company = f'[{company}]({rec["company_url"]})'
    cells = [
        f"**{company}**",
        esc(rec["title"]),
        esc(locations_cell(rec)),
        age_cell(rec, now),
        f'[Apply]({rec["url"]})' if rec.get("url") else "—",
    ]
    return "| " + " | ".join(cells) + " |"


def table(records, now):
    if not records:
        return "_No open roles in this bucket right now._"
    out = ["| " + " | ".join(HEADERS) + " |",
           "|" + "|".join("---" for _ in HEADERS) + "|"]
    out += [row(r, now) for r in records]
    return "\n".join(out)


def replace_marker(text, name, body):
    start, end = f"<!-- {name}_START -->", f"<!-- {name}_END -->"
    if start not in text or end not in text:
        return text
    before = text.split(start)[0]
    after = text.split(end, 1)[1]
    return f"{before}{start}\n{body}\n{end}{after}"


def sort_key(rec):
    return -(rec.get("date_posted") or rec.get("first_seen") or 0)


def main():
    now = int(time.time())
    with open(STORE) as f:
        all_recs = [r for r in json.load(f) if r.get("active")]

    for page in PAGES:
        path = os.path.join(ROOT, page["path"])
        if not os.path.exists(path):
            continue
        recs = sorted([r for r in all_recs if page["filter"](r)], key=sort_key)
        text = open(path).read()

        for name, tier in page["sections"]:
            if name == "NEW":
                cutoff = now - NEW_WINDOW_DAYS * 86400
                subset = [r for r in recs if r.get("first_seen", 0) >= cutoff]
            else:
                subset = [r for r in recs if r["tier"] == tier]
            text = replace_marker(text, f"TABLE_{name}", table(subset, now))

        text = replace_marker(text, "COUNT", f"**{len(recs)}** open roles")
        text = replace_marker(
            text, "UPDATED",
            f"_Last refreshed: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}_")
        with open(path, "w") as f:
            f.write(text)
        print(f"  {page['path']:20} {len(recs):5} roles")

    return len(all_recs)


if __name__ == "__main__":
    print(f"{main()} active roles rendered")

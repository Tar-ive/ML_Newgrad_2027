"""Instagram story sync tests. Offline: title resolution is stubbed.

What is pinned here is the bookkeeping around a story: which links count, how
they are cleaned so a reshared link dedupes, and when stored links are retried
or dropped. Getting this wrong either loses a story for good -- they expire in
24 hours -- or reposts the same role every run.

Run with: python3 tests/test_instagram.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import instagram  # noqa: E402
import sources  # noqa: E402

NOW = 1_800_000_000
DAY = 86400
failures = []


def expect(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


def event(story_id, *links, account="zero2sudo"):
    return {"type": "instagram.story.discovered", "account": {"username": account},
            "story": {"id": story_id, "posted_at": "2027-01-14T08:00:00Z",
                      "links": list(links)}}


WRAPPED = ("https://l.instagram.com/?u=https%3A%2F%2Fjob-boards.greenhouse.io%2Facme%2Fjobs%2F123"
           "%3Futm_source%3Dzero2sudo%26fbclid%3DPAZ&e=AUB")
ASHBY = "https://jobs.ashbyhq.com/acme/2d00752c-b3f2-40e1-9c50-60147c858d0b"


# --- Which links count ----------------------------------------------------
expect("unwrap l.instagram.com", instagram.unwrap(WRAPPED),
       "https://job-boards.greenhouse.io/acme/jobs/123?utm_source=zero2sudo&fbclid=PAZ")
expect("unwrap leaves other links", instagram.unwrap(ASHBY), ASHBY)
expect("wrapped sticker is unwrapped and untracked",
       instagram.sticker_links(event("1", {"url": WRAPPED})),
       ["https://job-boards.greenhouse.io/acme/jobs/123"])
expect("resolved_url wins over the wrapper",
       instagram.sticker_links(event("1", {"url": WRAPPED, "resolved_url": ASHBY})), [ASHBY])
expect("ashby application form becomes the posting",
       instagram.sticker_links(event("1", {"resolved_url": ASHBY + "/application?embed=true"})),
       [ASHBY])
expect("image-only story has no links", instagram.sticker_links(event("1")), [])
expect("non-story lines are ignored",
       list(instagram.read_events(['{"type": "health"}', "", "not json",
                                   json.dumps(event("1", {"url": WRAPPED}))])),
       [event("1", {"url": WRAPPED})])


# --- Merging into the store -----------------------------------------------
def found(url):
    return {"company": "Acme", "title": "Machine Learning Engineer, New Grad",
            "locations": ["New York, NY"]}


store = {}
added = instagram.merge(store, [event("1", {"resolved_url": ASHBY}),
                                event("2", {"resolved_url": ASHBY})], NOW, resolve=found)
expect("a link reshared in two stories is stored once", (added, len(store)), (1, 1))
expect("resolved title is stored", store[ASHBY]["title"], "Machine Learning Engineer, New Grad")
expect("story date becomes the posted date", store[ASHBY]["posted"], NOW - DAY)

store = {}
instagram.merge(store, [event("1", {"resolved_url": ASHBY})], NOW, resolve=lambda url: None)
expect("unresolvable link is kept for a retry", store[ASHBY]["title"], None)
instagram.merge(store, [], NOW + DAY, resolve=found)
expect("retry fills the title in later", store[ASHBY]["title"], "Machine Learning Engineer, New Grad")
expect("retry keeps first_seen", store[ASHBY]["first_seen"], NOW)
instagram.merge(store, [], NOW + (instagram.KEEP_DAYS + 1) * DAY, resolve=found)
expect("old links age out", store, {})


# --- Feeding the aggregator -----------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "instagram.json")
    with open(path, "w") as f:
        json.dump([dict(found(ASHBY), url=ASHBY, posted=NOW, first_seen=NOW),
                   {"url": "https://example.com/x", "posted": NOW, "first_seen": NOW,
                    "company": None, "title": None, "locations": []}], f)
    rows = sources.from_instagram(path)
    expect("only titled links become records", [r["url"] for r in rows], [ASHBY])
    expect("records carry the instagram source", rows[0]["source"], "instagram")
expect("missing store is no records", sources.from_instagram("/nonexistent/instagram.json"), [])


if failures:
    print("\n".join(failures))
    sys.exit(1)
print("instagram: all checks passed")

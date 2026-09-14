"""Decide, for every stored posting, whether it is still worth showing.

A role reaches data/listings.json because some tracker listed it and the title
classifier liked it. Neither is evidence the role is open, or that it is really
entry level. This stage collects that evidence from the employer and records
it on the posting as a `verification` block, which render.py obeys:

    status    live | closed | unknown | unresolvable | too_senior
    via       which check decided (greenhouse, workday, tiktok, page, ...)
    reason    why, in words
    checked   when, rounded to the hour
    strikes   consecutive non-authoritative "closed" sightings
    years     the experience requirement read from the description, if any
    evidence  the sentence that requirement came from
    posted    the employer's own posting date, when it reports one

The rules, and the failure each one prevents:

  * `unknown` never hides a role that was already verified. A bot wall or a
    slow API is not a closure.
  * A non-authoritative closure (Lever 404, a page redirecting to /careers,
    absence from a paginated board scrape) needs SOFT_STRIKES sightings at
    least STRIKE_GAP apart before it counts.
  * If one ATS reports more than MASS_CLOSURE_SHARE of its checked roles
    closed in a single run, those closures are thrown away. That is an outage
    or an API change, not a hiring freeze.
  * A role nobody can verify is shown for UNVERIFIED_GRACE_DAYS after it first
    appears, then hidden. New roles get a fair chance; unverifiable old ones
    do not linger.
  * Anything older than MAX_AGE_DAYS by the best posting date available is
    hidden, verified or not.
  * Bumping VERSION re-verifies everything on the next run, so a rule change
    reaches the whole list at once rather than as rows happen to come due.
"""
import collections
import concurrent.futures as futures
import re
import threading
import time
from urllib.parse import urlsplit

import experience
import verify_ats

VERSION = 1

HOUR, DAY = 3600, 86400
LIVE_TTL = 12 * HOUR
UNKNOWN_TTL = 6 * HOUR
TERMINAL_TTL = 3 * DAY       # closed / too_senior: cheap insurance against a bad call
LOST_CONTACT = 3 * DAY       # a live role whose rechecks keep failing stops counting as live
SOFT_STRIKES = 2
STRIKE_GAP = 2 * HOUR
# Measured against the employer's own posting date where the ATS reports one,
# because trackers re-date evergreen requisitions: one "Data Scientist" listed
# upstream as posted this week had been open on the employer's board for nine
# years. 90 days reaches back to mid-June, before the 2027 cycle opened.
MAX_AGE_DAYS = 90
UNVERIFIED_GRACE_DAYS = 14
MASS_CLOSURE_SHARE = 0.5
MASS_CLOSURE_MIN = 10

WORKERS = 16
PER_HOST = 4

HIDDEN = {"closed", "unresolvable", "too_senior"}

# An employer that titles a role "New Grad" has said what level it is. A
# years figure in that description is research or PhD time counted toward the
# requirement ("Applied Research Scientist - New Grad ... 5+ years of ML"),
# so the title outranks it. Weaker markers ("Associate", "Jr.") do not: at a
# bank "Associate" is the level after analyst.
NEW_GRAD_TITLE = re.compile(
    r"new ?grad|university grad|college grad|recent grad|\bcampus\b|early[- ]career|"
    r"entry[- ]level|\bgraduate\b|20(2[6-8]) (start|grad)", re.I)


def hour_floor(ts):
    return int(ts) // HOUR * HOUR


def candidate_urls(rec):
    urls = [rec.get("url")] + list(rec.get("urls") or [])
    return [u for u in dict.fromkeys(urls) if u]


def best_url(rec):
    urls = candidate_urls(rec)
    return min(urls, key=verify_ats.link_rank) if urls else None


def posted_at(rec):
    v = rec.get("verification") or {}
    return v.get("posted") or rec.get("date_posted") or rec.get("first_seen")


def due(rec, now):
    """Whether a posting should be (re)checked this run."""
    if not rec.get("active"):
        return False
    v = rec.get("verification")
    if not v or v.get("v") != VERSION or v.get("url") != best_url(rec):
        return True
    ttl = {"live": LIVE_TTL, "unknown": UNKNOWN_TTL}.get(v.get("status"), TERMINAL_TTL)
    if v.get("strikes"):
        ttl = min(ttl, STRIKE_GAP)
    return now - v.get("checked", 0) >= ttl


def apply(rec, result, now):
    """Fold one check result into a posting's verification block."""
    prev = rec.get("verification") or {}
    same_version = prev.get("v") == VERSION
    v = {"v": VERSION, "url": best_url(rec), "via": result["via"],
         "reason": result["reason"], "checked": hour_floor(now),
         "strikes": 0, "years": prev.get("years") if same_version else None,
         "evidence": prev.get("evidence") if same_version else None,
         "posted": result.get("posted") or prev.get("posted")}
    if result.get("apply_url"):
        rec["apply_url"] = result["apply_url"]
    status = result["status"]

    if status == "live":
        v["status"] = "live"
        v["confirmed"] = hour_floor(now)
        if result.get("description"):
            read = experience.read(result["description"])
            v["years"] = experience.label(read["required"])
            v["evidence"] = read["evidence"]
            if not read["acceptable"] and not NEW_GRAD_TITLE.search(rec.get("title", "")):
                v["status"] = "too_senior"
                v["reason"] = f"description requires {v['years']}"
    elif status == "closed" and result["authoritative"]:
        v["status"] = "closed"
    elif status == "closed":
        gap_ok = now - prev.get("checked", 0) >= STRIKE_GAP
        v["strikes"] = prev.get("strikes", 0) + (1 if gap_ok or not prev.get("strikes") else 0)
        needed = result.get("strikes_needed", SOFT_STRIKES)
        if v["strikes"] >= needed:
            v["status"] = "closed"
        else:
            # One sighting is a suspicion. Keep showing what we showed before.
            v["status"] = prev.get("status") if prev.get("status") in ("live", "unknown") else "unknown"
            v["reason"] = f"{result['reason']} (strike {v['strikes']}/{needed})"
    elif status == "unresolvable":
        v["status"] = "unresolvable"
    else:
        # Could not tell. A verified role stays verified through a blip.
        keep = prev.get("status") if same_version and prev.get("status") in ("live", "too_senior") else None
        last_good = prev.get("confirmed") or prev.get("checked", 0)
        if keep == "live" and now - last_good > LOST_CONTACT:
            keep = None  # verified once, unreachable for days: no longer vouched for
        v["status"] = keep or "unknown"
        v["confirmed"] = last_good if keep else None
        v["strikes"] = prev.get("strikes", 0)
        if keep:
            v["checked"] = prev.get("checked", v["checked"])  # retry soon, not in 12h
            v["reason"] = f"recheck failed: {result['reason']}"
    rec["verification"] = v


def visible(rec, now=None):
    """Whether render.py should show a posting."""
    now = now or time.time()
    if not rec.get("active"):
        return False
    v = rec.get("verification") or {}
    if v.get("status") in HIDDEN:
        return False
    posted = posted_at(rec)
    if posted and now - posted > MAX_AGE_DAYS * DAY:
        return False
    if v.get("status") == "live":
        return True
    # Unverified: a grace period for new roles with a direct employer link.
    fresh = now - (rec.get("first_seen") or now) <= UNVERIFIED_GRACE_DAYS * DAY
    return fresh and verify_ats.link_rank(best_url(rec) or "") < 4


def _suppress_mass_closures(results, log):
    by_via = collections.defaultdict(list)
    for rec, result in results:
        by_via[result["via"]].append(result)
    for via, rows in by_via.items():
        closed = [r for r in rows if r["status"] == "closed"]
        if len(rows) >= MASS_CLOSURE_MIN and len(closed) / len(rows) > MASS_CLOSURE_SHARE:
            log(f"  ! {via}: {len(closed)}/{len(rows)} checks say closed -- suppressed as an outage")
            for r in closed:
                r.update(status="unknown", authoritative=False,
                         reason=f"mass closure suppressed ({r['reason']})")


def run(store, boards=None, budget=None, now=None, log=print):
    """Verify the postings in `store` (id -> record) that are due. Mutates them."""
    now = now or time.time()
    queue = [r for r in store.values() if due(r, now)]
    # Never-checked first, then the stalest.
    queue.sort(key=lambda r: (bool(r.get("verification")), (r.get("verification") or {}).get("checked", 0)))
    if budget is not None:
        queue = queue[:budget]

    host_limits = collections.defaultdict(lambda: threading.Semaphore(PER_HOST))

    def one(rec):
        url = best_url(rec)
        with host_limits[urlsplit(url).netloc]:
            try:
                return rec, verify_ats.check(url, rec.get("title", ""), boards)
            except Exception as e:  # a checker bug must not take down the refresh
                return rec, verify_ats.unknown("error", f"{type(e).__name__}: {e}"[:120])

    started = time.time()
    with futures.ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(one, queue))
    _suppress_mass_closures(results, log)
    for rec, result in results:
        apply(rec, result, now)

    outcome = collections.Counter(r["verification"]["status"] for r, _ in results)
    shown = sum(1 for r in store.values() if visible(r, now))
    log(f"  verify: checked {len(results)} of {len(store)} in {time.time() - started:.0f}s -> "
        + "  ".join(f"{k}={v}" for k, v in outcome.most_common()))
    log(f"  verify: {shown} postings visible")
    return outcome

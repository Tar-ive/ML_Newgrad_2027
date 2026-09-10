"""Merge every source into data/listings.json, the repo's canonical store.

The store is stateful on purpose: keeping first_seen across runs is what lets
the README show which roles are genuinely new today, which is the whole point
of being fast.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import classify, normalize_company, role_family  # noqa: E402
import sources  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "listings.json")

# A role absent from every source for this long is treated as closed.
STALE_DAYS = 5

# Sources that list every role at a company rather than a curated new-grad set.
# Postings from these must prove they are entry level before being kept.
STRICT_SOURCES = {"ats"}

DAY = 86400


def day_floor(ts):
    """Round a timestamp down to UTC midnight.

    Timestamps are stored at day granularity so the four daily refreshes only
    produce a diff when a listing actually changed, instead of rewriting every
    row's last_seen four times a day.
    """
    return (int(ts) // DAY) * DAY if ts else ts

TITLE_NOISE = re.compile(
    r"\b(20\d\d|start|starting|new grad(uate)?|university grad(uate)?|"
    r"campus|early career|entry level|full[- ]time|\(.*?\))\b", re.I)


def canonical_url(url):
    """Strip tracking noise so the same posting on two lists collapses to one."""
    try:
        s = urlsplit(url)
    except ValueError:
        return url.lower()
    host = s.netloc.lower().removeprefix("www.")
    path = s.path.rstrip("/").removesuffix("/application").removesuffix("/apply")
    return f"{host}{path}".lower()


def normalize_title(title):
    t = TITLE_NOISE.sub(" ", (title or "").lower())
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def region(locations):
    """Coarse location key for dedupe: first state/country token we can find."""
    if not locations:
        return ""
    tail = locations[0].split(",")[-1].strip().lower()
    return re.sub(r"[^a-z]", "", tail)[:12]


def keys(rec):
    """Every identity a posting can be matched on."""
    out = []
    if rec["url"]:
        out.append("u:" + canonical_url(rec["url"]))
    nt = normalize_title(rec["title"])
    nc = normalize_company(rec["company"])
    if nt and nc:
        out.append(f"t:{nc}|{nt}|{region(rec['locations'])}")
    return out


def merge_into(dst, src):
    """Fold a duplicate into the record we're keeping, preferring richer data."""
    dst["sources"] = sorted(set(dst["sources"]) | {src["source"]})
    for field in ("company_url", "salary"):
        if not dst.get(field) and src.get(field):
            dst[field] = src[field]
    if src["date_posted"] and (not dst["date_posted"] or src["date_posted"] > dst["date_posted"]):
        dst["date_posted"] = src["date_posted"]
    known = {l.lower() for l in dst["locations"]}
    for loc in src["locations"]:
        if loc.lower() not in known:
            dst["locations"].append(loc)
            known.add(loc.lower())


def load_store():
    if os.path.exists(STORE):
        with open(STORE) as f:
            return {r["id"]: r for r in json.load(f)}
    return {}


def main(ats_tier="fast", trackers=True):
    now = day_floor(time.time())
    if trackers:
        raw, report = sources.fetch_all()
    else:
        raw, report = [], []

    if ats_tier:
        import ats_live  # imported lazily: only this path needs ats-scrapers
        live = ats_live.fetch(ats_tier)
        raw.extend(live)
        report.append((f"ats-{ats_tier}", len(live), None))

    kept = {}      # id -> record
    index = {}     # key -> id
    dropped = 0
    for r in raw:
        strict = r["source"] in STRICT_SOURCES
        keep, tier = classify(r["title"], r["category"], r["company"],
                              experience=r.get("experience"), strict=strict,
                              description=r.get("description"))
        if not keep:
            dropped += 1
            continue
        ks = keys(r)
        hit = next((index[k] for k in ks if k in index), None)
        if hit:
            merge_into(kept[hit], r)
            for k in ks:
                index.setdefault(k, hit)
            continue
        rid = hashlib.sha1((ks[0] if ks else r["url"]).encode()).hexdigest()[:12]
        rec = dict(r)
        rec.pop("source")
        # Descriptions are megabytes and only the classifier reads them.
        description = rec.pop("description", None)
        rec.update({
            "id": rid,
            "tier": tier,
            "family": role_family(r["title"], r["category"], r["company"], description),
            "is_usa": sources.is_usa(r["locations"], r["title"]),
            "sources": [r["source"]],
        })
        kept[rid] = rec
        for k in ks:
            index.setdefault(k, rid)

    store = load_store()
    new_today = 0
    for rid, rec in kept.items():
        prev = store.get(rid)
        if prev:
            rec["first_seen"] = prev.get("first_seen", now)
        else:
            # On a cold start, trust the upstream posting date so the "new this
            # week" section does not claim 600 roles appeared today.
            posted = rec.get("date_posted")
            rec["first_seen"] = min(posted, now) if posted else now
            new_today += 1
        rec["last_seen"] = now
        rec["active"] = True
        store[rid] = rec

    # Tightening the classifier must take effect now, not in STALE_DAYS. Any
    # stored role that no longer passes even the lenient gate is dropped
    # outright rather than left to age out.
    pruned = [rid for rid, rec in store.items()
              if rid not in kept and not classify(rec["title"], rec.get("category"),
                                                  rec["company"])[0]]
    for rid in pruned:
        del store[rid]

    closed = 0
    for rid, rec in store.items():
        if rid in kept:
            continue
        if rec.get("active") and now - rec.get("last_seen", now) > STALE_DAYS * DAY:
            rec["active"] = False
            closed += 1

    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    ordered = sorted(store.values(), key=lambda r: -(r.get("date_posted") or r["first_seen"]))
    with open(STORE, "w") as f:
        json.dump(ordered, f, indent=1, sort_keys=True)
        f.write("\n")

    for name, n, err in report:
        print(f"  {name:18} {n:6}" + (f"  FAILED: {err}" if err else ""))
    families = collections.Counter(r.get("family") for r in kept.values())
    print("  families           " + "  ".join(
        f"{k}={v}" for k, v in sorted(families.items(), key=lambda kv: -kv[1])))
    print(f"raw={len(raw)} ml_new_grad={len(kept)} filtered_out={dropped} "
          f"new={new_today} closed={closed} pruned={len(pruned)} store={len(store)}")
    return f"{len(kept)} roles, {new_today} new"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Refresh data/listings.json")
    ap.add_argument("--ats", default="fast", choices=["fast", "heavy", "all", "none"],
                    help="which ATS tier to scrape live (default: fast)")
    ap.add_argument("--no-trackers", action="store_true",
                    help="skip the community trackers; they only update daily")
    args = ap.parse_args()
    print(main(None if args.ats == "none" else args.ats,
               trackers=not args.no_trackers))

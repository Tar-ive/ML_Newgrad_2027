"""Verification regression tests. Offline: no network, only the decisions.

The checks themselves talk to live ATS APIs and cannot be pinned here. What
can be pinned is everything around them -- how links resolve, and how a run
of verdicts turns into shown or hidden -- which is where a quiet mistake would
either empty the list or let dead roles back in.

Run with: python3 tests/test_verify.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import verify  # noqa: E402
import verify_ats as V  # noqa: E402

NOW = 1_800_000_000
DAY, HOUR = 86400, 3600
failures = []


def expect(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# --- Link resolution ------------------------------------------------------
ZAPPLY = "https://zapply.jobs/l/d/{}?s=gh-new-grad-data-science-jobs-2027"
expect("zapply ashby", V.employer_url(ZAPPLY.format("ashby-anyscale-1466478e-9797-4318-bdca-bb1ae5798d52")),
       "https://jobs.ashbyhq.com/anyscale/1466478e-9797-4318-bdca-bb1ae5798d52")
expect("zapply lever", V.employer_url(ZAPPLY.format("lever-spotify-1bbaf909-5ff3-4ed6-87ca-f7ff007a169c")),
       "https://jobs.lever.co/spotify/1bbaf909-5ff3-4ed6-87ca-f7ff007a169c")
expect("zapply smartrecruiters", V.employer_url(ZAPPLY.format("sr-CapTechConsulting-744000115292477")),
       "https://jobs.smartrecruiters.com/CapTechConsulting/744000115292477")
expect("zapply bytedance", V.employer_url(ZAPPLY.format("bytedance-7672395094280063285")),
       "https://joinbytedance.com/search/7672395094280063285")
expect("zapply workday defers to network", V.employer_url(ZAPPLY.format("workday-bah-bah-jobs-R0248942")),
       "workday-slug:workday-bah-bah-jobs-R0248942")
expect("zapply unknown slug", V.employer_url(ZAPPLY.format("amazon-b8d4e2a2-5af7-4afc-92e7-e47e463256b2")), None)
expect("tracking stripped, gh_jid kept",
       V.employer_url("https://instacart.careers/job/?gh_jid=8143263&utm_source=aprameyak"),
       "https://instacart.careers/job/?gh_jid=8143263")
expect("jobright is opaque", V.is_opaque("https://jobright.ai/jobs/info/6a71a3f9"), True)
expect("greenhouse is not opaque", V.is_opaque("https://job-boards.greenhouse.io/x/jobs/1"), False)

expect("workday cxs with locale",
       V.workday_cxs("https://bah.wd1.myworkdayjobs.com/en-US/bah_jobs/job/Washington-DC/Data-Scientist_R0248942?x=1"),
       "https://bah.wd1.myworkdayjobs.com/wday/cxs/bah/bah_jobs/job/Washington-DC/Data-Scientist_R0248942")
expect("workday cxs myworkdaysite",
       V.workday_cxs("https://wd5.myworkdaysite.com/en-US/recruiting/acme/External/job/NYC/ML-Engineer_R1"),
       "https://wd5.myworkdaysite.com/wday/cxs/acme/External/job/NYC/ML-Engineer_R1")
expect("workday search page is not a job", V.workday_cxs("https://bah.wd1.myworkdayjobs.com/bah_jobs"), None)

expect("board key tiktok", V.board_key("https://lifeattiktok.com/search/7683577550217365765"),
       ("tiktok", "7683577550217365765"))
expect("board key google", V.board_key(
    "https://www.google.com/about/careers/applications/jobs/results/137298025448907462-product-marketing"),
    ("google", "137298025448907462"))
expect("board key apple", V.board_key("https://jobs.apple.com/en-us/details/200313970/in-business"),
       ("apple", "200313970"))
expect("board key tesla", V.board_key("https://www.tesla.com/careers/search/job/ai-engineer-optimus-224501"),
       ("tesla", "224501"))
expect("board key uber", V.board_key("https://jobs.uber.com/en/jobs/302095/"), ("uber", "302095"))
expect("board key none", V.board_key("https://jobs.lever.co/a/b"), None)

expect("workday today", V.workday_posted("Posted Today", NOW), NOW)
expect("workday 12 days", V.workday_posted("Posted 12 Days Ago", NOW), NOW - 12 * DAY)
expect("workday 30+ is a bound, not a date", V.workday_posted("Posted 30+ Days Ago", NOW), None)

ranked = sorted(["https://jobright.ai/jobs/info/1", "https://www.dreamworkhq.com/job/1",
                 "https://acme.com/careers/ml-engineer", "https://job-boards.greenhouse.io/acme/jobs/1"],
                key=V.link_rank)
expect("most direct link verified first", ranked[0], "https://job-boards.greenhouse.io/acme/jobs/1")
expect("opaque link verified last", ranked[-1], "https://jobright.ai/jobs/info/1")
expect("title match", V.titles_match("Machine Learning Engineer, Ads",
                                     "<title>Machine Learning Engineer - Ads | Acme</title>"), True)
expect("title mismatch", V.titles_match("Machine Learning Engineer, Ads",
                                        "<title>Search Jobs | Acme Careers</title>"), False)


# --- Verification state machine -------------------------------------------
def rec(**kw):
    base = {"active": True, "url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "title": "ML Engineer", "first_seen": NOW - DAY, "date_posted": NOW - DAY}
    base.update(kw)
    return base


def result(status, authoritative=True, description=None, via="greenhouse"):
    return {"status": status, "via": via, "reason": status, "authoritative": authoritative,
            "description": description, "posted": None, "apply_url": None}


r = rec()
verify.apply(r, result("live", description="<li>1+ years of experience</li>"), NOW)
expect("live stays live", r["verification"]["status"], "live")
expect("live shown", verify.visible(r, NOW), True)

r = rec()
verify.apply(r, result("live", description="<li>3-5 years of industry experience</li>"), NOW)
expect("3-5 years hidden", (r["verification"]["status"], verify.visible(r, NOW)), ("too_senior", False))

r = rec(title="Applied Research Scientist - New Grad - Perception")
verify.apply(r, result("live", description="<li>5+ years of experience in Machine Learning</li>"), NOW)
expect("an explicit new-grad title outranks a years figure", verify.visible(r, NOW), True)
r = rec(title="AI Integration Software Engineer - Associate")
verify.apply(r, result("live", description="<li>3-5 years of software development experience</li>"), NOW)
expect("'Associate' is not a new-grad title", verify.visible(r, NOW), False)

r = rec()
verify.apply(r, result("closed"), NOW)
expect("authoritative closure hides at once", verify.visible(r, NOW), False)

r = rec()
verify.apply(r, result("live"), NOW)
verify.apply(r, result("closed", authoritative=False, via="lever"), NOW + 12 * HOUR)
expect("one soft strike keeps showing", (r["verification"]["strikes"], verify.visible(r, NOW + 12 * HOUR)), (1, True))
expect("a struck role comes due soon", verify.due(r, NOW + 12 * HOUR + verify.STRIKE_GAP), True)
verify.apply(r, result("closed", authoritative=False, via="lever"), NOW + 12 * HOUR + 10 * 60)
expect("strikes minutes apart do not add up", r["verification"]["strikes"], 1)
verify.apply(r, result("closed", authoritative=False, via="lever"), NOW + 15 * HOUR)
expect("second soft strike closes", verify.visible(r, NOW + 15 * HOUR), False)

r = rec(url="https://jobs.apple.com/en-us/details/200313970")
verify.apply(r, result("live", via="apple"), NOW)
board_miss = V.check_board_member("https://jobs.apple.com/en-us/details/200313970", {"apple": {"1"}})
for hours in (6, 12):
    verify.apply(r, dict(board_miss), NOW + hours * HOUR)
expect("two board misses do not close", verify.visible(r, NOW + 12 * HOUR), True)
verify.apply(r, dict(board_miss), NOW + 18 * HOUR)
expect("a third board miss does", verify.visible(r, NOW + 18 * HOUR), False)
expect("an unscraped board is unknown, not closed",
       V.check_board_member("https://jobs.apple.com/en-us/details/200313970", {})["status"], "unknown")

r = rec()
verify.apply(r, result("live"), NOW)
verify.apply(r, result("closed", authoritative=False), NOW + 13 * HOUR)
verify.apply(r, result("live"), NOW + 16 * HOUR)
expect("a live sighting clears strikes", r["verification"]["strikes"], 0)

r = rec()
verify.apply(r, result("live"), NOW)
verify.apply(r, result("unknown", authoritative=False, via="workday"), NOW + 13 * HOUR)
expect("a blip does not unverify", (r["verification"]["status"], verify.visible(r, NOW + 13 * HOUR)), ("live", True))
verify.apply(r, result("unknown", authoritative=False, via="workday"), NOW + 4 * DAY)
expect("days of silence do", r["verification"]["status"], "unknown")

new, old = rec(first_seen=NOW - 2 * DAY), rec(first_seen=NOW - 30 * DAY, date_posted=NOW - 30 * DAY)
for x in (new, old):
    verify.apply(x, result("unknown", authoritative=False, via="page"), NOW)
expect("unverified new role gets a grace period", verify.visible(new, NOW), True)
expect("unverified old role is hidden", verify.visible(old, NOW), False)

r = rec(date_posted=NOW - 120 * DAY, first_seen=NOW - 120 * DAY)
verify.apply(r, result("live"), NOW)
expect("verified but 120 days old is hidden", verify.visible(r, NOW), False)
r = rec(date_posted=NOW - DAY)
live = result("live")
live["posted"] = NOW - 9 * 365 * DAY
verify.apply(r, live, NOW)
expect("the employer's date beats a tracker's fresh one", verify.visible(r, NOW), False)

r = rec(url="https://jobright.ai/jobs/info/1")
expect("never-checked opaque link is not shown", verify.visible(r, NOW), False)
r = rec(url="https://jobright.ai/jobs/info/1", urls=["https://job-boards.greenhouse.io/acme/jobs/9"])
expect("a merged direct link is what gets verified", verify.best_url(r), "https://job-boards.greenhouse.io/acme/jobs/9")

outage = [(rec(), result("closed", via="ashby")) for _ in range(12)] + [(rec(), result("live", via="ashby"))]
verify._suppress_mass_closures(outage, log=lambda *_: None)
expect("mass closure suppressed", sum(1 for _, x in outage if x["status"] == "closed"), 0)
normal = [(rec(), result("closed", via="lever")) for _ in range(2)] + [(rec(), result("live", via="lever")) for _ in range(10)]
verify._suppress_mass_closures(normal, log=lambda *_: None)
expect("ordinary closures kept", sum(1 for _, x in normal if x["status"] == "closed"), 2)

r = rec()
verify.apply(r, result("live"), NOW)
r["verification"]["v"] = verify.VERSION - 1
expect("version bump forces a recheck", verify.due(r, NOW + HOUR), True)


if __name__ == "__main__":
    for f in failures:
        print(f"  FAIL {f}")
    total = sum(1 for line in open(__file__) if line.lstrip().startswith("expect("))
    print(f"{total - len(failures)}/{total} verification cases pass")
    sys.exit(1 if failures else 0)

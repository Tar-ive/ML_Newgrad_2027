"""Classifier regression tests.

The classifier is the whole product: everything else just moves rows around.
These cases are drawn from real postings that were wrongly kept or wrongly
dropped at some point, so they are a record of actual mistakes, not a wishlist.

Run with: python3 tests/test_classify.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from classify import classify  # noqa: E402

# (title, category, company) that must appear in the list.
KEEP = [
    ("Machine Learning Engineer", "AI/ML/Data", "Stripe"),
    ("ML Infrastructure Engineer, Safeguards", "AI/ML/Data", "Anthropic"),
    ("Research Scientist, Reasoning", None, "OpenAI"),
    ("Applied Scientist", "AI/ML/Data", "Amazon"),
    ("Computer Vision Engineer", None, "Waymo"),
    ("Perception Engineer, Autonomy", None, "Zoox"),
    ("MLOps Engineer", None, "Rocket Companies"),
    ("Quantitative Researcher - PhD: 2027", None, "Jane Street"),
    ("Data Scientist", "AI/ML/Data", "Arcadis"),
    # Software engineering titles that carry a real ML specialization.
    ("Software Engineer, AI/Machine Learning, PhD, Early Career, 2027 Start", None, "Google"),
    ("Software Engineer Graduate (TikTok Recommendation Architecture) - 2027 Start", None, "TikTok"),
    ("LLM Backend Engineer Graduate - Applied Machine Learning", None, "ByteDance"),
    ("Software Engineer 1 New Grad - Perception", None, "Zoox"),
]

# (title, category, company) that must never appear.
DROP = [
    # Plain software engineering. "AI" names the product, team, or tooling.
    ("AI Security Software Engineer (Starshield)", None, "SpaceX"),
    ("Software Engineer, AI Satellites (Starmind)", None, "SpaceX"),
    ("Application Software Engineer, Applied AI", None, "SpaceX"),
    ("AI-Augmented Software Engineer", None, "Some Startup"),
    ("Junior AI Software Engineer", None, "Consultancy"),
    ("Backend Software Engineer, AI Infrastructure for SDLC", None, "TikTok"),
    ("Frontend Engineer, AI Observability & Evals Platform", None, "LangChain"),
    ("Site Reliability Engineer, AI Platform", None, "Big Co"),
    # AI-adjacent work that is not modelling.
    ("AI Prompt Engineer", None, "Agency"),
    ("AI Solutions Engineer", None, "Vendor"),
    ("AI QE Engineer - Associate", None, "Kyndryl"),
    ("Junior IT Infrastructure & AI Engineer", None, "Enterprise"),
    ("AI Business Development Analyst", "AI/ML/Data", "Houlihan Lokey"),
    # Wrong level or wrong kind of role entirely.
    ("Senior Applied Scientist", "AI/ML/Data", "Amazon"),
    ("Data Scientist - Mid", "AI/ML/Data", "Booz Allen"),
    ("Deep Learning Algorithm Engineering Intern - 2026", None, "NVIDIA"),
    ("Research Scientist - Antibody Discovery", "AI/ML/Data", "Elanco"),
    ("Thermal Engineer - AI Satellites - Starmind", None, "SpaceX"),
    ("Mechatronics & Robotics Tech", None, "Amazon"),
]

# Raw ATS feeds list every role at a company, so they need positive evidence of
# being entry level: (title, years_experience, should_keep).
STRICT = [
    ("Machine Learning Engineer, University Grad 2027", None, True),
    ("Software Engineer, AI/ML, Search Personalization", 2, True),
    ("Research Engineer, Code RL (Reinforcement Learning)", 8, False),
    ("Research Engineer, Cybersecurity RL", None, False),  # no evidence either way
]


def main():
    failures = []
    for title, category, company in KEEP:
        if not classify(title, category, company)[0]:
            failures.append(f"wrongly dropped: {title}")
    for title, category, company in DROP:
        if classify(title, category, company)[0]:
            failures.append(f"wrongly kept: {title}")
    for title, years, expected in STRICT:
        got = classify(title, None, "Anthropic", experience=years, strict=True)[0]
        if got != expected:
            verb = "dropped" if expected else "kept"
            failures.append(f"strict mode wrongly {verb}: {title}")

    total = len(KEEP) + len(DROP) + len(STRICT)
    for f in failures:
        print(f"  FAIL {f}")
    print(f"{total - len(failures)}/{total} classifier cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Classifier regression tests.

The classifier is the whole product: everything else just moves rows around.
These cases are drawn from real postings that were wrongly kept or wrongly
dropped at some point, so they are a record of actual mistakes, not a wishlist.

Run with: python3 tests/test_classify.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from classify import classify, role_family  # noqa: E402

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
    # Data science is a family in its own right and needs no ML qualifier.
    ("Associate Data Scientist", None, "Culture Amp"),
    ("Data Science New Grad", None, "Hewlett Packard Enterprise"),
    ("Decision Scientist, New Grad", None, "ibotta"),
    # Data engineering, but only with the specialization in the title.
    ("Machine Learning Data Engineer", None, "Some Co"),
    # "AI Scientist" names the work; only "AI Engineer" is ambiguous.
    ("AI Scientist I", None, "Axon"),
    ("AI Research Engineer", None, "Jump Trading"),
    # A stated requirement inside the early-career band.
    ("Machine Learning Engineer", None, "Yelp"),
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
    # Silicon. The whole title reads as AI because the chip is for AI.
    ("System AI Engineer New Grad - Display - ASICS Engineering", None, "Qualcomm"),
    ("PCB Design EDA and AI Engineer - New College Graduate 2027", None, "NVIDIA"),
    ("Silicon & AI Systems Innovation Engineer", None, "Annapurna Labs"),
    ("Electrical Hardware Engineer, AI Satellites (Starmind)", None, "SpaceX"),
    ("Power Electronics Engineer, AI Satellites (Starmind)", None, "SpaceX"),
    ("Semiconductor Packaging Research Engineer", None, "Intel"),
    ("Embedded Systems Engineer - Robotics Hardware", None, "Field AI"),
    ("Research Scientist New Grad - Circuits", "AI/ML/Data", "NVIDIA"),
    # Data labeling and teleoperation, not engineering.
    ("Robotics Data Collection Operator", None, "Dexmate"),
    ("AI/ML Data Contributor", None, "TSMG"),
    ("Motion Capture Participant - Robotics Project", None, "TSMG"),
    ("Teleoperator - Robotics", None, "FS Studio"),
    # Consultancies and enterprise IT integrating an LLM API.
    ("Forward Deployed Engineer, GenAI", None, "Scale AI"),
    ("Associate AI Engineer - Early Career Consult Program", None, "Kyndryl"),
    ("AI Ops Engineer - GTM", None, "Tapcart"),
    ("AI Customer Insights Engineer", None, "Seeq"),
    ("Copilot Developer/AI Engineer", None, "Pyrovio"),
    # Not a full-time new-grad job.
    ("2027 Data Science Summer Analyst", None, "Blackstone"),
    ("Duales Studium Data Science und Kunstliche Intelligenz B.Sc. 2027", None, "Carrier"),
    ("Part Time - Student - Graduate - AI Research Assistant", None, "Penn State"),
    ("Pharmaziepraktikantin im Bereich FBC FF NLP Production Mai 2027", None, "Sanofi"),
    # Robotics without a learning component is mechanical work.
    ("Robotics Engineer - Motion Planning", None, "Contoro"),
    ("Subsea Robotics Engineer", None, "Johns Hopkins APL"),
    ("Systems Engineer - Robotics", None, "Allegro MicroSystems"),
    # "AI" used as a noun with no engineering or science attached.
    ("AI & Data Analyst", "AI/ML/Data", "Accenture"),
    ("AI Innovation Analyst", "AI/ML/Data", "Deloitte"),
    ("AI Resident", "AI/ML/Data", "Ema"),
    # Quantitative analytics on a bank risk desk is not research.
    ("2027 Quantitative Analytics Analyst Graduate Program New York", None, "Barclays"),
    # Wet lab and physical science sharing the research title.
    ("Exploratory Biology Research Scientist", None, "Vertex"),
    ("Research Scientist - Ceramist", None, "GE Vernova"),
    ("Associate Research Scientist - Real World Evidence", None, "Precision AQ"),
    # A plain data engineering title, with no ML specialization.
    ("AI Data Engineer", None, "UJET"),
    ("Agentic AI Data Engineer - CMC Data Integration", None, "Lilly"),
    # Test and validation engineering riding along on an autonomy program.
    ("2026 Early Career Flight Test Engineer - Mission Autonomy", None, "Anduril"),
    ("Software Validation Engineer, AI Platforms", None, "Tesla"),
]

# Roles that must land in a specific family, because the family is what the
# whitelist is written in terms of: (title, company, family).
FAMILIES = [
    ("Machine Learning Engineer, New Grad", "Stripe", "ml"),
    ("Data Scientist I", "Esri", "ds"),
    ("Quantitative Researcher - PhD: 2027", "Jane Street", "quant"),
    ("Software Engineer, Machine Learning Integration", "Tesla", "swe_ml"),
    ("Machine Learning Data Engineer", "Some Co", "de_ml"),
    ("Software Engineer, Backend", "Stripe", None),
    ("Data Engineer", "Stripe", None),
]

# A software engineering title with no ML in it is promoted only by a job
# description that is unmistakably about ML work -- two distinct signals, not
# one passing mention: (description, should_promote).
DESCRIPTIONS = [
    ("Build and ship backend services. We are an AI company.", False),
    ("Our mission is powered by machine learning.", False),
    ("Train models in PyTorch and own the ML pipeline end to end.", True),
    ("You will build computer vision systems and own model evaluation.", True),
]

# Experience is enforced for every source, not only the raw ATS feeds:
# (title, years, should_keep).
EXPERIENCE = [
    ("Machine Learning Engineer", 1, True),
    ("Machine Learning Engineer", 3, True),
    ("Machine Learning Engineer", 5, False),
    ("Data Scientist", 8, False),
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
    for title, company, expected in FAMILIES:
        got = role_family(title, None, company)
        if got != expected:
            failures.append(f"family {got!r} != {expected!r}: {title}")
    for description, expected in DESCRIPTIONS:
        got = classify("Software Engineer, New Grad", None, "Some Co",
                       description=description)[0]
        if got != expected:
            verb = "promoted" if got else "did not promote"
            failures.append(f"description wrongly {verb}: {description}")
    for title, years, expected in EXPERIENCE:
        got = classify(title, None, "Some Co", experience=years)[0]
        if got != expected:
            verb = "dropped" if expected else "kept"
            failures.append(f"experience gate wrongly {verb}: {title} ({years}y)")
    for title, years, expected in STRICT:
        got = classify(title, None, "Anthropic", experience=years, strict=True)[0]
        if got != expected:
            verb = "dropped" if expected else "kept"
            failures.append(f"strict mode wrongly {verb}: {title}")

    total = (len(KEEP) + len(DROP) + len(STRICT) + len(FAMILIES)
             + len(DESCRIPTIONS) + len(EXPERIENCE))
    for f in failures:
        print(f"  FAIL {f}")
    print(f"{total - len(failures)}/{total} classifier cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

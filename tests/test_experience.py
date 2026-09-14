"""Experience-requirement regression tests.

Each description is a trimmed excerpt of the shape real postings take. The
cases that matter most are the ones that fooled the old reader, which took the
smallest number anywhere in the text and read only the first 4,000 characters.

Run with: python3 tests/test_experience.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from experience import label, read  # noqa: E402

# (description, expected label or None, expected acceptable)
CASES = [
    # Nothing stated: acceptable, and the title gates the role instead.
    ("<p>You will train ranking models on billions of events.</p>", None, True),
    # The early-career band.
    ("<h3>Qualifications</h3><ul><li>0-2 years of industry experience</li></ul>", "0-2 yrs", True),
    ("<ul><li>2+ years of experience building ML systems</li></ul>", "2+ yrs", True),
    ("<ul><li>1 year of professional experience with Python</li></ul>", "1 yr", True),
    ("Requirements:\n3 years of experience in data science", "3 yrs", True),
    # What the user flagged: 3-5 and 3+ are mid-level.
    ("<ul><li>3-5 years of experience in machine learning</li></ul>", "3-5 yrs", False),
    ("<ul><li>3+ years of hands-on experience with PyTorch</li></ul>", "3+ yrs", False),
    ("Minimum Qualifications:\nAt least 4 years of relevant work experience", "4+ yrs", False),
    ("<li>Five or more years of professional experience</li>", "5+ yrs", False),
    # Preferred never counts against a role, by heading or by sentence.
    ("<h3>Minimum Qualifications</h3><ul><li>BS in CS</li><li>1+ years of experience</li></ul>"
     "<h3>Preferred Qualifications</h3><ul><li>5+ years of experience in ML</li></ul>", "1+ yrs", True),
    ("<ul><li>5+ years of experience is preferred</li></ul>", None, True),
    # ...but a bullet ending "a plus" must not turn the rest into a preferred section.
    ("Requirements:\nPyTorch a plus\n4+ years of professional experience", "4+ yrs", False),
    # The old reader's failure: smallest number wins, so this read as 2.
    ("<h3>Basic Qualifications</h3><ul><li>5+ years of software engineering experience</li>"
     "<li>2+ years of experience with machine learning</li></ul>", "5+ yrs", False),
    # Degree alternatives: the smallest path wins.
    ("<ul><li>Bachelor's degree and 5+ years of experience, or Master's degree and 3+ years "
     "of experience, or PhD and 0 years of experience</li></ul>", "0 yrs", True),
    ("<ul><li>Bachelor's degree with 4+ years of experience</li>"
     "<li>Master's degree with 2+ years of experience</li><li>PhD in Computer Science</li></ul>",
     "2+ yrs", True),
    ("<ul><li>PhD, or Master's degree and 4+ years of relevant experience in Computer Science</li></ul>",
     "0 yrs", True),
    ("<ul><li>Bachelor's degree or equivalent and 4+ years of professional experience</li></ul>",
     "4+ yrs", False),
    # Not experience requirements at all.
    ("With millions of diners and 25+ years of experience, OpenTable is part of Booking.", None, True),
    ("We have a 25+ year track record of innovation.", None, True),
    ("<li>4 years of relevant experience can substitute for a Bachelor's degree</li>", None, True),
    ("For over 20 years we have built search. You hold a 4-year degree.", None, True),
    ("Graduated within the last 2 years from an accredited university.", None, True),
    ("3+ years of academic experience with deep learning research", None, True),
    # Responsibilities are not requirements; a sentence far past 4,000 characters still counts.
    ("<h3>About the role</h3>" + "<p>Build models. </p>" * 400 +
     "<h3>Requirements</h3><ul><li>6+ years of industry experience</li></ul>", "6+ yrs", False),
    # A ceiling is not a requirement.
    ("<ul><li>Up to 2 years of professional experience</li></ul>", "0-2 yrs", True),
    ("<ul><li>No more than 3 years of industry experience</li></ul>", "0-3 yrs", True),
    # Greenhouse double-escapes its HTML.
    ("&lt;ul&gt;&lt;li&gt;3-5 years of experience&lt;/li&gt;&lt;/ul&gt;", "3-5 yrs", False),
]

NEW_GRAD = [
    ("This role is for new grads graduating in 2027.", True),
    ("Senior engineers with deep expertise.", False),
]


def main():
    failures = []
    for description, want_label, want_ok in CASES:
        got = read(description)
        if label(got["required"]) != want_label or got["acceptable"] != want_ok:
            failures.append(f"{description[:70]!r}: got {label(got['required'])!r}/"
                            f"{got['acceptable']}, want {want_label!r}/{want_ok}")
    for text, want in NEW_GRAD:
        if read(text)["new_grad_language"] != want:
            failures.append(f"new-grad language wrong for {text!r}")
    total = len(CASES) + len(NEW_GRAD)
    for f in failures:
        print(f"  FAIL {f}")
    print(f"{total - len(failures)}/{total} experience cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

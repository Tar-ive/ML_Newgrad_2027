"""Read how much experience a job description actually requires.

Titles lie about level. "Machine Learning Engineer" with no qualifier is as
likely to want five years as zero, and upstream trackers label it new grad
either way. The description is the only place an employer says what it means,
so this reads the requirement from there.

Reading it naively goes wrong in predictable ways, and each rule below exists
because a real posting broke the rule before it:

  * "5+ years required ... 2+ years preferred" is a five-year role. Taking the
    smallest number in the text calls it a two-year role. Mentions under a
    "Preferred" or "Nice to have" heading, or in a sentence that says so, never
    count against a role.
  * "3-5 years" starts at three but is a mid-level role. A range is judged by
    where it ends as well as where it starts.
  * "Bachelor's with 5 years, or Master's with 3, or PhD" is a PhD new-grad
    role. Degree-conditional mentions are alternatives, so the smallest wins.
  * "5+ years of software engineering and 2+ years of ML" requires five.
    Independent requirements stack, so the largest wins.
  * "We have been building for over 20 years", "4-year degree", and "graduated
    within the last 2 years" are not experience requirements at all.
"""
import html
import re

# The early-career band. A stated requirement is acceptable when its lower
# bound is at most ACCEPT_MIN_YEARS, or when it is exactly EDGE_YEARS with no
# "+" and no longer upper bound. So "2+ years" and "2-4 years" pass, "3 years"
# passes, and "3+ years", "3-5 years" and "5 years" do not.
ACCEPT_MIN_YEARS = 2
EDGE_YEARS = 3
MAX_PLAUSIBLE_YEARS = 15

WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}
WORD_NUMBER = re.compile(r"\b(" + "|".join(WORD_NUMBERS) + r")\b(?=\s*(?:\(\d+\)\s*)?(?:\+|-|–|to|or more)?\s*(?:years?|yrs?))", re.I)

# Block-level tags become line breaks before markup is stripped, so headings
# and bullets survive as separate lines.
BLOCK_TAGS = re.compile(r"<\s*/?\s*(p|div|li|ul|ol|br|h[1-6]|tr|section|strong|b)\b[^>]*>", re.I)
TAGS = re.compile(r"<[^>]+>")

YEAR_UNIT = r"(?:years?|yrs?)"
# Each pattern yields (low, high, plus). Order matters: ranges before singles.
MENTIONS = [
    # A ceiling ("up to 2 years", "no more than 3 years") is an upper bound on
    # what the role wants, which is the opposite of a requirement.
    (re.compile(r"(?:up to|no more than|at most|less than|fewer than|under|maximum of)\s*(\d{1,2})\s*" + YEAR_UNIT, re.I), "ceiling"),
    (re.compile(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*" + YEAR_UNIT, re.I), "range"),
    (re.compile(r"(\d{1,2})\s*\+?\s*(?:or more|or greater)\s*" + YEAR_UNIT, re.I), "plus"),
    (re.compile(r"(?:at least|minimum of|a minimum of|min\.?|no less than)\s*(\d{1,2})\s*\+?\s*" + YEAR_UNIT, re.I), "plus"),
    (re.compile(r"(\d{1,2})\s*\+\s*" + YEAR_UNIT, re.I), "plus"),
    (re.compile(r"(\d{1,2})\s*" + YEAR_UNIT + r"\s*(?:\+|or more|or greater|and above|plus\b)", re.I), "plus"),
    (re.compile(r"(\d{1,2})\s*" + YEAR_UNIT, re.I), "exact"),
]

# The mention has to be about experience, and close by.
EXPERIENCE_CONTEXT = re.compile(
    r"experience|industry|professional|work(ing)? (history|in)|hands[- ]on|"
    r"track record|background in|in (a|an) (similar|related) role", re.I)

# Mentions that look like requirements but are not.
NOT_A_REQUIREMENT = re.compile(
    r"years? old|years? of age|\d[- ]year (degree|program|college|university)|"
    r"(bachelor|master|associate)'?s? degree program|within the (last|past) \d|"
    r"graduat\w* (within|in the (last|past))|years? ago|for (over|more than) \d+ years|"
    r"founded|since \d{4}|in business|\d+ years? (running|in a row)|"
    r"(including|incl\.?|counting) (academic|internship|school|research|coursework)|"
    r"(academic|coursework|internship|school|research|graduate studies) experience|"
    r"(401k|vesting|tenure|anniversary|contract|assignment|visa|sponsorship)|"
    # The company's history, not the candidate's.
    r"year track record|\b(we|our (company|firm|team)) (have|has|bring)\b|"
    # Experience offered in place of a degree widens eligibility; it is not a bar.
    r"substitut|in lieu of|in place of (a|the) degree|instead of a degree", re.I)

DEGREE = re.compile(r"\b(bachelor|master|ph\.?d|doctorate|b\.?s\.?|m\.?s\.?|bs/ms|ms/phd|degree)\b", re.I)

# Sentence-level hedges. A requirement stated alongside one of these is not a
# requirement.
PREFERRED_WORDS = re.compile(
    r"preferred|nice[- ]to[- ]have|bonus|\ba plus\b|\bpluses\b|desired|ideal(ly)?|"
    r"would be (great|nice)|stand out|extra credit|good to have|not required|"
    r"is a plus|are a plus|optional", re.I)

# Headings are matched from the start of a short line, so a bullet such as
# "PyTorch a plus" does not open a "preferred" section and silently discount
# every requirement after it.
PREFERRED_HEADING = re.compile(
    r"^\W*(preferred|nice[- ]to[- ]have|bonus|pluses|desired|ideal|additional|"
    r"good to have|extra credit|it'?s? a plus|you('ll)? stand out|we'?d love|"
    r"what would make you stand out)", re.I)
OTHER_HEADING = re.compile(
    r"^\W*(responsibilit|what you('ll)? (do|work on)|the role|about (the|this|us)|"
    r"benefits|compensation|salary|pay (range|transparency)|perks|who we are|"
    r"our (team|mission|culture)|equal opportunity|eeo|why join|location|"
    r"the (team|opportunity|impact)|in this role|day to day|job description|overview)", re.I)
REQUIRED_HEADING = re.compile(
    r"^\W*(minimum|basic|required|requirements|must[- ]have|qualifications|"
    r"what you('ll)? (need|bring)|you (have|bring|are|might be)|who you are|"
    r"about you|what we('re)? look(ing)? for|key qualifications|skills)", re.I)

NEW_GRAD_LANGUAGE = re.compile(
    r"new grad|recent(ly)? graduat|entry[- ]level|early[- ]career|final[- ]year|"
    r"graduating (in|by|between)|university grad|no (prior|previous) experience "
    r"(is )?(required|necessary)|0\s*(-|–|to)\s*[12]\s*" + YEAR_UNIT + r"|"
    r"(class of|graduation (date|in)) ?20(2[5-8])|"
    r"currently (enrolled|pursuing).{0,40}(bachelor|master|ph\.?d)", re.I)


def to_text(description):
    """Turn a description, HTML or plain, into lines of plain text."""
    if not description:
        return ""
    text = str(description)
    # Greenhouse double-escapes its HTML, so unescape until it stops changing.
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = BLOCK_TAGS.sub("\n", text)
    text = TAGS.sub(" ", text)
    text = text.replace("•", "\n").replace(" ", " ")
    text = WORD_NUMBER.sub(lambda m: WORD_NUMBERS[m.group(1).lower()], text)
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _heading(line):
    """The section a line opens, or None when the line is content."""
    if len(line) > 80 or re.search(r"\d\s*" + YEAR_UNIT, line, re.I):
        return None
    explicit = line.endswith(":") or line.isupper()
    if not explicit and (len(line.split()) > 6 or re.search(r"[,.;]", line)):
        return None
    for name, pattern in (("preferred", PREFERRED_HEADING), ("other", OTHER_HEADING),
                          ("required", REQUIRED_HEADING)):
        if pattern.search(line):
            return name
    return "other" if explicit else None


def _mentions(sentence):
    """Year-requirement mentions in one sentence, as (low, high, plus, span)."""
    found, taken = [], []
    for pattern, kind in MENTIONS:
        for m in pattern.finditer(sentence):
            if any(m.start() < end and start < m.end() for start, end in taken):
                continue
            nums = [int(g) for g in m.groups() if g is not None]
            # No individual requirement runs past MAX_PLAUSIBLE_YEARS; "25+ years
            # of experience" in a posting is the company describing itself.
            if not nums or max(nums) > MAX_PLAUSIBLE_YEARS:
                continue
            tail = sentence[m.start():m.end() + 80]
            head = sentence[max(0, m.start() - 40):m.end()]
            if not EXPERIENCE_CONTEXT.search(tail):
                continue
            if NOT_A_REQUIREMENT.search(head + " " + tail[:60]):
                continue
            taken.append((m.start(), m.end()))
            if kind == "ceiling":
                found.append((0, nums[0], False, m.group(0)))
            elif kind == "range":
                low, high = sorted(nums[:2])
                found.append((low, high, False, m.group(0)))
            elif kind == "plus":
                found.append((nums[0], None, True, m.group(0)))
            else:
                found.append((nums[0], nums[0], False, m.group(0)))
    return found


def _acceptable(low, high, plus):
    if low <= ACCEPT_MIN_YEARS:
        return True
    return low == EDGE_YEARS and not plus and high == EDGE_YEARS


def read(description):
    """Return a dict describing the experience a description requires.

    Keys: ``required`` (low, high, plus) or None when nothing is stated;
    ``acceptable`` bool, True when nothing is stated; ``evidence`` the text the
    decision rests on; ``new_grad_language`` whether the text says new grad.
    """
    text = to_text(description)
    result = {"required": None, "acceptable": True, "evidence": None,
              "new_grad_language": bool(NEW_GRAD_LANGUAGE.search(text))}
    if not text:
        return result

    section = "unknown"
    degree_alternatives = []   # degree-conditional: the smallest wins
    independent = []           # stacked requirements: the largest wins
    for line in text.splitlines():
        heading = _heading(line)
        if heading:
            section = heading
            continue
        if section == "preferred":
            continue
        for sentence in re.split(r"(?<=[.;!?])\s+", line):
            mentions = _mentions(sentence)
            if not mentions or PREFERRED_WORDS.search(sentence):
                continue
            smallest = min(mentions, key=lambda x: x[0])
            # "PhD, or Master's and 4+ years": a degree offered as its own
            # alternative, before any number, is a path that needs no years.
            if re.search(r"\b(ph\.?\s?d|doctorate|master'?s?)\b[^0-9]{0,60}?\bor\b", sentence, re.I) and \
                    not re.search(r"\d", sentence.split(" or ", 1)[0]):
                smallest = (0, 0, False, "degree alternative")
            if DEGREE.search(sentence) or len(mentions) > 1 and re.search(r"\bor\b", sentence):
                degree_alternatives.append((smallest, sentence))
            else:
                independent.append((smallest, sentence))

    candidates = []
    if degree_alternatives:
        candidates.append(min(degree_alternatives, key=lambda x: x[0][0]))
    if independent:
        candidates.append(max(independent, key=lambda x: x[0][0]))
    if not candidates:
        return result
    (low, high, plus, _), sentence = max(candidates, key=lambda x: x[0][0])
    result.update(required=(low, high, plus), acceptable=_acceptable(low, high, plus),
                  evidence=sentence[:200])
    return result


def label(required):
    """Human form of a requirement tuple: "2+ yrs", "3-5 yrs", "1 yr"."""
    if not required:
        return None
    low, high, plus = required
    if plus:
        return f"{low}+ yrs"
    if high is not None and high != low:
        return f"{low}-{high} yrs"
    return f"{low} yr" if low == 1 else f"{low} yrs"

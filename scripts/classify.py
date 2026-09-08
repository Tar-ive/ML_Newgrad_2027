"""Decide whether a posting is a genuine ML new-grad role, and bucket it.

The value of this repo over a generic new-grad list is precision: a title
containing "AI" is not an ML role ("AI Business Development Analyst"), and a
title containing "Scientist" is not a new-grad role if it says "Senior".
"""
import re

def _rx(*parts):
    return re.compile("|".join(parts), re.I)

# Unambiguous ML/AI engineering + research titles.
CORE = _rx(
    r"machine learning", r"\bml\b", r"\bmle\b", r"deep learning",
    r"applied scientist", r"research scientist", r"research engineer",
    r"computer vision", r"\bcv engineer", r"\bnlp\b", r"natural language",
    r"\bllm\b", r"large language model", r"foundation model",
    r"generative ai", r"\bgenai\b", r"diffusion",
    r"reinforcement learning", r"\brl\b",
    r"recommendation", r"\brecsys\b", r"search relevance", r"\branking\b",
    r"perception", r"autonomy", r"autonomous (vehicle|driving|systems)",
    r"speech (recognition|synthesis)", r"\basr\b", r"\btts\b",
    r"\bmlops\b", r"ml (infra|infrastructure|platform|systems|compiler|ops)",
    r"\bai\b.{0,20}\b(engineer|scientist|researcher|research)\b",
    r"\b(engineer|scientist|researcher)\b.{0,20}\bai\b",
    r"inference (engine|optimization)", r"model (serving|training|optimization)",
    r"\bgpu\b.{0,15}(kernel|performance|compiler)", r"\bcuda\b", r"\btriton\b",
)

# Real ML work often, but only when the surrounding signal agrees.
SUPPORTING = _rx(
    r"data scientist", r"data science",
    r"quantitative research", r"\bquant research",
    r"algorithm(s)? engineer", r"decision scien",
    r"robotics", r"\bsimulation\b", r"signal processing",
)

# Titles that merely contain AI/ML vocabulary but are not ML engineering jobs.
NEGATIVE = _rx(
    r"business development", r"\bsales\b", r"account (executive|manager)",
    r"marketing", r"recruit", r"customer success", r"solutions consultant",
    r"product manager", r"program manager", r"project manager",
    r"\bpolicy\b", r"\bethics\b", r"\blegal\b", r"communications",
    r"\bwriter\b", r"content", r"\btutor\b", r"\btrainer\b", r"annotat",
    r"development program", r"rotational program", r"leadership program",
    r"\bsupport\b", r"technical account", r"field engineer",
    r"\bteacher\b", r"professor", r"postdoc", r"\bfellowship\b",
    r"\bqa\b", r"quality assurance", r"\bsdet\b",
    r"\bcompliance\b", r"\boperations\b", r"technician", r"\btech\b$",
    r"warehouse", r"maintenance", r"\bdriver\b", r"\bmechatronics\b",
    # Engineering disciplines that are not ML. These matter because product
    # names leak into titles: "Thermal Engineer - AI Satellites" is a thermal
    # job that merely works on a product called AI Satellites.
    r"\bthermal\b", r"propulsion", r"structural", r"avionics", r"\brf\b",
    r"automation and controls", r"mechanical engineer", r"electrical engineer",
    r"manufacturing engineer", r"facilities", r"\btest engineer\b",
    # Front-of-stack roles on an AI product are not ML roles.
    r"front[- ]?end", r"\bfullstack\b", r"\bfull[- ]stack\b", r"\bui engineer\b",
    # "AI Engineer" flavors that are IT, delivery, or tooling work rather than
    # modelling. These come overwhelmingly from enterprises and consultancies
    # integrating an LLM API, not from teams building models.
    r"prompt engineer", r"vibe coder", r"solutions engineer", r"sales engineer",
    r"\bqe\b", r"it infrastructure", r"information technology",
    r"enterprise technology", r"automation engineer", r"\bautomation\b",
    r"application security", r"offensive", r"\bsupply chain\b",
    r"manufacturing", r"\bclinical\b", r"data analytics", r"\bhelpdesk\b",
    r"\bimplementation\b", r"\bintegration engineer\b",
)

# Explicit new-grad markers. Curated trackers do not need these — every role on
# them is already new-grad. Raw ATS feeds do.
NEW_GRAD_SIGNAL = _rx(
    r"new ?grad", r"university grad", r"recent grad", r"college grad",
    r"entry[- ]level", r"early career", r"\bcampus\b", r"\bjunior\b",
    r"grad(uate)? (program|role|hire|position)", r"\bapprentice\b", r"\btrainee\b",
    r"\bassociate\b", r"\bl3\b", r"level 1", r"\bi\b$", r"\b20(2[6-9])\b",
)

# Not a new-grad role.
SENIOR = _rx(
    r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b",
    r"\blead\b", r"\bmanager\b", r"\bdirector\b", r"\bhead of\b",
    r"\bvp\b", r"\bvice president\b", r"\bfellow\b", r"\barchitect\b",
    r"\b(ii|iii|iv|v)\b", r"\b[3-9]\+? years", r"\blevel [3-9]\b", r"\bL[4-9]\b",
    r"\bmid\b(?!west)", r"\bmid[- ]level\b", r"\bavp\b", r"\bexperienced\b",
    r"\bexpert\b", r"\bconsultant\b",
)

# Wet-lab and clinical research titles that share vocabulary with ML research
# ("Research Scientist - Antibody Discovery") but involve no modelling.
DOMAIN_NOISE = _rx(
    r"antibody", r"immuno", r"oncolog", r"vaccine", r"assay", r"in vitro",
    r"cell (culture|biology)", r"molecular biolog", r"\bchemist\b", r"chemistry",
    r"formulation", r"toxicolog", r"pharmacolog", r"clinical (trial|research)",
    r"materials science", r"metallurg", r"food science", r"agronom",
)

# Tokens that prove a title really is computational, overriding DOMAIN_NOISE.
HARD_ML = _rx(
    r"machine learning", r"\bml\b", r"\bai\b", r"deep learning", r"\bllm\b",
    r"computer vision", r"\bnlp\b", r"computational", r"\bmodel(ing|ling)?\b",
    r"algorithm", r"data scien",
)

INTERN = _rx(r"\bintern\b", r"internship", r"\bco-?op\b", r"summer 20\d\d")

# Company buckets. Matched against a normalized company name.
AI_LAB = {
    "openai", "anthropic", "google deepmind", "deepmind", "xai", "mistral ai",
    "mistral", "cohere", "perplexity", "perplexity ai", "scale ai", "ssi",
    "safe superintelligence", "figure", "figure ai", "world labs", "thinking machines",
    "reflection ai", "luma ai", "runway", "runwayml", "midjourney", "suno",
    "elevenlabs", "character ai", "adept", "inflection", "harvey", "cursor",
    "anysphere", "sierra", "glean", "together ai", "fireworks ai", "groq",
    "cerebras", "sambanova", "modal", "weights biases", "huggingface",
    "hugging face", "databricks", "waymo", "cruise", "zoox", "nuro", "wayve",
    "applied intuition", "skild ai", "physical intelligence", "1x", "agility robotics",
}
BIGTECH = {
    "google", "alphabet", "meta", "meta platforms", "facebook", "apple",
    "amazon", "amazon web services", "aws", "microsoft", "netflix", "nvidia",
    "tesla", "tiktok", "bytedance", "linkedin", "uber", "lyft", "airbnb",
    "stripe", "snowflake", "palantir", "salesforce", "adobe", "ibm", "intel",
    "amd", "qualcomm", "oracle", "pinterest", "snap", "snap inc", "reddit",
    "doordash", "instacart", "coinbase", "robinhood", "spotify", "shopify",
    "roblox", "duolingo", "figma", "notion", "openai",
}
QUANT = {
    "jane street", "hudson river trading", "hrt", "citadel", "citadel securities",
    "two sigma", "jump trading", "de shaw", "d e shaw", "the d. e. shaw group",
    "optiver", "imc", "imc trading", "susquehanna", "sig", "radix trading",
    "point72", "millennium", "akuna capital", "drw", "five rings", "old mission",
    "tower research", "virtu", "belvedere trading", "cubist", "qube research",
    "man group", "aqr", "balyasny", "verition", "xtx markets", "headlands",
}

# Titles whose core role is software engineering. "AI" next to one of these
# usually names the product, the team, or the tooling the engineer uses -- not
# the work. "AI-Augmented Software Engineer" writes code with an AI assistant;
# "AI Security Software Engineer" secures an AI product. Neither trains models.
SWE_CORE = _rx(
    r"software (development )?engineer", r"software developer", r"\bsde\b",
    r"\bprogrammer\b", r"web developer", r"application engineer",
    r"\b(backend|back[- ]end|frontend|front[- ]end|fullstack|full[- ]stack)\b",
    r"platform engineer", r"security engineer", r"infrastructure engineer",
    r"devops", r"site reliability", r"\bsre\b", r"systems engineer",
)

# A genuine ML specialization. One of these has to appear alongside a software
# engineering title for the role to count as ML work. Bare "AI" does not
# qualify -- that is the whole point of the distinction.
ML_SPECIALIZATION = _rx(
    r"machine learning", r"\bml\b", r"\bmle\b", r"deep learning", r"neural",
    r"computer vision", r"\bnlp\b", r"natural language", r"\bllm\b",
    r"large language model", r"foundation model", r"generative", r"diffusion",
    r"multimodal", r"multi[- ]modal", r"reinforcement learning", r"\brl\b",
    r"recommendation", r"\brecsys\b", r"\branking\b", r"search relevance",
    r"perception", r"autonomy", r"autonomous", r"speech", r"\basr\b", r"\btts\b",
    r"research (scientist|engineer)", r"applied scien", r"data scien",
    r"model (training|serving|inference|optimization)", r"\binference\b",
    r"\bmlops\b", r"ml (infra|infrastructure|platform|systems|compiler|ops)",
    r"robotics", r"\bcuda\b", r"\btriton\b", r"\bgpu\b",
)


def is_software_engineering(title):
    """True when a title is a software engineering role with no ML specialty."""
    t = title or ""
    return bool(SWE_CORE.search(t)) and not ML_SPECIALIZATION.search(t)


def normalize_company(name):
    n = (name or "").lower().strip()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|the|group|technologies|technology|labs?)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()

def company_tier(name):
    n = normalize_company(name)
    if n in AI_LAB:
        return "ai_lab"
    if n in BIGTECH:
        return "bigtech"
    if n in QUANT:
        return "quant"
    return "other"

def is_intern(title):
    return bool(INTERN.search(title or ""))

def is_new_grad(title):
    """Reject titles that clearly signal experience beyond new grad."""
    return not SENIOR.search(title or "")

def ml_score(title, category=None, company=None):
    """0 = not ML. 2 = core ML. 1 = adjacent, needs corroboration.

    `category` is the source repo's own label (e.g. Simplify's "AI/ML/Data"),
    used to promote supporting titles that would otherwise be ambiguous.
    """
    t = title or ""
    if NEGATIVE.search(t):
        return 0
    if CORE.search(t):
        if DOMAIN_NOISE.search(t) and not HARD_ML.search(t):
            return 0
        return 2
    if SUPPORTING.search(t):
        cat = (category or "").lower()
        if "ai" in cat or "ml" in cat or "machine learning" in cat or "data" in cat:
            return 2
        if company_tier(company) in ("ai_lab", "quant"):
            return 2
        return 1
    return 0

def has_new_grad_signal(title):
    return bool(NEW_GRAD_SIGNAL.search(title or ""))


def classify(title, category=None, company=None, experience=None, strict=False):
    """Return (keep: bool, bucket: str) for a posting.

    `strict` is for raw ATS feeds, which list every role at a company rather
    than a curated new-grad set. There, a role must prove it is entry level:
    either a years-of-experience figure of 2 or less, or an explicit new-grad
    marker in the title. Without that gate a feed of "all jobs at Anthropic"
    would fill the list with senior research roles.

    `experience` is years required, when the source reports it.
    """
    if is_intern(title) or is_software_engineering(title):
        return False, None
    score = ml_score(title, category, company)
    if score < 2 or not is_new_grad(title):
        return False, None
    if strict:
        if experience is not None:
            if experience > 2:
                return False, None
        elif not has_new_grad_signal(title):
            return False, None
    return True, company_tier(company)

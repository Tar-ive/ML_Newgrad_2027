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

def classify(title, category=None, company=None):
    """Return (keep: bool, bucket: str) for a posting."""
    score = ml_score(title, category, company)
    if score < 2 or not is_new_grad(title):
        return False, None
    return True, company_tier(company)

"""Decide whether a posting belongs on this list, and bucket it.

The value of this repo over a generic new-grad list is precision. A title
containing "AI" is not an ML role ("AI Business Development Analyst"); a title
containing "Scientist" is not a new-grad role if it says "Senior"; and a title
containing both can still be a chip job ("System AI Engineer - Display - ASICS
Engineering").

The gate is a WHITELIST of four role families, not a blacklist of noise. A
posting is kept only if it lands in exactly one of:

    ml      Machine learning / AI engineering and research. MLE, applied
            scientist, research scientist, CV, NLP, LLM, RL, recsys, ranking,
            perception, speech, MLOps, ML infra.
    ds      Data science. Data scientist, decision scientist, and (when
            ALLOW_QUANT_RESEARCH is on) quantitative researcher.
    de_ml   Data engineering, but only with an ML specialization in the title.
            A plain "Data Engineer" is not on this list.
    swe_ml  Software engineering, but only with an ML specialization in the
            title, or a description that is unambiguously about ML work.
            A plain "Software Engineer" is not on this list, and neither is
            "AI Security Software Engineer" -- there "AI" names the product.

Everything else is dropped. Three exclusion sets run before the families are
even consulted, because they describe jobs that share ML vocabulary without
being ML jobs: hardware/silicon, wet-lab and physical science, and the
business/ops/annotation functions that surround an AI product.

Level is a separate gate from family: the role must read as new grad or early
career, and any stated experience requirement must be at most MAX_YEARS.
"""
import re

# Early career means new grad through roughly three years. A posting that
# states a higher figure is dropped even when its title looks junior.
MAX_YEARS = 3

# Quantitative research at a trading firm is statistical modelling, and the
# README has a section for it. Flip this off to hold the list to the strict
# ML / DS / DE+ML / SWE+ML reading.
ALLOW_QUANT_RESEARCH = True


def _rx(*parts):
    return re.compile("|".join(parts), re.I)


# ---------------------------------------------------------------------------
# Level 0 exclusions. These run first and are unconditional.
# ---------------------------------------------------------------------------

# Not a full-time new-grad job at all: internships, apprenticeships, the German
# dual-study programs, and the "summer analyst" title banks use for interns.
NOT_NEW_GRAD_ROLE = _rx(
    r"\bintern\b", r"internship", r"\bco-?op\b", r"summer 20\d\d",
    r"summer (analyst|associate|scholar)", r"praktikant", r"werkstudent",
    r"duales studium", r"\bapprentice", r"working student", r"student worker",
    r"\bpart[- ]time\b", r"\bstudent\b", r"\bscholar\b", r"\bphd student\b",
    r"\bfellowship\b", r"\bpostdoc", r"research assistant",
)

# Hardware and silicon. This is the category that prompted the whitelist: chip
# and board work routinely carries "AI" in the title because the silicon is
# aimed at AI workloads, but the job is circuit design, not modelling.
EXCLUDE_HARDWARE = _rx(
    r"\basics?\b", r"\bsoc\b", r"\bvlsi\b", r"\brtl\b", r"verilog", r"vhdl",
    r"\bfpga\b", r"\beda\b", r"\bpcb\b", r"\bsilicon\b", r"semiconductor",
    r"\bwafer\b", r"lithograph", r"\bfoundry\b", r"tape[- ]?out",
    r"physical design", r"design verification", r"\bdft\b", r"analog design",
    r"mixed[- ]signal", r"standard cell", r"place and route", r"\bcircuit",
    r"chip design", r"\bic design\b",
    r"power electronics", r"electrical (hardware|engineer)", r"hardware engineer",
    r"board design", r"\bfirmware\b", r"embedded (hardware|systems?)",
    r"\bmetrolog", r"process integration", r"\bthermal\b",
    r"propulsion", r"structural", r"avionics", r"\brf engineer",
    r"mechanical engineer", r"manufacturing", r"\bmechatronics\b",
    r"environmental engineer", r"sensor (systems?|hardware)", r"antenna",
    r"\boptical engineer", r"\bphotonic", r"\bpower engineer",
)

# Wet lab, clinical, and physical science. These share "Research Scientist" and
# "Associate Scientist" with ML research and share nothing else.
EXCLUDE_DOMAIN = _rx(
    r"antibody", r"immuno", r"oncolog", r"vaccine", r"assay", r"in vitro",
    r"cell (culture|biology|gene)", r"gene therapy", r"stem cell",
    r"molecular biolog", r"\bbiolog", r"lentiviral", r"purification", r"electrophysiolog",
    r"optogenetic", r"two photon", r"\bchemist\b", r"chemistry",
    r"formulation", r"toxicolog", r"pharmacolog", r"clinical (trial|research)",
    r"analytical development", r"real world evidence",
    r"materials (science|research)", r"metallurg", r"\bceramist\b", r"\bceramic",
    r"food science", r"agronom", r"\bgeolog", r"\bveterinar",
)

# Business, operations, delivery, and data-labeling functions. An AI company
# hires all of these; none of them build models.
EXCLUDE_FUNCTION = _rx(
    r"business development", r"\bsales\b", r"account (executive|manager)",
    r"marketing", r"recruit", r"customer success", r"customer insights",
    r"solutions? (consultant|engineer|architect)", r"sales engineer",
    r"product manager", r"program manager", r"project manager",
    r"\bpolicy\b", r"\bethics\b", r"\blegal\b", r"communications",
    r"\bwriter\b", r"\bcontent\b", r"\btutor\b", r"\btrainer\b",
    # Data labeling and teleoperation. "Robotics Data Collection Operator" is
    # a person moving a robot arm, not an engineer.
    r"annotat", r"\blabeler\b", r"data (collection|contributor|operator)",
    r"teleoperat", r"motion capture", r"\bparticipant\b", r"\boperator\b",
    r"\btester\b", r"\bqa\b", r"quality assurance", r"\bsdet\b", r"\bqe\b",
    # Consultancies and enterprise IT wiring an LLM API into a workflow.
    r"forward deployed", r"\bconsult", r"capability center", r"\bpresales\b",
    r"copilot developer", r"process engineer", r"business engineer",
    r"\badoption\b", r"\bgtm\b", r"prompt engineer", r"vibe coder",
    r"it infrastructure", r"information technology", r"enterprise technology",
    r"\bimplementation\b", r"\bintegration engineer\b", r"\bhelpdesk\b",
    r"technical account", r"field engineer", r"\bsupport\b",
    r"developer relations", r"relations developer", r"\bdevrel\b",
    r"\btooling\b", r"program engineer",
    # Programs that rotate through business functions rather than hire for one.
    r"development program", r"rotational program", r"leadership program",
    r"\bcompliance\b", r"\boperations\b", r"technician", r"\btech\b$",
    r"warehouse", r"maintenance", r"\bdriver\b", r"\bfacilities\b",
    r"\bteacher\b", r"professor", r"application security", r"offensive",
    r"\btest engineer\b", r"flight test", r"validation engineer", r"\baudit",
    r"security analy",
    r"\bsupply chain\b", r"\bclinical\b", r"\bnurse\b",
)

# Beyond early career.
SENIOR = _rx(
    r"\bsenior\b", r"\bsr\.?\b", r"\bstaff\b", r"\bprincipal\b",
    r"\blead\b", r"\bmanager\b", r"\bdirector\b", r"\bhead of\b",
    r"\bvp\b", r"\bvice president\b", r"\bfellow\b", r"\barchitect\b",
    r"\b(iii|iv|v|vi)\b", r"\b[4-9]\+? years", r"\b1[0-9]\+? years",
    r"\blevel [3-9]\b", r"\bL[4-9]\b", r"\bmid\b(?!west)", r"\bmid[- ]level\b",
    r"\bavp\b", r"\bexperienced\b", r"\bexpert\b", r"\bconsultant\b",
)

# Explicit new-grad markers, needed by raw ATS feeds (see `strict`).
NEW_GRAD_SIGNAL = _rx(
    r"new ?grad", r"university grad", r"recent grad", r"college grad",
    r"entry[- ]level", r"early career", r"\bcampus\b", r"\bjunior\b", r"\bjr\.?\b",
    r"grad(uate)? (program|role|hire|position)", r"\bgraduate\b", r"\btrainee\b",
    r"\bassociate\b", r"\bl3\b", r"level [12]\b", r"\b(i|1|ii|2)\b$",
    r"\b20(2[6-9])\b", r"\b[0-3]\+? years",
)


# ---------------------------------------------------------------------------
# Level 1: the four role families.
# ---------------------------------------------------------------------------

# Titles that are unambiguously ML on their own.
ML_STRONG = _rx(
    r"machine learning", r"\bml\b", r"\bmle\b", r"deep learning",
    r"applied scien", r"\bnlp\b", r"natural language", r"computer vision",
    r"\bllm\b", r"large language model", r"foundation model", r"multimodal",
    r"multi[- ]modal", r"\bdiffusion\b", r"reinforcement learning", r"\brl\b",
    r"recommendation", r"\brecsys\b", r"search relevance", r"\branking\b",
    r"\bperception\b", r"\bautonomy\b", r"autonomous (vehicle|driving|systems)",
    r"speech (recognition|synthesis)", r"\basr\b", r"\btts\b", r"\bmlops\b",
    r"ml (infra|infrastructure|platform|systems?|compiler|ops|engineer)",
    r"inference (engine|optimization|system)", r"model (serving|training|optimization)",
    r"post[- ]?training", r"world model", r"\bneural\b", r"\bcuda\b", r"\btriton\b",
    r"\bgpu\b.{0,15}(kernel|performance|compiler)",
    r"\bai (scientist|researcher|research)\b",
    r"artificial intelligence (scientist|researcher|research)",
)

# ML vocabulary that is real but not self-sufficient: it names a field an
# employer might merely be adjacent to. Kept only with corroboration.
ML_WEAK = _rx(
    r"\b(ai|genai)\b.{0,25}\b(engineer|scientist|researcher|research)\b",
    r"\b(engineer|scientist|researcher)\b.{0,25}\b(ai|genai)\b",
    r"(artificial intelligence|generative ai).{0,25}\b(engineer|scientist|research)",
    r"algorithm(s)? engineer", r"\bsimulation\b", r"signal processing",
    r"\brobotic", r"\binference\b",
)

# A generic research title. "Research Scientist" is ML at OpenAI and food
# chemistry at a dairy company, so it needs corroboration too.
RESEARCH_TITLE = _rx(r"research (scientist|engineer|associate)", r"\bresearcher\b")

DS_TITLE = _rx(
    r"data scien", r"decision scien", r"analytics scientist",
    r"statistic(ian|al modeling)",
)
QUANT_TITLE = _rx(r"quantitative research", r"\bquant research")

DE_TITLE = _rx(r"data engineer", r"\bdata platform\b", r"\banalytics engineer\b")

SWE_TITLE = _rx(
    r"software (development )?engineer", r"software developer", r"\bsde\b",
    r"\bsw engineer\b", r"\bsw dev", r"\bsoftware engineering\b",
    r"\bprogrammer\b", r"web developer", r"application engineer",
    r"\b(backend|back[- ]end|frontend|front[- ]end|fullstack|full[- ]stack)\b",
    r"platform engineer", r"security engineer", r"infrastructure engineer",
    r"devops", r"site reliability", r"\bsre\b", r"systems? engineer",
)

# The specialization that has to sit next to a DE or SWE title for the role to
# count. Bare "AI" is deliberately absent: that is the whole distinction.
ML_SPECIALIZATION = _rx(
    r"machine learning", r"\bml\b", r"\bmle\b", r"deep learning", r"\bneural\b",
    r"computer vision", r"\bnlp\b", r"natural language", r"\bllm\b",
    r"large language model", r"foundation model", r"generative", r"diffusion",
    r"multimodal", r"multi[- ]modal", r"reinforcement learning", r"\brl\b",
    r"recommendation", r"\brecsys\b", r"\branking\b", r"search relevance",
    r"\bperception\b", r"\bautonomy\b", r"autonomous", r"speech", r"\basr\b",
    r"\btts\b", r"applied scien", r"data scien", r"\bmlops\b",
    r"model (training|serving|inference|optimization)", r"post[- ]?training",
    r"\binference\b", r"ml (infra|infrastructure|platform|systems?|compiler|ops)",
    r"\bcuda\b", r"\btriton\b", r"world model",
)

# Description evidence, used only to promote a SWE title. Two distinct hits are
# required: one passing mention of "machine learning" in a boilerplate company
# blurb is not a job description about ML.
ML_IN_DESCRIPTION = _rx(
    r"machine learning", r"deep learning", r"\bneural network",
    r"\bmodel(s|ing|ling)?\b.{0,20}\b(train|training|deploy|inference|serving)",
    r"train(ing)? (a |the )?model", r"computer vision", r"\bnlp\b",
    r"large language model", r"\bllm(s)?\b", r"\bpytorch\b", r"tensorflow",
    r"\bml (pipeline|model|system|infrastructure|platform)",
    r"reinforcement learning", r"recommendation system", r"ranking model",
    r"feature engineering", r"model evaluation",
)
DESCRIPTION_HITS_REQUIRED = 2

# Tokens that prove a research or science title really is computational,
# overriding EXCLUDE_DOMAIN. "Computational Genomics Research Scientist" is a
# modelling job; "Stem Cell Research Scientist" is not.
COMPUTATIONAL = _rx(
    r"machine learning", r"\bml\b", r"\bai\b", r"deep learning", r"\bllm\b",
    r"computer vision", r"\bnlp\b", r"computational", r"\bmodel(ing|ling)\b",
    r"\balgorithm", r"data scien",
)

# Robotics is mechanical work as often as it is learning work, so it counts
# only alongside something that is unmistakably about models.
ROBOTICS_ML = _rx(
    r"machine learning", r"\bml\b", r"deep learning", r"\bai\b",
    r"perception", r"computer vision", r"\bvision\b", r"autonomy", r"autonomous",
    r"foundation model", r"reinforcement learning", r"manipulation",
    r"\bpolicy learning\b", r"research (scientist|engineer)",
)


# ---------------------------------------------------------------------------
# Company buckets. Matched against a normalized company name.
# ---------------------------------------------------------------------------
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
    "decagon", "factory", "exa", "baseten", "contextual ai", "sakana ai",
    "liquid ai", "essential ai", "magic", "codeium", "windsurf", "poolside",
    "imbue", "normal computing", "extropic", "goodfire", "eleuther", "luma",
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
    "renaissance", "renaissance technologies", "voleon", "quantlab", "tgs",
    "trexquant", "engineers gate", "flow traders", "dv trading", "squarepoint",
    "wolverine trading", "peak6", "group one trading", "arrowstreet capital",
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


# ---------------------------------------------------------------------------
# Predicates.
# ---------------------------------------------------------------------------

def is_intern(title):
    return bool(NOT_NEW_GRAD_ROLE.search(title or ""))


def is_new_grad(title):
    """Reject titles that clearly signal experience beyond early career."""
    return not SENIOR.search(title or "")


def has_new_grad_signal(title):
    return bool(NEW_GRAD_SIGNAL.search(title or ""))


def is_excluded(title):
    """True when a title is disqualified regardless of what family it looks like."""
    t = title or ""
    if EXCLUDE_HARDWARE.search(t) or EXCLUDE_FUNCTION.search(t):
        return True
    # Wet-lab vocabulary only disqualifies a title that has no computational
    # counterweight, so "Computational Genomics Research Scientist" survives.
    return bool(EXCLUDE_DOMAIN.search(t)) and not COMPUTATIONAL.search(t)


def is_software_engineering(title):
    """True when a title is a software engineering role with no ML specialty.

    Kept as a public name because the README and the tests both refer to this
    distinction: "AI Security Software Engineer" secures an AI product, and
    "AI-Augmented Software Engineer" writes code with an AI assistant. Neither
    trains a model.
    """
    t = title or ""
    return bool(SWE_TITLE.search(t)) and not ML_SPECIALIZATION.search(t)


def description_is_ml(description):
    """True when a job description is unmistakably about ML work."""
    if not description:
        return False
    hits = {m.group(0).lower() for m in ML_IN_DESCRIPTION.finditer(description)}
    return len(hits) >= DESCRIPTION_HITS_REQUIRED


def _corroborated(title, category, company, description):
    """Outside evidence that a weak ML title really is an ML role."""
    cat = (category or "").lower()
    if "ml" in cat or "machine learning" in cat or "ai/" in cat or cat.startswith("ai"):
        return True
    if company_tier(company) in ("ai_lab", "quant", "bigtech"):
        return True
    return description_is_ml(description)


def role_family(title, category=None, company=None, description=None):
    """Return "ml", "ds", "de_ml", "swe_ml", "quant", or None.

    None means the posting does not belong on this list. The families are
    checked in order of how much evidence they demand, and a title that lands
    in a software or data engineering family is held to the extra requirement
    that an ML specialization appear alongside the engineering title.
    """
    t = title or ""
    if not t or is_excluded(t):
        return None

    # Data science first: "Data Scientist" is its own family and never needs an
    # ML qualifier.
    if DS_TITLE.search(t):
        return "ds"
    if QUANT_TITLE.search(t):
        return "quant" if ALLOW_QUANT_RESEARCH else None

    # Engineering titles. These are the two families that require a
    # specialization, so they are checked before the general ML match -- that
    # is what keeps "Backend Engineer, AI Platform" off the list.
    if DE_TITLE.search(t):
        return "de_ml" if ML_SPECIALIZATION.search(t) else None
    if SWE_TITLE.search(t):
        if ML_SPECIALIZATION.search(t):
            return "swe_ml"
        return "swe_ml" if description_is_ml(description) else None

    # Robotics only counts with a learning or perception component.
    if re.search(r"\brobotic", t, re.I) and not ROBOTICS_ML.search(t):
        return None

    if ML_STRONG.search(t):
        return "ml"

    if RESEARCH_TITLE.search(t) or ML_WEAK.search(t):
        if ML_SPECIALIZATION.search(t):
            return "ml"
        return "ml" if _corroborated(t, category, company, description) else None

    return None


def classify(title, category=None, company=None, experience=None, strict=False,
             description=None):
    """Return (keep: bool, bucket: str) for a posting.

    `strict` is for raw ATS feeds, which list every role at a company rather
    than a curated new-grad set. There, a role must prove it is entry level:
    a stated experience requirement within MAX_YEARS, or an explicit new-grad
    marker in the title. Without that gate a feed of "all jobs at Anthropic"
    would fill the list with senior research roles.

    `experience` is years required when the source reports it, and is enforced
    for every source -- a curated tracker still occasionally carries a role
    asking for five years.
    """
    if is_intern(title) or not is_new_grad(title):
        return False, None
    if experience is not None and experience > MAX_YEARS:
        return False, None
    if role_family(title, category, company, description) is None:
        return False, None
    if strict and experience is None and not has_new_grad_signal(title):
        return False, None
    return True, company_tier(company)

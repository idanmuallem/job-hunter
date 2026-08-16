"""
Shared, non-sensitive pipeline settings — job keywords, title/location
filters, and the Israeli-company ATS crawl list. Deliberately split out
of config.py (which is git-ignored) because none of this is personal or
secret: it's application configuration that should just live in the repo
like any other code, get committed normally, and never need to be pasted
into a GitHub secret. config.py does `from config_public import *` so
every name here is still reachable as config.WHATEVER everywhere else in
the codebase — no other file needs to change when this one does.
"""

from __future__ import annotations

# ─── Job Search Keywords ────────────────────────────────────────
# Searched across ALL companies globally via JSearch — no pre-configured
# company list (location filtering is handled separately, below).
JOB_KEYWORDS = [
    "Software Developer",
    "Backend Developer",
    "Backend Engineer",
    "Data Engineer",
    "Python Developer",
    "Cloud Engineer",
    "Platform Engineer",
]

# ─── Title filter ──────────────────────────────────────────────────
# Applied to the job TITLE only (not description — description text is
# too noisy, e.g. "reports to the Engineering Lead" in an otherwise-
# junior posting). A job is rejected if its title contains any keyword
# below. Checked by job_scraper._passes_title_filter().
EXCLUDED_TITLE_KEYWORDS = [
    # QA / Testing
    "qa", "quality assurance", "test engineer", "sdet",
    "automation tester", "testing engineer",

    # DevOps / SRE — deliberately does NOT include a bare "infrastructure"
    # keyword, so "Platform Engineer" and "Systems Engineer" stay in scope.
    "devops", "sre", "site reliability", "infrastructure engineer",

    # Support / Solutions
    "support engineer", "solutions engineer", "solutions architect",
    "technical support",

    # Sales / Pre-Sales
    "sales engineer", "pre-sales", "customer success",

    # Technical Writer / Scrum Master
    "technical writer", "scrum master", "agile coach",

    # Other non-dev roles that might slip through keyword matching.
    # Only the specific phrases below — no bare "analyst", so "Data
    # Engineer" stays in scope while "Data Analyst" doesn't. "hr " has a
    # trailing space (matching the existing HR_TITLES convention below)
    # so it doesn't false-positive on some unrelated word containing "hr".
    "business analyst", "data analyst", "recruiter", "hr ",
    "marketing", "product designer", "ui/ux designer",

    # Seniority — junior + mid only, block everything above.
    # "sr " (trailing space) and "sr." catch "Sr. Developer" / "Sr Dev"
    # without catching "Israel" — the "sr" inside "israel" is always
    # followed by "a", never a space or period.
    "senior", "sr.", "sr ", "staff", "principal", "director",
    "vp ", "vice president", "head of", "lead", "architect",
    "chief", "cto", "cio",
]

# ─── Location filter: is the POSITION in Israel? ─────────────────
# Applied to every source (JSearch, free job boards, and the Israeli ATS
# crawl below) — company nationality doesn't guarantee the job itself is
# based in Israel (e.g. Taboola/JFrog post plenty of US/EU roles too), so
# this checks the job's own location text instead. "Loose" mode: a job
# passes if its location explicitly names Israel, OR is generic/open
# remote with no other region restriction. See
# job_scraper._is_israel_relevant() for the matching logic.
ISRAEL_LOCATION_KEYWORDS = [
    "israel", "tel aviv", "tel-aviv", "jerusalem", "haifa", "herzliya",
    "ramat gan", "petah tikva", "petach tikva", "beer sheva", "beersheba",
    "rehovot", "netanya", "raanana", "ra'anana", "kfar saba", "yokneam",
    "caesarea", "ashdod", "holon", "bnei brak", "modiin",
    "rishon lezion", "rishon le zion",
]
# Generic/open remote signals — pass through when no restriction is found.
REMOTE_OPEN_KEYWORDS = [
    "remote", "anywhere", "worldwide", "global", "location independent",
    "work from anywhere",
]
# If any of these appear, a "remote" listing is restricted to somewhere
# that isn't Israel — reject even though it contains "remote".
REMOTE_RESTRICTION_KEYWORDS = [
    "us only", "usa only", "u.s. only", "us-only", "united states only",
    "uk only", "u.k. only", "eu only", "europe only", "canada only",
    "latam only", "apac only", "emea only", "na only", "north america only",
    "must be located in the us", "must reside in the us",
    "us based", "us-based", "us citizens", "us work authorization",
    "no visa sponsorship",
]

# ─── ATS crawl (free, unlimited — see job_scraper.py) ──────────────
# Hand-curated companies known to be on Greenhouse or Lever, crawled
# directly via their own public job-board APIs. This never touches the
# JSearch budget. Every slug below was verified live against the real
# Greenhouse/Lever APIs. To add more: try
#   https://boards-api.greenhouse.io/v1/boards/<slug>/jobs
#   https://api.lever.co/v0/postings/<slug>?mode=json
# A 404 means wrong slug or not on that ATS — just skip it, nothing breaks.
# (Comeet is common among Israeli companies too, but its API needs a
# per-company token you can only get from that company's careers-page
# source — not a guessable slug — so it isn't included here yet.)
#
# NOT restricted to Israeli-founded companies — the position's location
# matters, not the company's nationality (see _is_israel_relevant in
# job_scraper.py, applied to every job from every company here). Several
# entries below are global companies with real Israel R&D/offices; their
# global job boards get pulled in full and then filtered down to just
# Israel/open-remote postings downstream, same as everything else.
ISRAELI_ATS_COMPANIES = [
    # Israeli-founded
    {"name": "AppsFlyer", "ats_platform": "greenhouse", "ats_slug": "appsflyer"},
    {"name": "JFrog", "ats_platform": "greenhouse", "ats_slug": "jfrog"},
    {"name": "Forter", "ats_platform": "greenhouse", "ats_slug": "forter"},
    {"name": "Cybereason", "ats_platform": "greenhouse", "ats_slug": "cybereason"},
    {"name": "Orca Security", "ats_platform": "greenhouse", "ats_slug": "orcasecurity"},
    {"name": "Axonius", "ats_platform": "greenhouse", "ats_slug": "axonius"},
    {"name": "Yotpo", "ats_platform": "greenhouse", "ats_slug": "yotpo"},
    {"name": "Melio", "ats_platform": "greenhouse", "ats_slug": "melio"},
    {"name": "Riskified", "ats_platform": "greenhouse", "ats_slug": "riskified"},
    {"name": "SimilarWeb", "ats_platform": "greenhouse", "ats_slug": "similarweb"},
    {"name": "Lightricks", "ats_platform": "greenhouse", "ats_slug": "lightricks"},
    {"name": "Gong", "ats_platform": "greenhouse", "ats_slug": "gongio"},
    {"name": "Taboola", "ats_platform": "greenhouse", "ats_slug": "taboola"},
    {"name": "Bringg", "ats_platform": "greenhouse", "ats_slug": "bringg"},
    {"name": "Cato Networks", "ats_platform": "greenhouse", "ats_slug": "catonetworks"},
    {"name": "Transmit Security", "ats_platform": "greenhouse", "ats_slug": "transmitsecurity"},
    {"name": "Sisense", "ats_platform": "greenhouse", "ats_slug": "sisense"},
    {"name": "Augury", "ats_platform": "greenhouse", "ats_slug": "augury"},
    {"name": "Fireblocks", "ats_platform": "greenhouse", "ats_slug": "fireblocks"},
    {"name": "Cymulate", "ats_platform": "greenhouse", "ats_slug": "cymulate"},
    {"name": "WalkMe", "ats_platform": "lever", "ats_slug": "walkme"},
    {"name": "Salt Security", "ats_platform": "greenhouse", "ats_slug": "saltsecurity"},
    {"name": "Apiiro", "ats_platform": "greenhouse", "ats_slug": "apiiro"},
    {"name": "Pagaya", "ats_platform": "greenhouse", "ats_slug": "pagaya"},
    {"name": "Payoneer", "ats_platform": "greenhouse", "ats_slug": "payoneer"},
    {"name": "Cloudinary", "ats_platform": "lever", "ats_slug": "cloudinary"},
    {"name": "Via", "ats_platform": "greenhouse", "ats_slug": "via"},
    {"name": "Innovid", "ats_platform": "greenhouse", "ats_slug": "innovid"},
    {"name": "Connecteam", "ats_platform": "greenhouse", "ats_slug": "connecteam"},
    {"name": "Duda", "ats_platform": "greenhouse", "ats_slug": "duda"},
    {"name": "NICE", "ats_platform": "greenhouse", "ats_slug": "nice"},
    {"name": "MyHeritage", "ats_platform": "greenhouse", "ats_slug": "myheritage"},
    {"name": "Sweet Security", "ats_platform": "greenhouse", "ats_slug": "sweetsecurity"},

    # Global companies with real Israel R&D/offices — global board pulled
    # in full, filtered down to Israel/open-remote postings downstream.
    {"name": "Elastic", "ats_platform": "greenhouse", "ats_slug": "elastic"},
    {"name": "MongoDB", "ats_platform": "greenhouse", "ats_slug": "mongodb"},
    {"name": "Twilio", "ats_platform": "greenhouse", "ats_slug": "twilio"},
    {"name": "Datadog", "ats_platform": "greenhouse", "ats_slug": "datadog"},
    {"name": "Cloudflare", "ats_platform": "greenhouse", "ats_slug": "cloudflare"},
    {"name": "GitLab", "ats_platform": "greenhouse", "ats_slug": "gitlab"},
    {"name": "Scopely", "ats_platform": "greenhouse", "ats_slug": "scopely"},
    {"name": "Speechify", "ats_platform": "greenhouse", "ats_slug": "speechify"},
    {"name": "Veeva Systems", "ats_platform": "lever", "ats_slug": "veeva"},
]

# ─── Contact Discovery ───────────────────────────────────────────
# Title substrings used to classify Apollo results into Priority C/D
# (also sent to Apollo as the person_titles filter).
ENGINEERING_TITLES = [
    "engineering manager", "tech lead", "team lead",
    "data engineering manager", "principal engineer",
    "staff engineer", "director of engineering",
    "vp engineering", "head of engineering",
]
HR_TITLES = [
    "recruiter", "talent acquisition", "hr ",
    "human resources", "people operations",
    "technical recruiter", "sourcer",
]

# ─── Contact Priority Hierarchy ──────────────────────────────────
PRIORITY_LABELS = {
    "A": "1st-degree connection",
    "B": "University alumni",
    "C": "Engineering / Tech Lead / Manager",
    "D": "HR / Technical Recruiter",
}

# ─── API usage budget (hard caps — never exceeded, regardless of plan) ──
# JSearch's free tier caps out at 200 requests/month; only one keyword is
# queried per day (see job_scraper._keywords_for_today), so this cap is a
# backstop, not the primary control. Apollo's cap is a conservative
# safety margin in case its free-tier restriction ever lifts.
MAX_MONTHLY_JSEARCH_CALLS = 180
MAX_MONTHLY_APOLLO_CALLS = 70

# ─── Pipeline Settings ────────────────────────────────────────────
MESSAGE_CHAR_LIMIT = 300

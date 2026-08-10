"""
Configuration template for the Job Hunter Agent.

Copy this file to `config.py` and fill in your own profile info.
`config.py` is git-ignored so your personal details never get committed.
Secrets (Telegram, RapidAPI/JSearch, Apollo) are loaded separately from a
`.env` file — see `.env.example`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# ─── Your Profile ───────────────────────────────────────────────
PROFILE = {
    "name": "Your Name",
    # Short form used verbatim inside the outreach message template.
    "degree": "3rd-year CS",
    "university": "Your University",
    # A second school to also count as "alumni" (e.g. exchange program).
    "alt_university": "Your Alt University",
}

# ─── Job Search Keywords ────────────────────────────────────────
# Searched across ALL companies globally via JSearch — no pre-configured
# company list and no location filtering (all locations are relevant).
JOB_KEYWORDS = [
    "Software Developer",
    "Backend Developer",
    "Data Engineer",
    "Python Developer",
    "Cloud Engineer",
]

# ─── LinkedIn Connections (Priority A, free, manual export) ──────
# Export from: LinkedIn → Settings & Privacy → Data privacy →
# Get a copy of your data → Connections.
LINKEDIN_CSV_PATH = os.getenv("LINKEDIN_CSV_PATH", "Connections.csv")

# ─── Secrets (loaded from .env — see .env.example) ───────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

# ─── Local persistence ────────────────────────────────────────────
SEEN_JOBS_FILE = BASE_DIR / "seen_jobs.json"
API_USAGE_FILE = BASE_DIR / "api_usage.json"

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


def check_keys() -> list[str]:
    """Return human-readable warnings for missing/optional configuration."""
    warnings: list[str] = []

    if not TELEGRAM_BOT_TOKEN:
        warnings.append(
            "TELEGRAM_BOT_TOKEN is not set — Telegram alerts are disabled "
            "(falling back to console output). Set it in .env to enable."
        )
    if not TELEGRAM_CHAT_ID:
        warnings.append(
            "TELEGRAM_CHAT_ID is not set — Telegram alerts are disabled "
            "(falling back to console output). Set it in .env to enable."
        )
    if not RAPIDAPI_KEY:
        warnings.append(
            "RAPIDAPI_KEY is not set — job search is disabled; use --mock "
            "to test with sample data, or set it in .env to enable JSearch."
        )
    if not APOLLO_API_KEY:
        warnings.append(
            "APOLLO_API_KEY is not set — Priority C/D contact auto-discovery "
            "via Apollo is disabled; only your LinkedIn CSV will be used."
        )
    if not Path(LINKEDIN_CSV_PATH).exists():
        warnings.append(
            f"{LINKEDIN_CSV_PATH} not found — no Priority A contacts "
            "available. Export your connections from LinkedIn (Settings & "
            "Privacy → Data privacy → Get a copy of your data → "
            f"Connections) and save the CSV as {LINKEDIN_CSV_PATH}."
        )

    return warnings

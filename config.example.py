"""
Configuration template for the Job Hunter Agent.

Copy this file to `config.py` and fill in your own profile info.
`config.py` is git-ignored so your personal details never get committed.
Secrets (Telegram, Apollo) are loaded separately from a `.env` file —
see `.env.example`.
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
    "degree": "B.Sc. Computer Science (3rd year)",
    # Short form used inside the outreach message template.
    "degree_short": "3rd-year CS",
    "university": "Your University",
    # A second school to also count as "alumni" (e.g. exchange program).
    "alt_university": "Your Alt University",
    "skills": ["Python", "Java", "AWS", "Azure", "Backend Development", "Data Engineering"],
    "target_roles": ["Software Developer", "Backend Engineer", "Data Engineer"],
    "linkedin_url": "https://linkedin.com/in/your-profile",
}

# ─── Job Search Keywords ────────────────────────────────────────
JOB_KEYWORDS = [
    "Software Developer",
    "Backend Engineer",
    "Backend Developer",
    "Data Engineer",
    "Python Developer",
    "Cloud Engineer",
    "Platform Engineer",
]

# ─── Target Locations (for filtering) ───────────────────────────
TARGET_LOCATIONS = ["Israel", "Remote", "Tel Aviv", "Beer Sheva", "Haifa"]

# ─── Free Job Sources ────────────────────────────────────────────
# Greenhouse board slugs to poll — no API key needed. Find a company's
# slug from its careers page URL: boards.greenhouse.io/<slug>
GREENHOUSE_COMPANY_SLUGS: list[str] = [
    # "stripe",
    # "gitlab",
]

# Plain RSS/Atom job feed URLs, if any of your target companies publish one.
RSS_FEED_URLS: list[str] = []

# ─── Secrets (loaded from .env — see .env.example) ───────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

# ─── Contact Discovery ───────────────────────────────────────────
KNOWN_CONNECTIONS_FILE = BASE_DIR / "known_connections.json"

# Title substrings used to classify Apollo results into Priority C/D.
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

# ─── Pipeline Settings ────────────────────────────────────────────
MAX_RESULTS_PER_COMPANY = 20
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
    if not APOLLO_API_KEY:
        warnings.append(
            "APOLLO_API_KEY is not set — Priority C/D contact auto-discovery "
            "via Apollo is disabled; only known_connections.json will be used."
        )
    if not KNOWN_CONNECTIONS_FILE.exists():
        warnings.append(
            f"{KNOWN_CONNECTIONS_FILE.name} not found — no manual contacts "
            "available (Priority A/B). Copy known_connections.example.json "
            "to get started."
        )
    if not GREENHOUSE_COMPANY_SLUGS and not RSS_FEED_URLS:
        warnings.append(
            "No GREENHOUSE_COMPANY_SLUGS or RSS_FEED_URLS configured — "
            "the scraper will run in mock/demo mode with sample jobs only."
        )

    return warnings

"""
Configuration template for the Job Hunter Agent.

Copy this file to `config.py` and fill in your own profile info.
`config.py` is git-ignored so your personal details never get committed.
Everything that ISN'T personal/secret (job keywords, filters, the
company list) lives in config_public.py instead, which IS committed —
copying this template pulls those in automatically via the import
below, so you don't need to duplicate them. Secrets (Telegram,
RapidAPI/JSearch, Apollo) are loaded separately from a `.env` file —
see `.env.example`.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from config_public import *  # noqa: F401,F403 — shared, non-sensitive settings

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
# Lives in state/ (tracked in git, unlike most local files) so a daily
# GitHub Actions run — which starts from a fresh checkout every time —
# can commit updates back and carry dedup/budget state across runs.
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)  # self-healing if ever missing
SEEN_JOBS_FILE = STATE_DIR / "seen_jobs.json"
API_USAGE_FILE = STATE_DIR / "api_usage.json"
OUTREACH_LOG_FILE = STATE_DIR / "outreach_log.jsonl"


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

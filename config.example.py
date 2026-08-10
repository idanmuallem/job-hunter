"""
Configuration template for the Autonomous Job Hunter Agent.

Copy this file to `config.py` and fill in your own values.
`config.py` is git-ignored so your personal info and API keys never
get committed.
"""

import os

# ─── Your Profile ───────────────────────────────────────────────
PROFILE = {
    "name": "Your Name",
    "university": "Your University",
    "alt_university": "Your Alt University",
    "degree": "Your Degree",
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

# ─── API Keys (replace with real values or set as env vars) ──────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")
PROXYCURL_API_KEY = os.getenv("PROXYCURL_API_KEY", "PROXYCURL_PLACEHOLDER")

# ─── Contact Priority Hierarchy ─────────────────────────────────
PRIORITY_LABELS = {
    "A": "1st-degree connection",
    "B": "University alumni",
    "C": "Engineering / Tech Lead / Manager",
    "D": "HR / Technical Recruiter",
}

# ─── Pipeline Settings ──────────────────────────────────────────
MAX_RESULTS_PER_COMPANY = 20
MESSAGE_CHAR_LIMIT = 300
POLL_INTERVAL_MINUTES = 30

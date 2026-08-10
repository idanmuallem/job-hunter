"""
Module 4: Alert System (Human-in-the-Loop)
Sends a single Telegram message per job with up to 3 ranked contacts,
each with their own personalized LinkedIn message ready to copy-paste.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


@dataclass
class OutreachPackage:
    """One contact + generated message pair."""
    rank: int
    contact_name: str
    contact_role: str
    contact_linkedin: str
    priority_label: str
    message: str
    char_count: int


@dataclass
class JobAlert:
    """A full alert for one job posting, containing up to 3 contacts."""
    company: str
    job_title: str
    job_url: str
    posted_date: Optional[str]
    contacts: list[OutreachPackage]

    @property
    def is_valid(self) -> bool:
        return len(self.contacts) > 0


class AlertChannel(ABC):
    """Base class for alert delivery channels."""

    @abstractmethod
    def send(self, alert: JobAlert) -> bool:
        """Send the job alert. Returns True on success."""
        ...


class TelegramAlert(AlertChannel):
    """Sends one formatted Telegram message per job with all 3 contacts."""

    RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ):
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send(self, alert: JobAlert) -> bool:
        # Build the header
        lines = [
            f"🎯 *NEW JOB MATCH*",
            f"",
            f"*{alert.company}* — {alert.job_title}",
            f"📅 Posted: {alert.posted_date or 'N/A'}",
            f"🔗 [Open Job Posting]({alert.job_url})",
            f"",
            f"━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Build each contact block
        for pkg in alert.contacts:
            emoji = self.RANK_EMOJI.get(pkg.rank, "▪️")
            lines += [
                f"",
                f"{emoji} *Option {pkg.rank}: {pkg.contact_name}*",
                f"   Role: {pkg.contact_role}",
                f"   Why: {pkg.priority_label}",
                f"   🔗 [LinkedIn Profile]({pkg.contact_linkedin})",
                f"",
                f"   📋 Message ({pkg.char_count} chars):",
                f"   `{pkg.message}`",
                f"",
                f"━━━━━━━━━━━━━━━━━━━━━",
            ]

        lines += [
            f"",
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')} · Job Hunter Agent",
        ]

        text = "\n".join(lines)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        if not self.bot_token or not self.chat_id:
            logger.warning(
                "Telegram not configured (missing bot token/chat id) — skipping alert."
            )
            return False

        try:
            resp = requests.post(self.api_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Telegram alert sent for %s at %s", alert.job_title, alert.company)
            return True
        except requests.exceptions.RequestException as e:
            # Never let a failed notification crash the whole pipeline run.
            logger.error("Telegram alert failed: %s", e)
            return False


class ConsoleAlert(AlertChannel):
    """Prints alerts to stdout — useful for testing."""

    RANK_LABEL = {1: "★ BEST", 2: "★★ 2ND", 3: "★★★ 3RD"}

    def send(self, alert: JobAlert) -> bool:
        sep = "=" * 60
        thin = "─" * 60

        print(f"\n{sep}")
        print(f"  🎯  JOB MATCH — {alert.company}")
        print(f"  Role: {alert.job_title}")
        print(f"  URL:  {alert.job_url}")
        print(sep)

        for pkg in alert.contacts:
            label = self.RANK_LABEL.get(pkg.rank, f"#{pkg.rank}")
            print(f"\n  {label}: {pkg.contact_name}")
            print(f"  Role:     {pkg.contact_role}")
            print(f"  Why:      {pkg.priority_label}")
            print(f"  LinkedIn: {pkg.contact_linkedin}")
            print(f"  📋 MESSAGE ({pkg.char_count} chars):")
            print(f"  {pkg.message}")
            print(f"  {thin}")

        print()
        return True


class JsonLogAlert(AlertChannel):
    """Appends alerts as JSON lines for record-keeping."""

    def __init__(self, path: str = "outreach_log.jsonl"):
        self.path = Path(path)

    def send(self, alert: JobAlert) -> bool:
        record = {
            "timestamp": datetime.now().isoformat(),
            "company": alert.company,
            "job_title": alert.job_title,
            "job_url": alert.job_url,
            "contacts": [
                {
                    "rank": pkg.rank,
                    "name": pkg.contact_name,
                    "role": pkg.contact_role,
                    "linkedin": pkg.contact_linkedin,
                    "priority": pkg.priority_label,
                    "message": pkg.message,
                    "char_count": pkg.char_count,
                }
                for pkg in alert.contacts
            ],
        }
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info("Logged outreach to %s", self.path)
            return True
        except Exception as e:
            logger.error("JSON log failed: %s", e)
            return False


class AlertDispatcher:
    """Dispatches job alerts to one or more channels."""

    def __init__(self, channels: list[AlertChannel] | None = None):
        self.channels = channels or [ConsoleAlert(), JsonLogAlert()]

    def dispatch(self, alert: JobAlert) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for channel in self.channels:
            name = channel.__class__.__name__
            results[name] = channel.send(alert)
        return results

"""
Module 1: Job Scraping / Trigger
Discovers new job postings by keyword, searching ALL companies globally
via JSearch (free tier on RapidAPI, indexes LinkedIn/Indeed/Glassdoor/etc
through Google Jobs) — no pre-configured company list, no location filter.

Seen jobs are persisted to seen_jobs.json so re-running the pipeline
doesn't re-alert on the same posting across days. A small hardcoded mock
job list is available via --mock for offline testing.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

import config
from modules import usage_tracker

logger = logging.getLogger(__name__)

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_HOST = "jsearch.p.rapidapi.com"
REQUEST_TIMEOUT = 15


@dataclass
class JobPosting:
    """Represents a single discovered job posting."""
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    posted_date: Optional[str] = None
    source: str = "mock"
    uid: str = field(default="", init=False)

    def __post_init__(self):
        raw = f"{self.company}|{self.title}|{self.url}"
        self.uid = hashlib.sha256(raw.encode()).hexdigest()[:12]

    def matches_keywords(self, keywords: list[str]) -> bool:
        """Check if the job title or description contains any target keyword."""
        text = f"{self.title} {self.description}".lower()
        return any(kw.lower() in text for kw in keywords)


class JobScraper:
    """
    Searches ALL companies by keyword via JSearch — the scraper never
    iterates over a pre-configured company list. Falls back to a small
    hardcoded mock list when `use_mock=True` (--mock flag), for testing
    without burning JSearch's free-tier request budget.
    """

    def __init__(self, keywords: list[str], use_mock: bool = False):
        self.keywords = keywords
        self.use_mock = use_mock
        self._seen_uids: set[str] = self._load_seen_uids()

    # ── Public API ──────────────────────────────────────────────

    def fetch_new_jobs(self) -> list[JobPosting]:
        """
        Fetch jobs (mock or real), filter by keyword, and return only
        previously-unseen postings. Newly-seen uids are persisted to disk.
        """
        raw_jobs = self._fetch_mock_jobs() if self.use_mock else self._fetch_from_jsearch()
        filtered = self._apply_filters(raw_jobs)
        new_jobs = [j for j in filtered if j.uid not in self._seen_uids]

        for job in new_jobs:
            self._seen_uids.add(job.uid)
        if new_jobs:
            self._save_seen_uids(self._seen_uids)

        logger.info(
            "Scraper found %d raw → %d filtered → %d new jobs",
            len(raw_jobs), len(filtered), len(new_jobs),
        )
        return new_jobs

    # ── Filters ─────────────────────────────────────────────────

    def _apply_filters(self, jobs: list[JobPosting]) -> list[JobPosting]:
        return [j for j in jobs if j.matches_keywords(self.keywords)]

    # ── Keyword Rotation (stay under JSearch's 200 req/month) ────

    def _keywords_for_today(self) -> list[str]:
        """
        Query exactly ONE keyword per day — day_of_year % len(keywords)
        picks which one — so a daily run costs ~1 JSearch request instead
        of one per keyword. The full list still gets covered once every
        len(keywords) days, and this keeps monthly usage far under the
        free-tier cap even with a long keyword list.
        """
        if not self.keywords:
            return []
        day_of_year = datetime.now().timetuple().tm_yday
        index = day_of_year % len(self.keywords)
        return [self.keywords[index]]

    # ── JSearch (free tier) ───────────────────────────────────────

    def _fetch_from_jsearch(self) -> list[JobPosting]:
        if not config.RAPIDAPI_KEY:
            logger.warning("RAPIDAPI_KEY not set — skipping job search (use --mock to test).")
            return []

        keywords_today = self._keywords_for_today()
        if not keywords_today:
            logger.info("No keywords scheduled for today's rotation slot.")
            return []

        jobs: list[JobPosting] = []
        for keyword in keywords_today:
            if not usage_tracker.can_call_jsearch():
                break  # monthly cap reached — stop issuing further requests
            usage_tracker.record_jsearch_call()
            jobs += self._search_jsearch(keyword)
        return jobs

    @staticmethod
    def _search_jsearch(keyword: str) -> list[JobPosting]:
        """One JSearch request for a single keyword, across all companies/locations."""
        headers = {
            "X-RapidAPI-Key": config.RAPIDAPI_KEY,
            "X-RapidAPI-Host": JSEARCH_HOST,
        }
        params = {
            "query": keyword,
            "date_posted": "3days",  # fresh postings only, avoids re-alerting on stale ones
            "num_pages": "1",
        }
        try:
            resp = requests.get(JSEARCH_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            data = resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("JSearch request failed for '%s': %s", keyword, e)
            return []

        if data.get("status") != "OK":
            # e.g. {"message": "You are not subscribed to this API."} on RapidAPI,
            # or a JSearch-side error payload — either way, skip gracefully.
            logger.warning(
                "JSearch returned no results for '%s': %s",
                keyword, data.get("message") or data.get("error") or data,
            )
            return []

        jobs = []
        for item in data.get("data", []):
            location_parts = [p for p in (item.get("job_city"), item.get("job_country")) if p]
            if location_parts:
                location = ", ".join(location_parts)
            elif item.get("job_is_remote"):
                location = "Remote"
            else:
                location = "Unknown"

            jobs.append(JobPosting(
                title=item.get("job_title", "Unknown role"),
                company=item.get("employer_name", "Unknown company"),
                location=location,
                url=item.get("job_apply_link") or item.get("job_google_link") or "",
                description=item.get("job_description", "") or "",
                posted_date=item.get("job_posted_at_datetime_utc"),
                source="jsearch",
            ))
        return jobs

    # ── Mock / Offline Demo Data ──────────────────────────────────

    @staticmethod
    def _fetch_mock_jobs() -> list[JobPosting]:
        """Simulated job feed — used only when explicitly requested via --mock."""
        return [
            JobPosting(
                title="Backend Software Developer",
                company="NVIDIA",
                location="Tel Aviv, Israel",
                url="https://nvidia.com/careers/backend-dev-12345",
                description="Design and build high-performance backend services for GPU cloud platform. Python, Go, Kubernetes.",
                posted_date="2026-08-09",
            ),
            JobPosting(
                title="Data Engineer",
                company="Wix",
                location="Tel Aviv, Israel",
                url="https://wix.com/careers/data-engineer-67890",
                description="Build scalable data pipelines using Spark, Airflow, and AWS. Strong Python required.",
                posted_date="2026-08-08",
            ),
            JobPosting(
                title="Cloud Platform Engineer",
                company="Monday.com",
                location="Tel Aviv, Israel",
                url="https://monday.com/careers/cloud-eng-11111",
                description="Design cloud infrastructure on AWS/Azure. Terraform, CI/CD, backend microservices.",
                posted_date="2026-08-10",
            ),
            JobPosting(
                title="Junior Backend Developer",
                company="CyberArk",
                location="Beer Sheva, Israel",
                url="https://cyberark.com/careers/jr-backend-22222",
                description="Join our identity security team. Java, Python, REST APIs, microservices.",
                posted_date="2026-08-10",
            ),
            JobPosting(
                title="Marketing Manager",
                company="NVIDIA",
                location="Tel Aviv, Israel",
                url="https://nvidia.com/careers/marketing-99999",
                description="Lead product marketing campaigns for enterprise GPU solutions.",
                posted_date="2026-08-07",
            ),
            JobPosting(
                title="Software Developer – Platform Team",
                company="AppsFlyer",
                location="Herzliya, Israel",
                url="https://appsflyer.com/careers/platform-dev-33333",
                description="Clojure, Kafka, large-scale event processing. Backend systems at massive scale.",
                posted_date="2026-08-09",
            ),
        ]

    # ── seen_jobs.json persistence ─────────────────────────────────

    @staticmethod
    def _load_seen_uids() -> set[str]:
        path = config.SEEN_JOBS_FILE
        if not path.exists():
            return set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s — starting with an empty seen-jobs set.", path.name, e)
            return set()

    @staticmethod
    def _save_seen_uids(uids: set[str]) -> None:
        try:
            with open(config.SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
                json.dump(sorted(uids), f, indent=2)
        except OSError as e:
            logger.warning("Failed to save %s: %s", config.SEEN_JOBS_FILE.name, e)

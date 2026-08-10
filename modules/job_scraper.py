"""
Module 1: Job Scraping / Trigger
Discovers new job postings via mock data, RSS feeds, or API integrations.
Swap the mock for real sources (LinkedIn API, Greenhouse, Lever, etc.).
"""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


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

    def matches_locations(self, locations: list[str]) -> bool:
        """Check if the job location matches any target location."""
        loc = self.location.lower()
        return any(target.lower() in loc for target in locations)


class JobScraper:
    """
    Pulls job postings from configured sources.
    Currently uses mock data — replace _fetch_mock_jobs() with real integrations.
    """

    def __init__(self, keywords: list[str], locations: list[str] | None = None):
        self.keywords = keywords
        self.locations = locations or []
        self._seen_uids: set[str] = set()

    # ── Public API ──────────────────────────────────────────────

    def fetch_new_jobs(self) -> list[JobPosting]:
        """
        Fetch jobs from all sources, filter by keywords/location,
        and return only previously-unseen postings.
        """
        raw_jobs = self._fetch_mock_jobs()
        # Plug in real sources here:
        # raw_jobs += self._fetch_from_rss("https://example.com/jobs.rss")
        # raw_jobs += self._fetch_from_greenhouse("company-slug")

        filtered = self._apply_filters(raw_jobs)
        new_jobs = [j for j in filtered if j.uid not in self._seen_uids]

        for job in new_jobs:
            self._seen_uids.add(job.uid)

        logger.info(
            "Scraper found %d raw → %d filtered → %d new jobs",
            len(raw_jobs), len(filtered), len(new_jobs),
        )
        return new_jobs

    # ── Filters ─────────────────────────────────────────────────

    def _apply_filters(self, jobs: list[JobPosting]) -> list[JobPosting]:
        results = []
        for job in jobs:
            if not job.matches_keywords(self.keywords):
                continue
            if self.locations and not job.matches_locations(self.locations):
                continue
            results.append(job)
        return results

    # ── Data Sources (swap these out) ───────────────────────────

    @staticmethod
    def _fetch_mock_jobs() -> list[JobPosting]:
        """Simulated job feed — replace with real API calls."""
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

    # ── Real source stubs (uncomment and implement) ─────────────

    # def _fetch_from_rss(self, feed_url: str) -> list[JobPosting]:
    #     """Parse an RSS/Atom feed for job postings."""
    #     import feedparser
    #     feed = feedparser.parse(feed_url)
    #     jobs = []
    #     for entry in feed.entries:
    #         jobs.append(JobPosting(
    #             title=entry.title,
    #             company=self._extract_company(entry),
    #             location=entry.get("location", "Unknown"),
    #             url=entry.link,
    #             description=entry.get("summary", ""),
    #             source="rss",
    #         ))
    #     return jobs

    # def _fetch_from_greenhouse(self, company_slug: str) -> list[JobPosting]:
    #     """Pull from Greenhouse API (no auth needed for public boards)."""
    #     import requests
    #     resp = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs")
    #     resp.raise_for_status()
    #     jobs = []
    #     for item in resp.json().get("jobs", []):
    #         loc = item.get("location", {}).get("name", "Unknown")
    #         jobs.append(JobPosting(
    #             title=item["title"],
    #             company=company_slug,
    #             location=loc,
    #             url=item["absolute_url"],
    #             description=item.get("content", ""),
    #             source="greenhouse",
    #         ))
    #     return jobs

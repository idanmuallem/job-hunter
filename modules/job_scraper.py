"""
Module 1: Job Scraping / Trigger
Discovers new job postings from free, no-auth sources only:
  - Greenhouse's public job board API (no API key required)
  - Plain RSS/Atom job feeds
A small hardcoded mock job list is used as a fallback/demo mode so the
pipeline can be tested without network access or any sources configured.
"""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
REQUEST_TIMEOUT = 10


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
    Pulls job postings from free sources: Greenhouse boards and RSS feeds.
    Falls back to a small hardcoded mock list if no real source is
    configured, or if every configured source returns nothing (e.g. no
    network access) — this keeps the pipeline testable offline.
    """

    def __init__(
        self,
        keywords: list[str],
        locations: list[str] | None = None,
        greenhouse_slugs: list[str] | None = None,
        rss_feed_urls: list[str] | None = None,
    ):
        self.keywords = keywords
        self.locations = locations or []
        self.greenhouse_slugs = greenhouse_slugs or []
        self.rss_feed_urls = rss_feed_urls or []
        self._seen_uids: set[str] = set()

    # ── Public API ──────────────────────────────────────────────

    def fetch_new_jobs(self) -> list[JobPosting]:
        """
        Fetch jobs from all configured sources, filter by keywords/location,
        and return only previously-unseen postings.
        """
        raw_jobs = self._fetch_all_sources()
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

    # ── Source Orchestration ─────────────────────────────────────

    def _fetch_all_sources(self) -> list[JobPosting]:
        """Pull from every configured free source; fall back to mock data."""
        jobs: list[JobPosting] = []

        for slug in self.greenhouse_slugs:
            jobs += self._fetch_from_greenhouse(slug)

        for feed_url in self.rss_feed_urls:
            jobs += self._fetch_from_rss(feed_url)

        if not jobs:
            reason = (
                "no sources configured"
                if not (self.greenhouse_slugs or self.rss_feed_urls)
                else "configured sources returned nothing (offline or empty boards)"
            )
            logger.info("Falling back to mock/demo job data — %s", reason)
            jobs = self._fetch_mock_jobs()

        return jobs

    # ── Free Data Sources ────────────────────────────────────────

    @staticmethod
    def _fetch_from_greenhouse(company_slug: str) -> list[JobPosting]:
        """
        Pull open roles from a public Greenhouse job board.
        Free, no API key required: https://boards-api.greenhouse.io
        """
        url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
        try:
            resp = requests.get(url, params={"content": "true"}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning("Greenhouse fetch failed for '%s': %s", company_slug, e)
            return []

        try:
            data = resp.json()
        except ValueError as e:
            logger.warning("Greenhouse returned invalid JSON for '%s': %s", company_slug, e)
            return []

        jobs = []
        for item in data.get("jobs", []):
            description = _HTML_TAG_RE.sub(" ", item.get("content", "")).strip()
            jobs.append(JobPosting(
                title=item.get("title", "Unknown role"),
                company=item.get("company_name", company_slug),
                location=(item.get("location") or {}).get("name", "Unknown"),
                url=item.get("absolute_url", ""),
                description=description,
                posted_date=item.get("updated_at"),
                source="greenhouse",
            ))
        return jobs

    @staticmethod
    def _fetch_from_rss(feed_url: str) -> list[JobPosting]:
        """Parse a plain RSS/Atom feed for job postings using the stdlib only."""
        try:
            resp = requests.get(feed_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning("RSS fetch failed for '%s': %s", feed_url, e)
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning("RSS parse failed for '%s': %s", feed_url, e)
            return []

        jobs = []
        # Support both RSS 2.0 (<item>) and Atom (<entry>) formats.
        items = root.findall(".//item") or root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )
        for entry in items:
            title = _text_of(entry, "title")
            link = _text_of(entry, "link") or _atom_link(entry)
            description = _HTML_TAG_RE.sub(
                " ", _text_of(entry, "description") or _text_of(entry, "summary") or ""
            ).strip()
            pub_date = _text_of(entry, "pubDate") or _text_of(entry, "updated")

            if not title or not link:
                continue

            jobs.append(JobPosting(
                title=title,
                company=_text_of(root.find(".//channel"), "title") or "Unknown",
                location="Unknown",
                url=link,
                description=description,
                posted_date=pub_date,
                source="rss",
            ))
        return jobs

    @staticmethod
    def _fetch_mock_jobs() -> list[JobPosting]:
        """Simulated job feed — used as a fallback/demo when no real source is configured."""
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


def _text_of(node: Optional[ET.Element], tag: str) -> str:
    """Safely read the text of a direct child tag, empty string if missing."""
    if node is None:
        return ""
    child = node.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _atom_link(entry: ET.Element) -> str:
    """Atom <link href="..."/> is an attribute, not text — read it directly."""
    link = entry.find("{http://www.w3.org/2005/Atom}link")
    return link.get("href", "") if link is not None else ""

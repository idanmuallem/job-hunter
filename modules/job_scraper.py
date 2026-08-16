"""
Module 1: Job Scraping / Trigger
Discovers new job postings from multiple sources:
  - JSearch (RapidAPI, free tier, capped/rate-limited — see usage_tracker;
    searches ALL companies globally, no pre-configured list)
  - Remotive, RemoteOK, Arbeitnow (free, unlimited, no API key required —
    run every day regardless of the JSearch budget)
  - A curated list of Israeli tech companies (config.ISRAELI_ATS_COMPANIES),
    crawled directly via their own Greenhouse/Lever job-board APIs — also
    free and unlimited, and independent of JSearch's location handling.
All raw postings pass through the same keyword filter, a title filter
(rejects irrelevant categories — QA, DevOps/SRE, support, sales, etc. —
and anything above mid-level seniority; see _passes_title_filter), an
Israel-location filter (see _is_israel_relevant — position location, not
company nationality), and dedup logic before an alert is ever generated.

Seen jobs are persisted to seen_jobs.json so re-running the pipeline
doesn't re-alert on the same posting across days; entries older than
SEEN_JOB_RETENTION_DAYS are pruned automatically. Dedup is keyed on
normalized company+title, not URL — the same real posting can reach
this pipeline through multiple sources with different apply/tracking
links, and would otherwise alert twice on one actual opening (see
JobPosting.__post_init__). A small hardcoded mock job list is
available via --mock for offline testing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import requests

import config
from modules import usage_tracker

logger = logging.getLogger(__name__)

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search-v2"
JSEARCH_HOST = "jsearch.p.rapidapi.com"
REQUEST_TIMEOUT = 15

# How long a job uid is remembered before it's eligible to be re-alerted on.
# Keeps seen_jobs.json from growing forever.
SEEN_JOB_RETENTION_DAYS = 30


def _passes_title_filter(title: str) -> bool:
    """False if the title names a role/seniority the user isn't targeting
    (QA, DevOps/SRE, support, sales, senior+, etc.) — see
    config.EXCLUDED_TITLE_KEYWORDS."""
    title_lower = (title or "").lower()
    return not any(kw in title_lower for kw in config.EXCLUDED_TITLE_KEYWORDS)


_COMPANY_SUFFIX_RE = re.compile(r"\s+(inc\.?|ltd\.?|llc\.?|corp\.?|co\.?|gmbh|s\.a\.|plc)$")


def _normalize_for_dedup(text: str) -> str:
    """Lowercase + collapse whitespace, so minor formatting differences
    between sources (extra spaces, casing) don't produce different dedup
    keys for what's actually the same posting."""
    return " ".join((text or "").lower().split())


def _normalize_company_for_dedup(company: str) -> str:
    """Same as _normalize_for_dedup, plus stripping common company-name
    suffixes (Inc/Ltd/etc.) that different sources add inconsistently."""
    return _COMPANY_SUFFIX_RE.sub("", _normalize_for_dedup(company)).strip()


def _is_israel_relevant(location: str) -> bool:
    """
    True if the POSITION (not the company) is Israel-relevant: the
    location text explicitly names Israel, or it's a generic/open remote
    listing with no other region restriction. See config.py for the
    keyword lists and the "loose" matching rationale.
    """
    loc = (location or "").lower()
    if any(kw in loc for kw in config.ISRAEL_LOCATION_KEYWORDS):
        return True
    if any(kw in loc for kw in config.REMOTE_RESTRICTION_KEYWORDS):
        return False
    return any(kw in loc for kw in config.REMOTE_OPEN_KEYWORDS)


@dataclass
class JobPosting:
    """Represents a single discovered job posting."""
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    posted_date: Optional[str] = None
    uid: str = field(default="", init=False)

    def __post_init__(self):
        # Deliberately excludes url: the same real posting can reach this
        # pipeline through more than one source with a different apply/
        # tracking link each time (e.g. a company's own Greenhouse listing
        # vs. the identical job aggregated by JSearch from LinkedIn) —
        # keying on url would treat those as two different jobs and alert
        # on the same actual opening twice. company/title are normalized
        # (case, whitespace, common suffixes) so formatting differences
        # between sources don't do the same thing.
        raw = f"{_normalize_company_for_dedup(self.company)}|{_normalize_for_dedup(self.title)}"
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
        # uid -> ISO timestamp first seen. A dict (not a set) so stale
        # entries can be pruned by age — see SEEN_JOB_RETENTION_DAYS.
        self._seen_uids: dict[str, str] = self._load_seen_uids()

    # ── Public API ──────────────────────────────────────────────

    def fetch_new_jobs(self) -> list[JobPosting]:
        """
        Fetch jobs (mock or real), filter by keyword, and return only
        previously-unseen postings. Newly-seen uids are persisted to disk.
        """
        if self.use_mock:
            raw_jobs = self._fetch_mock_jobs()
        else:
            raw_jobs = (
                self._fetch_from_jsearch()
                + self._fetch_from_free_sources()
                + self._fetch_from_ats_companies()
            )
        filtered = self._apply_filters(raw_jobs)

        # Drop duplicates within this batch too, not just against
        # already-seen history — e.g. a company can genuinely post the
        # same-titled role as two separate reqs (different job ids, same
        # company+title), or the same posting can turn up via two
        # different sources in one run. Keep the first occurrence.
        deduped: list[JobPosting] = []
        seen_this_batch: set[str] = set()
        for job in filtered:
            if job.uid in seen_this_batch:
                continue
            seen_this_batch.add(job.uid)
            deduped.append(job)

        new_jobs = [j for j in deduped if j.uid not in self._seen_uids]

        now_iso = datetime.now().isoformat()
        for job in new_jobs:
            self._seen_uids[job.uid] = now_iso
        if new_jobs:
            self._save_seen_uids(self._seen_uids)

        logger.info(
            "Scraper found %d raw → %d filtered → %d deduped → %d new jobs",
            len(raw_jobs), len(filtered), len(deduped), len(new_jobs),
        )
        return new_jobs

    # ── Filters ─────────────────────────────────────────────────

    def _apply_filters(self, jobs: list[JobPosting]) -> list[JobPosting]:
        return [
            j for j in jobs
            if j.matches_keywords(self.keywords)
            and _is_israel_relevant(j.location)
            and _passes_title_filter(j.title)
        ]

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
            "country": "il",  # JSearch defaults to "us" when omitted — scope to Israel server-side
            "job_requirements": "under_3_years_experience,no_experience,no_degree",  # junior/mid only, server-side
            "employment_types": "FULLTIME",
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
        # /search-v2 nests results at data.jobs (a v1-era plain list under
        # "data" is no longer what this endpoint returns).
        for item in (data.get("data") or {}).get("jobs", []):
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
            ))
        return jobs

    # ── Free job boards (no key, no rate limit) ────────────────────
    # Unlike JSearch these never touch usage_tracker — they're free and
    # unlimited, so they run on every cycle regardless of budget. Each
    # source is isolated: a failure in one never blocks the others or the
    # rest of the pipeline.

    def _fetch_from_free_sources(self) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        for name, fetcher in (
            ("Remotive", self._fetch_remotive),
            ("RemoteOK", self._fetch_remoteok),
            ("Arbeitnow", self._fetch_arbeitnow),
        ):
            try:
                found = fetcher()
                logger.info("%s: %d job(s) fetched", name, len(found))
                jobs += found
            except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as e:
                logger.warning("%s fetch failed: %s", name, e)
        return jobs

    @staticmethod
    def _fetch_remotive() -> list[JobPosting]:
        """Remotive — free, no key. https://remotive.com/api/remote-jobs"""
        resp = requests.get(
            "https://remotive.com/api/remote-jobs",
            params={"category": "software-dev", "limit": 100},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            JobPosting(
                title=item.get("title", "Unknown role"),
                company=item.get("company_name", "Unknown company"),
                location=item.get("candidate_required_location", "Anywhere") or "Anywhere",
                url=item.get("url", ""),
                description=item.get("description", "") or "",
                posted_date=item.get("publication_date"),
            )
            for item in data.get("jobs", [])
        ]

    @staticmethod
    def _fetch_remoteok() -> list[JobPosting]:
        """RemoteOK — free, no key. https://remoteok.com/api"""
        resp = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "job-hunter/1.0"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # The first element of the response is API metadata, not a job.
        return [
            JobPosting(
                title=item.get("position", "Unknown role"),
                company=item.get("company", "Unknown company"),
                location=item.get("location", "Remote") or "Remote",
                url=item.get("url") or f"https://remoteok.com/l/{item.get('id', '')}",
                description=item.get("description", "") or "",
                posted_date=item.get("date"),
            )
            for item in data[1:]
        ]

    @staticmethod
    def _fetch_arbeitnow() -> list[JobPosting]:
        """Arbeitnow — free, no key. https://arbeitnow.com/api"""
        resp = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            JobPosting(
                title=item.get("title", "Unknown role"),
                company=item.get("company_name", "Unknown company"),
                location=item.get("location", "Remote") or "Remote",
                url=item.get("url", ""),
                description=item.get("description", "") or "",
                posted_date=str(item.get("created_at")) if item.get("created_at") else None,
            )
            for item in data.get("data", [])
        ]

    # ── Curated Israeli-company ATS crawl (free, no key, no limit) ──
    # Hits companies' own public job-board APIs directly — the same
    # endpoints their careers pages call — so there's no rate limit to
    # track and it never touches the JSearch budget. See
    # config.ISRAELI_ATS_COMPANIES for the company list and how to extend
    # it. Each company is isolated: one 404/timeout never blocks the rest.

    def _fetch_from_ats_companies(self) -> list[JobPosting]:
        companies = getattr(config, "ISRAELI_ATS_COMPANIES", [])
        if not companies:
            return []

        jobs: list[JobPosting] = []
        for company in companies:
            platform = company.get("ats_platform")
            fetcher = {
                "greenhouse": self._fetch_greenhouse,
                "lever": self._fetch_lever,
            }.get(platform)
            if fetcher is None:
                logger.warning(
                    "Unknown ats_platform '%s' for %s — skipping.",
                    platform, company.get("name"),
                )
                continue
            try:
                found = fetcher(company)
                if found:
                    logger.info("%s (%s): %d job(s) fetched", company["name"], platform, len(found))
                jobs += found
            except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as e:
                logger.warning("%s (%s) fetch failed: %s", company.get("name"), platform, e)
        return jobs

    @staticmethod
    def _fetch_greenhouse(company: dict) -> list[JobPosting]:
        """Greenhouse — free public API, no auth. One company at a time."""
        slug = company["ats_slug"]
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return []  # wrong/stale slug — not a failure worth logging loudly
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for item in data.get("jobs", []):
            location = item.get("location") or {}
            location_name = location.get("name", "") if isinstance(location, dict) else str(location)
            jobs.append(JobPosting(
                title=item.get("title", "Unknown role"),
                company=company["name"],
                location=location_name or "Israel",
                url=item.get("absolute_url", ""),
                description=item.get("content", "") or "",
                posted_date=item.get("updated_at"),
            ))
        return jobs

    @staticmethod
    def _fetch_lever(company: dict) -> list[JobPosting]:
        """Lever — free public API, no auth. One company at a time."""
        slug = company["ats_slug"]
        resp = requests.get(
            f"https://api.lever.co/v0/postings/{slug}",
            params={"mode": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 404:
            return []  # wrong/stale slug — not a failure worth logging loudly
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []

        jobs = []
        for item in data:
            categories = item.get("categories") or {}
            location = categories.get("location", "") if isinstance(categories, dict) else ""
            jobs.append(JobPosting(
                title=item.get("text", "Unknown role"),
                company=company["name"],
                location=location or "Israel",
                url=item.get("hostedUrl", ""),
                description=item.get("descriptionPlain") or item.get("description", "") or "",
                posted_date=None,
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
    # Stored as {uid: iso_timestamp_first_seen} so entries older than
    # SEEN_JOB_RETENTION_DAYS can be pruned on load — otherwise the file
    # would grow forever. Transparently migrates the old flat-list format
    # (no timestamps) the first time it's loaded.

    @staticmethod
    def _load_seen_uids() -> dict[str, str]:
        path = config.SEEN_JOBS_FILE
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s — starting with an empty seen-jobs set.", path.name, e)
            return {}

        if isinstance(data, list):
            # Legacy format: a flat list of uids with no timestamps.
            # Treat every entry as "seen right now" so migrating doesn't
            # silently lose them or prune them all in one go.
            now_iso = datetime.now().isoformat()
            seen = {uid: now_iso for uid in data}
        elif isinstance(data, dict):
            seen = data
        else:
            logger.warning("%s has an unrecognized format — starting with an empty seen-jobs set.", path.name)
            return {}

        cutoff = datetime.now() - timedelta(days=SEEN_JOB_RETENTION_DAYS)
        pruned: dict[str, str] = {}
        for uid, ts in seen.items():
            try:
                seen_at = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                # Malformed timestamp — treat as freshly seen rather than
                # silently dropping the uid.
                seen_at = datetime.now()
            if seen_at >= cutoff:
                pruned[uid] = seen_at.isoformat()

        dropped = len(seen) - len(pruned)
        if dropped:
            logger.info(
                "Pruned %d seen-job uid(s) older than %d days.",
                dropped, SEEN_JOB_RETENTION_DAYS,
            )
        return pruned

    @staticmethod
    def _save_seen_uids(seen: dict[str, str]) -> None:
        try:
            with open(config.SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
                json.dump(seen, f, indent=2, sort_keys=True)
        except OSError as e:
            logger.warning("Failed to save %s: %s", config.SEEN_JOBS_FILE.name, e)

"""
Pipeline Orchestrator
Ties all four modules together. Processes each job with up to 3 contacts.
Supports single run and once-daily scheduling.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import config
from modules.job_scraper import JobScraper, JobPosting
from modules.contact_finder import ContactFinder, Contact
from modules.message_generator import MessageGenerator, GeneratedOutreach
from modules.alerter import (
    AlertDispatcher,
    ConsoleAlert,
    JsonLogAlert,
    TelegramAlert,
    JobAlert,
    OutreachPackage,
)

logger = logging.getLogger(__name__)

# How many contacts to include per job
CONTACTS_PER_JOB = 3


@dataclass
class PipelineResult:
    """Result of processing a single job posting."""
    job: JobPosting
    contacts: list[Contact] = field(default_factory=list)
    outreach_list: list[GeneratedOutreach] = field(default_factory=list)
    alert_results: dict[str, bool] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return len(self.outreach_list) > 0 and any(self.alert_results.values())


class JobHunterPipeline:
    """
    The main autonomous job hunting agent.
    Scrape → Find Top 3 Contacts → Generate Messages → Alert Human.
    """

    def __init__(
        self,
        use_telegram: bool = False,
    ):
        # Module 1: Job Scraper
        self.scraper = JobScraper(
            keywords=config.JOB_KEYWORDS,
            locations=config.TARGET_LOCATIONS,
        )

        # Module 2: Contact Finder
        self.finder = ContactFinder()

        # Module 3: Message Generator (hardcoded template, no LLM)
        self.generator = MessageGenerator()

        # Module 4: Alert Dispatcher
        channels = [ConsoleAlert(), JsonLogAlert()]
        if use_telegram:
            channels.insert(0, TelegramAlert())
        self.alerter = AlertDispatcher(channels=channels)

        self._processed_count = 0

    # ── Single Run ──────────────────────────────────────────────

    def run_once(self) -> list[PipelineResult]:
        """Execute one full cycle of the pipeline."""
        logger.info("━━━ Pipeline cycle starting ━━━")
        results: list[PipelineResult] = []

        # Step 1: Discover new jobs
        new_jobs = self.scraper.fetch_new_jobs()
        if not new_jobs:
            logger.info("No new jobs found this cycle.")
            return results

        logger.info("Found %d new job(s) to process", len(new_jobs))

        # Step 2–4: Process each job
        for job in new_jobs:
            result = self._process_job(job)
            results.append(result)
            self._processed_count += 1

        successes = sum(1 for r in results if r.success)
        logger.info(
            "━━━ Cycle complete: %d/%d jobs produced outreach ━━━",
            successes, len(results),
        )
        return results

    def _process_job(self, job: JobPosting) -> PipelineResult:
        """Run a single job through the full pipeline."""
        result = PipelineResult(job=job)
        logger.info("Processing: %s at %s", job.title, job.company)

        # Step 2: Find top 3 contacts
        contacts = self.finder.find_top_contacts(job.company, n=CONTACTS_PER_JOB)
        if not contacts:
            result.error = f"No suitable contacts found at {job.company}"
            logger.warning(result.error)
            return result
        result.contacts = contacts

        # Step 3: Generate a message for each contact
        try:
            outreach_list = self.generator.generate_batch(contacts, job)
            result.outreach_list = outreach_list
        except Exception as e:
            result.error = f"Message generation failed: {e}"
            logger.error(result.error)
            return result

        # Step 4: Build a single alert with all contacts and send it
        packages = [
            OutreachPackage(
                rank=i + 1,
                contact_name=o.contact.name,
                contact_role=o.contact.role,
                contact_linkedin=o.contact.linkedin_url,
                priority_label=o.priority_label,
                message=o.message,
                char_count=o.char_count,
            )
            for i, o in enumerate(outreach_list)
        ]

        alert = JobAlert(
            company=job.company,
            job_title=job.title,
            job_url=job.url,
            posted_date=job.posted_date,
            contacts=packages,
        )
        result.alert_results = self.alerter.dispatch(alert)
        return result

    # ── Daily Schedule ──────────────────────────────────────────

    def run_daily(self, run_at_hour: int = 8):
        """
        Run the pipeline once per day at the specified hour (24h format).
        Example: run_at_hour=8 → runs at 08:00 every day.
        Press Ctrl+C to stop.
        """
        logger.info(
            "Daily mode: will run every day at %02d:00. Ctrl+C to stop.",
            run_at_hour,
        )

        try:
            while True:
                now = datetime.now()
                # Calculate next run time
                next_run = now.replace(
                    hour=run_at_hour, minute=0, second=0, microsecond=0,
                )
                if next_run <= now:
                    next_run += timedelta(days=1)

                wait_seconds = (next_run - now).total_seconds()
                logger.info(
                    "Next run at %s (in %.1f hours)",
                    next_run.strftime("%Y-%m-%d %H:%M"),
                    wait_seconds / 3600,
                )
                time.sleep(wait_seconds)

                # Run the pipeline
                self.run_once()
        except KeyboardInterrupt:
            logger.info(
                "Pipeline stopped. Total jobs processed: %d",
                self._processed_count,
            )

    # ── Stats ───────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        return {
            "total_processed": self._processed_count,
            "seen_jobs": len(self.scraper._seen_uids),
        }

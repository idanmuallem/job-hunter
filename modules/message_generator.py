"""
Module 3: Message Generation
Generates a personalized outreach message using a hardcoded, dynamic
f-string template. No external LLM/AI API is used — the message text
is fixed and only the target name, company, and job title are injected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import config
from modules.contact_finder import Contact
from modules.job_scraper import JobPosting

logger = logging.getLogger(__name__)


@dataclass
class GeneratedOutreach:
    """Container for the final outreach package."""
    contact: Contact
    job: JobPosting
    message: str
    priority_label: str
    char_count: int

    @property
    def is_valid(self) -> bool:
        return 0 < self.char_count <= config.MESSAGE_CHAR_LIMIT


class MessageGenerator:
    """
    Builds outreach messages from a fixed, hardcoded template.
    No AI/LLM calls are made — the message is deterministic and only
    the target name, company name, and job title vary between contacts.
    """

    # ── Public API ──────────────────────────────────────────────

    def generate_batch(
        self, contacts: list[Contact], job: JobPosting
    ) -> list[GeneratedOutreach]:
        """Generate a message for each contact in the list."""
        return [self.generate(contact, job) for contact in contacts]

    def generate(self, contact: Contact, job: JobPosting) -> GeneratedOutreach:
        """Build the personalized outreach message for a single contact."""
        message = self._build_message(
            target_name=contact.name,
            company_name=contact.company,
            job_title=job.title,
        )

        outreach = GeneratedOutreach(
            contact=contact,
            job=job,
            message=message,
            priority_label=contact.priority_label,
            char_count=len(message),
        )
        logger.info(
            "Generated message for %s (%d chars, valid=%s)",
            contact.name, outreach.char_count, outreach.is_valid,
        )
        return outreach

    # ── Template ────────────────────────────────────────────────

    @staticmethod
    def _build_message(target_name: str, company_name: str, job_title: str) -> str:
        """
        Fixed outreach message template.
        The only moving parts are the target's name, the company name,
        and the job title — everything else is a hardcoded string.
        """
        message = f"Hi {target_name}! I'm a 3rd-year CS & Cognitive Science student. I’ve been following {company_name} and would love to apply for the {job_title} role. I've attached my resume—would you be open to passing it along internally for this position? Thanks!"
        return message

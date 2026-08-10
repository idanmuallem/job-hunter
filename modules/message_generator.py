"""
Module 3: Message Templater
No LLM. No external API call. No per-contact customization beyond the
recipient's first name — every outreach message is the same fixed
template string, personalized only by substituting {first_name}.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import config
from modules.contact_finder import Contact
from modules.job_scraper import JobPosting

logger = logging.getLogger(__name__)

# The one and only message template — reused for every contact regardless
# of company, role, or priority tier. No branching logic per priority.
MESSAGE_TEMPLATE = (
    "Hi {first_name}, I'm {sender_name} — a {sender_degree} student "
    "specializing in backend development, data engineering, and cloud "
    "(AWS/Azure). I'd love to connect and learn more about your work!"
)


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
    """Fills the fixed template with the contact's first name. That's it."""

    # ── Public API ──────────────────────────────────────────────

    def generate_batch(
        self, contacts: list[Contact], job: JobPosting
    ) -> list[GeneratedOutreach]:
        """Generate a message for each contact in the list."""
        return [self.generate(contact, job) for contact in contacts]

    def generate(self, contact: Contact, job: JobPosting) -> GeneratedOutreach:
        """Build the personalized outreach message for a single contact."""
        first_name = self._extract_first_name(contact.name)
        message = MESSAGE_TEMPLATE.format(
            first_name=first_name,
            sender_name=config.PROFILE["name"],
            sender_degree=config.PROFILE["degree_short"],
        )
        message = self._enforce_char_limit(message)

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

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_first_name(full_name: str) -> str:
        """Return just the first token of a full name."""
        parts = full_name.strip().split()
        return parts[0] if parts else full_name

    @staticmethod
    def _enforce_char_limit(message: str) -> str:
        """
        Hard safety net: truncate at a word boundary if the message ever
        exceeds the configured limit. Shouldn't trigger with the default
        template + a normal first name, but guards against edge cases
        (very long names, a future template edit, etc.).
        """
        if len(message) <= config.MESSAGE_CHAR_LIMIT:
            return message
        return message[: config.MESSAGE_CHAR_LIMIT - 3].rsplit(" ", 1)[0] + "..."

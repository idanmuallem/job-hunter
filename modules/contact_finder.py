"""
Module 2: The Finder Logic (Target Prioritization)
Finds people to contact at a target company from two free sources and
ranks them by a strict priority hierarchy:
  A) 1st-degree connections     — known_connections.json (manual, free)
  B) Alumni (BGU / McGill)      — known_connections.json (manual, free)
  C) Engineering Managers/Leads — Apollo.io free tier (auto-discovered)
  D) HR / Technical Recruiters  — Apollo.io free tier (auto-discovered)

We never scrape or log into LinkedIn — that violates its Terms of
Service. known_connections.json is the intended, ToS-compliant way to
capture your own network; Apollo's free tier only ever discloses
name/title/company/LinkedIn URL (revealing emails/phone is what costs
credits, and this project never does that).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/search"
REQUEST_TIMEOUT = 10


class Priority(IntEnum):
    """Contact priority — lower numeric value = higher priority."""
    A = 1  # 1st-degree connection
    B = 2  # University alumni
    C = 3  # Engineering manager / tech lead
    D = 4  # HR / recruiter
    NONE = 99


@dataclass
class Contact:
    """A person found at the target company."""
    name: str
    role: str
    company: str
    linkedin_url: str
    is_first_degree: bool = False
    university: str = ""
    department: str = ""
    source: str = "known_connections"

    @property
    def priority(self) -> Priority:
        """Determine this contact's priority bucket."""
        if self.is_first_degree:
            return Priority.A

        alumni_schools = {
            config.PROFILE["university"].lower(),
            config.PROFILE["alt_university"].lower(),
        }
        if self.university.lower() in alumni_schools:
            return Priority.B

        role_lower = self.role.lower()
        if any(signal in role_lower for signal in config.ENGINEERING_TITLES):
            return Priority.C
        if any(signal in role_lower for signal in config.HR_TITLES):
            return Priority.D

        return Priority.NONE

    @property
    def priority_label(self) -> str:
        p = self.priority
        if p == Priority.NONE:
            return "No matching priority"
        return config.PRIORITY_LABELS[p.name]


class ContactFinder:
    """
    Finds and ranks contacts at a target company by merging:
      1. known_connections.json (manual, free — Priority A/B)
      2. Apollo.io free-tier search (auto, free — Priority C/D)
    Works with just #1 if Apollo isn't configured; never fabricates
    placeholder people if nothing is found.
    """

    def __init__(self):
        self._cache: dict[str, list[Contact]] = {}
        self._known_connections = self._load_known_connections()

    def find_best_contact(self, company: str) -> Optional[Contact]:
        """Convenience wrapper — returns the single top contact."""
        top = self.find_top_contacts(company, n=1)
        return top[0] if top else None

    def find_top_contacts(self, company: str, n: int = 3) -> list[Contact]:
        """
        Search for people at `company` and return up to `n` contacts,
        ranked by the priority hierarchy (A → B → C → D).
        Returns an empty list if nobody relevant is found — never
        fabricates placeholder contacts.
        """
        key = company.lower().strip()
        if key not in self._cache:
            self._cache[key] = self._gather_contacts(company)
        contacts = self._cache[key]

        ranked = [c for c in contacts if c.priority != Priority.NONE]
        if not ranked:
            logger.warning("No prioritized contacts found at %s", company)
            return []

        ranked.sort(key=lambda c: c.priority)
        top = ranked[:n]
        logger.info(
            "Top %d contact(s) at %s: %s",
            len(top),
            company,
            ", ".join(f"{c.name} (Pri {c.priority.name})" for c in top),
        )
        return top

    # ── Source Aggregation ───────────────────────────────────────

    def _gather_contacts(self, company: str) -> list[Contact]:
        """Merge known connections and Apollo results, de-duplicated by name."""
        contacts: list[Contact] = []
        seen_names: set[str] = set()

        for contact in self._get_known_contacts(company):
            if contact.name.lower() not in seen_names:
                contacts.append(contact)
                seen_names.add(contact.name.lower())

        for contact in self._search_apollo(company):
            if contact.name.lower() not in seen_names:
                contacts.append(contact)
                seen_names.add(contact.name.lower())

        return contacts

    # ── Source 1: known_connections.json (manual, free) ──────────

    def _get_known_contacts(self, company: str) -> list[Contact]:
        key = company.lower().strip()
        entries = []
        for db_key, people in self._known_connections.items():
            if db_key in key or key in db_key:
                entries = people
                break

        return [
            Contact(
                name=e["name"],
                role=e.get("role", ""),
                company=company,
                linkedin_url=e.get("linkedin_url", ""),
                is_first_degree=e.get("is_first_degree", False),
                university=e.get("university", ""),
                department=e.get("department", ""),
                source="known_connections",
            )
            for e in entries
        ]

    @staticmethod
    def _load_known_connections() -> dict[str, list[dict]]:
        """Load the user's manual connections file. Missing file → empty dict."""
        path = config.KNOWN_CONNECTIONS_FILE
        if not path.exists():
            logger.warning(
                "%s not found — Priority A/B contacts unavailable. "
                "Copy known_connections.example.json to get started.",
                path.name,
            )
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load %s: %s", path.name, e)
            return {}

        # Keys starting with "_" (e.g. "_readme") are documentation, not companies.
        return {k: v for k, v in data.items() if not k.startswith("_")}

    # ── Source 2: Apollo.io free tier (auto-discovery, free) ─────

    @staticmethod
    def _search_apollo(company: str) -> list[Contact]:
        """
        Search Apollo's free tier for engineering leads and recruiters at
        `company`. Returns [] on any failure — must never crash the pipeline.
        """
        if not config.APOLLO_API_KEY:
            return []

        titles = ["Engineering Manager", "Tech Lead", "Technical Recruiter", "Talent Acquisition"]
        payload = {
            "q_organization_name": company,
            "person_titles": titles,
            "page": 1,
            "per_page": 10,
        }
        headers = {
            "X-Api-Key": config.APOLLO_API_KEY,
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(
                APOLLO_SEARCH_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("Apollo search failed for '%s': %s", company, e)
            return []
        except ValueError as e:
            logger.warning("Apollo returned invalid JSON for '%s': %s", company, e)
            return []

        people = data.get("people", [])
        if not people:
            return []

        contacts = []
        for person in people:
            name = person.get("name") or " ".join(
                filter(None, [person.get("first_name"), person.get("last_name")])
            )
            linkedin_url = person.get("linkedin_url")
            role = person.get("title", "")
            if not name or not linkedin_url:
                continue  # skip incomplete records rather than fabricating data

            contacts.append(Contact(
                name=name,
                role=role,
                company=(person.get("organization") or {}).get("name", company),
                linkedin_url=linkedin_url,
                is_first_degree=False,
                university="",
                department="",
                source="apollo",
            ))
        return contacts

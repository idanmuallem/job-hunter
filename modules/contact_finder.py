"""
Module 2: The Finder Logic (Target Prioritization)
Finds people to contact at a target company from two free sources and
ranks them by a strict priority hierarchy:
  A) 1st-degree connections — your LinkedIn Connections.csv export (free)
  B) University alumni      — not available from the CSV (no university
                               column); kept in the enum for future use
  C) Engineering Managers/Leads — Apollo.io (auto-discovered per company)
  D) HR / Technical Recruiters  — Apollo.io (auto-discovered per company)

We never scrape or log into LinkedIn — that violates its Terms of
Service. The Connections.csv export is LinkedIn's own officially
provided data export, which is the ToS-compliant way to get your 1st-
degree network. Apollo is called per-company as jobs are discovered —
there is no pre-configured company list.

NOTE: as of this writing, Apollo's search endpoints return
"API_INACCESSIBLE" on a true Free plan (API access requires a paid
plan) — see _search_apollo(). The integration is implemented so it
starts working automatically the moment the key gains API access;
until then, Priority C/D will simply come back empty.
"""

from __future__ import annotations

import csv
import logging
import re
import urllib.parse
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Optional

import requests

import config
from modules import usage_tracker

logger = logging.getLogger(__name__)

# Current Apollo endpoints per official docs (docs.apollo.io), verified
# live against the project's own API key:
#   - "organization_top_people" does NOT exist (confirmed: HTTP 404).
#   - These two endpoints exist and are correctly named, but return
#     HTTP 403 {"error_code": "API_INACCESSIBLE"} on a Free plan — API
#     access itself requires a paid plan. See _flag_if_plan_inaccessible().
APOLLO_ORG_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_companies/search"
APOLLO_PEOPLE_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/api_search"
REQUEST_TIMEOUT = 10

_COMPANY_SUFFIXES = (
    " incorporated", " inc.", " inc", " ltd.", " ltd", " llc.", " llc",
    " corp.", " corp", " co.", " co", " gmbh", " s.a.", " plc",
)
_NON_ALNUM_RE = re.compile(r"[^\w\s]")


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
    source: str = "linkedin_csv"

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


# ── Priority E: LinkedIn search fallback (no real contact found) ────
# Generated only when Priority A-D come up completely empty for a
# company. There's no name attached — just a LinkedIn people-search link
# — so this intentionally never reaches modules.message_generator (there's
# no first name to substitute). The human clicks through, picks a real
# person from the results, and sends the message themselves.
LINKEDIN_SEARCH_TITLES = [
    {"title": "Engineering Manager", "label": "Engineering Manager", "category": "engineering"},
    {"title": "Recruiter", "label": "Recruiter / HR", "category": "hr"},
]


@dataclass
class SearchFallback:
    """A LinkedIn people-search link, shown in place of a named contact."""
    label: str
    category: str  # "engineering" | "hr"
    search_url: str


class ContactFinder:
    """
    Finds and ranks contacts at a target company by merging:
      1. Your LinkedIn Connections.csv export (free, manual — Priority A)
      2. Apollo.io auto-discovery, called per-company (free tier — Priority C/D)
    Works with just #1 if Apollo isn't configured/accessible; never
    fabricates placeholder people.
    """

    def __init__(self):
        self._connections = self._load_linkedin_connections()
        # Set True after the first hard Apollo failure (e.g. plan doesn't
        # include API access) so we stop retrying a dead key mid-run.
        self._apollo_unavailable = False

    def find_top_contacts(self, company: str, n: int = 3) -> list[Contact]:
        """
        Search for people at `company` and return up to `n` contacts,
        ranked by the priority hierarchy (A → B → C → D). Returns an
        empty list if nobody relevant is found — never fabricates
        placeholder contacts.
        """
        contacts = self._gather_contacts(company)
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

    def find_search_fallbacks(self, company: str) -> list[SearchFallback]:
        """
        Priority E — call this only when find_top_contacts() returned
        nothing. Builds LinkedIn people-search URLs (pure string
        templating, no API call, always succeeds) so the job still gets
        alerted on instead of silently disappearing.
        """
        fallbacks = []
        for entry in LINKEDIN_SEARCH_TITLES:
            keywords = f"{company} {entry['title']}"
            url = (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={urllib.parse.quote(keywords)}"
            )
            fallbacks.append(SearchFallback(
                label=entry["label"],
                category=entry["category"],
                search_url=url,
            ))
        return fallbacks

    # ── Source Aggregation ───────────────────────────────────────

    def _gather_contacts(self, company: str) -> list[Contact]:
        """Merge LinkedIn CSV matches and Apollo results, de-duplicated by name."""
        contacts: list[Contact] = []
        seen_names: set[str] = set()

        for contact in self._match_linkedin_connections(company):
            if contact.name.lower() not in seen_names:
                contacts.append(contact)
                seen_names.add(contact.name.lower())

        for contact in self._search_apollo(company):
            if contact.name.lower() not in seen_names:
                contacts.append(contact)
                seen_names.add(contact.name.lower())

        return contacts

    # ── Source 1: LinkedIn Connections.csv (manual export, free) ─

    def _match_linkedin_connections(self, company: str) -> list[Contact]:
        matches = []
        for row in self._connections:
            row_company = (row.get("Company") or "").strip()
            if not row_company or not _companies_match(row_company, company):
                continue

            name = " ".join(
                part.strip() for part in
                (row.get("First Name", ""), row.get("Last Name", ""))
                if part.strip()
            )
            if not name:
                continue

            matches.append(Contact(
                name=name,
                role=(row.get("Position") or "").strip(),
                company=company,
                linkedin_url=(row.get("URL") or "").strip(),
                is_first_degree=True,  # the CSV only ever contains 1st-degree connections
                university="",
                source="linkedin_csv",
            ))
        return matches

    @staticmethod
    def _load_linkedin_connections() -> list[dict]:
        """
        Load and parse the user's LinkedIn Connections.csv export.
        LinkedIn prefixes the file with a few note lines before the real
        header row, so we scan for the line containing "First Name" first.
        Missing/malformed file → empty list, never crashes the pipeline.
        """
        path = Path(config.LINKEDIN_CSV_PATH)
        if not path.exists():
            logger.warning(
                "%s not found — Priority A contacts unavailable. Export your "
                "connections from LinkedIn (Settings & Privacy → Data "
                "privacy → Get a copy of your data → Connections).",
                path.name,
            )
            return []

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                lines = f.readlines()
        except OSError as e:
            logger.error("Failed to read %s: %s", path.name, e)
            return []

        header_idx = next(
            (i for i, line in enumerate(lines) if "First Name" in line), None
        )
        if header_idx is None:
            logger.error(
                "%s doesn't look like a LinkedIn connections export — no "
                "'First Name' header row found.", path.name,
            )
            return []

        rows = list(csv.DictReader(lines[header_idx:]))
        if not rows:
            logger.warning("%s has a header row but no connections listed.", path.name)
        else:
            logger.info("Loaded %d LinkedIn connection(s) from %s", len(rows), path.name)
        return rows

    # ── Source 2: Apollo.io (auto-discovery per company, free tier) ─

    def _search_apollo(self, company: str) -> list[Contact]:
        """
        Discover engineering leads / recruiters at `company` via Apollo.
        Returns [] on any failure — must never crash the pipeline.
        """
        if not config.APOLLO_API_KEY or self._apollo_unavailable:
            return []

        org_id = self._apollo_lookup_organization_id(company)
        if org_id is None:
            return []
        return self._apollo_people_search(company, org_id)

    def _apollo_lookup_organization_id(self, company: str) -> Optional[str]:
        """Resolve a company name to an Apollo organization id (required by people search)."""
        if not usage_tracker.can_call_apollo():
            self._apollo_unavailable = True
            return None
        usage_tracker.record_apollo_call()

        headers = {"x-api-key": config.APOLLO_API_KEY, "Content-Type": "application/json"}
        payload = {"q_organization_name": company, "page": 1, "per_page": 1}
        try:
            resp = requests.post(
                APOLLO_ORG_SEARCH_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("Apollo organization search failed for '%s': %s", company, e)
            return None

        if self._flag_if_plan_inaccessible(data):
            return None
        if "error" in data:
            logger.warning("Apollo organization search error for '%s': %s", company, data["error"])
            return None

        orgs = data.get("organizations") or data.get("accounts") or []
        return orgs[0].get("id") if orgs else None

    def _apollo_people_search(self, company: str, org_id: str) -> list[Contact]:
        """Search for engineering/HR people at a resolved Apollo organization id."""
        if not usage_tracker.can_call_apollo():
            self._apollo_unavailable = True
            return []
        usage_tracker.record_apollo_call()

        titles = config.ENGINEERING_TITLES + config.HR_TITLES
        headers = {"x-api-key": config.APOLLO_API_KEY, "Content-Type": "application/json"}
        payload = {
            "organization_ids": [org_id],
            "person_titles": titles,
            "page": 1,
            "per_page": 10,
        }
        try:
            resp = requests.post(
                APOLLO_PEOPLE_SEARCH_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("Apollo people search failed for '%s': %s", company, e)
            return []

        if self._flag_if_plan_inaccessible(data):
            return []
        if "error" in data:
            logger.warning("Apollo people search error for '%s': %s", company, data["error"])
            return []

        contacts = []
        for person in data.get("people", []):
            name = person.get("name") or " ".join(
                filter(None, [person.get("first_name"), person.get("last_name")])
            )
            role = person.get("title") or ""
            linkedin_url = person.get("linkedin_url")

            # Fallback filter in Python in case the server-side person_titles
            # filter isn't honored by this endpoint.
            role_lower = role.lower()
            if not any(sig in role_lower for sig in titles):
                continue
            if not name or not linkedin_url:
                continue  # skip incomplete records rather than fabricating data

            contacts.append(Contact(
                name=name,
                role=role,
                company=(person.get("organization") or {}).get("name", company),
                linkedin_url=linkedin_url,
                is_first_degree=False,
                university="",
                source="apollo",
            ))
        return contacts

    def _flag_if_plan_inaccessible(self, data: dict) -> bool:
        """
        Detect Apollo's "your plan doesn't include API access" response and
        disable further Apollo calls for the rest of this run instead of
        retrying a permanently-dead key against every company.
        """
        if data.get("error_code") == "API_INACCESSIBLE":
            logger.warning(
                "Apollo returned API_INACCESSIBLE — your current Apollo "
                "plan doesn't include API access at all (this is a plan "
                "restriction, not a bug: confirmed against Apollo's live "
                "API — every search endpoint 403s on a Free plan). "
                "Disabling Priority C/D auto-discovery for the rest of "
                "this run. Upgrade at https://www.apollo.io/pricing if "
                "you want this to work. (%s)",
                data.get("error", ""),
            )
            self._apollo_unavailable = True
            return True
        return False


# ── Fuzzy Company Matching ──────────────────────────────────────────

def _normalize_company(name: str) -> str:
    """Lowercase, strip common suffixes (Inc/Ltd/.com/etc) and punctuation."""
    n = name.lower().strip()
    n = n.replace(".com", "")
    for suffix in _COMPANY_SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    n = _NON_ALNUM_RE.sub("", n)
    return n.strip()


def _companies_match(a: str, b: str) -> bool:
    """True if the normalized forms of two company names overlap either way."""
    na, nb = _normalize_company(a), _normalize_company(b)
    if not na or not nb:
        return False
    return na in nb or nb in na

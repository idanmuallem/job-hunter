"""
Module 2: The Finder Logic (Target Prioritization)
Searches for employees at a target company and selects the single best
contact based on the strict priority hierarchy:
  A) 1st-degree connections
  B) Alumni (BGU / McGill)
  C) Engineering Managers, Tech Leads
  D) HR / Technical Recruiters
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import config

logger = logging.getLogger(__name__)


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
        eng_signals = [
            "engineering manager", "tech lead", "team lead",
            "data engineering manager", "principal engineer",
            "staff engineer", "director of engineering",
            "vp engineering", "head of engineering",
        ]
        if any(signal in role_lower for signal in eng_signals):
            return Priority.C

        hr_signals = [
            "recruiter", "talent acquisition", "hr ",
            "human resources", "people operations",
            "technical recruiter", "sourcer",
        ]
        if any(signal in role_lower for signal in hr_signals):
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
    Finds and ranks contacts at a target company.
    Uses mock data by default — swap _search_company_employees()
    for real Proxycurl / Apollo / LinkedIn API calls.
    """

    def __init__(self):
        self._cache: dict[str, list[Contact]] = {}

    def find_best_contact(self, company: str) -> Optional[Contact]:
        """Convenience wrapper — returns the single top contact."""
        top = self.find_top_contacts(company, n=1)
        return top[0] if top else None

    def find_top_contacts(self, company: str, n: int = 3) -> list[Contact]:
        """
        Search for employees at `company` and return up to `n`
        contacts, ranked by the priority hierarchy (A → B → C → D).
        Returns an empty list if nobody relevant is found.
        """
        employees = self._get_employees(company)
        if not employees:
            logger.warning("No employees found at %s", company)
            return []

        # Keep only contacts that match at least one priority bucket
        ranked = [c for c in employees if c.priority != Priority.NONE]
        if not ranked:
            logger.warning("No prioritized contacts at %s", company)
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

    # ── Data Source ──────────────────────────────────────────────

    def _get_employees(self, company: str) -> list[Contact]:
        """Fetch employees, with simple caching."""
        key = company.lower().strip()
        if key not in self._cache:
            self._cache[key] = self._search_company_employees(company)
        return self._cache[key]

    @staticmethod
    def _search_company_employees(company: str) -> list[Contact]:
        """
        Mock employee data — replace with real API integration.
        Example real implementation using Proxycurl:

            import requests
            headers = {"Authorization": f"Bearer {config.PROXYCURL_API_KEY}"}
            resp = requests.get(
                "https://nubela.co/proxycurl/api/linkedin/company/employees/",
                params={"url": company_linkedin_url, "role_search": "engineering"},
                headers=headers,
            )
            resp.raise_for_status()
            return [Contact(...) for item in resp.json()["employees"]]
        """
        mock_db: dict[str, list[Contact]] = {
            "nvidia": [
                Contact(
                    name="Yael Cohen",
                    role="Engineering Manager – Cloud Platform",
                    company="NVIDIA",
                    linkedin_url="https://linkedin.com/in/yael-cohen-mock",
                    is_first_degree=False,
                    university="Ben-Gurion University of the Negev",
                    department="Cloud Platform",
                ),
                Contact(
                    name="Tom Raviv",
                    role="Senior Backend Developer",
                    company="NVIDIA",
                    linkedin_url="https://linkedin.com/in/tom-raviv-mock",
                    is_first_degree=True,
                    university="Technion",
                    department="AI Infrastructure",
                ),
                Contact(
                    name="Sarah Miller",
                    role="Technical Recruiter",
                    company="NVIDIA",
                    linkedin_url="https://linkedin.com/in/sarah-miller-mock",
                    is_first_degree=False,
                    university="Tel Aviv University",
                    department="Talent Acquisition",
                ),
                Contact(
                    name="Amit Shazar",
                    role="Data Engineer",
                    company="NVIDIA",
                    linkedin_url="https://linkedin.com/in/amit-shazar-mock",
                    is_first_degree=False,
                    university="Ben-Gurion University of the Negev",
                    department="Data Platform",
                ),
            ],
            "wix": [
                Contact(
                    name="Noa Levi",
                    role="Tech Lead – Data Engineering",
                    company="Wix",
                    linkedin_url="https://linkedin.com/in/noa-levi-mock",
                    is_first_degree=False,
                    university="Hebrew University",
                    department="Data Engineering",
                ),
                Contact(
                    name="Daniel Katz",
                    role="HR Business Partner",
                    company="Wix",
                    linkedin_url="https://linkedin.com/in/daniel-katz-mock",
                    is_first_degree=False,
                    university="McGill University",
                    department="People",
                ),
            ],
            "monday.com": [
                Contact(
                    name="Omer Ben-David",
                    role="Director of Engineering – Platform",
                    company="Monday.com",
                    linkedin_url="https://linkedin.com/in/omer-bd-mock",
                    is_first_degree=False,
                    university="Technion",
                    department="Platform",
                ),
            ],
            "cyberark": [
                Contact(
                    name="Lior Azulay",
                    role="Engineering Manager – Identity Security",
                    company="CyberArk",
                    linkedin_url="https://linkedin.com/in/lior-azulay-mock",
                    is_first_degree=False,
                    university="Ben-Gurion University of the Negev",
                    department="Identity Security",
                ),
                Contact(
                    name="Shira Nahum",
                    role="Talent Acquisition Partner",
                    company="CyberArk",
                    linkedin_url="https://linkedin.com/in/shira-nahum-mock",
                    is_first_degree=False,
                    university="IDC Herzliya",
                    department="HR",
                ),
            ],
            "appsflyer": [
                Contact(
                    name="Gal Friedman",
                    role="Technical Recruiter",
                    company="AppsFlyer",
                    linkedin_url="https://linkedin.com/in/gal-friedman-mock",
                    is_first_degree=False,
                    university="Bar-Ilan University",
                    department="Talent",
                ),
            ],
        }

        key = company.lower().strip()
        for db_key, contacts in mock_db.items():
            if db_key in key or key in db_key:
                return contacts
        return []

"""
Module: API Usage Tracker
Hard safety net so this project can never rack up overages: tracks how
many JSearch and Apollo calls have been made this calendar month in a
local api_usage.json file, and refuses further calls once a cap is hit.
Counters reset automatically on the 1st of each month.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def _current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def _empty_usage() -> dict:
    return {"month": _current_month_key(), "jsearch": 0, "apollo": 0}


def _load() -> dict:
    path = config.API_USAGE_FILE
    if not path.exists():
        return _empty_usage()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load %s: %s — resetting usage counters.", path.name, e)
        return _empty_usage()

    if data.get("month") != _current_month_key():
        # New calendar month — reset both counters.
        return _empty_usage()
    return data


def _save(data: dict) -> None:
    try:
        with open(config.API_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        logger.warning("Failed to save %s: %s", config.API_USAGE_FILE.name, e)


def can_call_jsearch() -> bool:
    """Check the JSearch counter before every call — never exceed the monthly cap."""
    data = _load()
    if data["jsearch"] >= config.MAX_MONTHLY_JSEARCH_CALLS:
        logger.warning(
            "Monthly JSearch limit reached — skipping. (%d/%d calls used this month)",
            data["jsearch"], config.MAX_MONTHLY_JSEARCH_CALLS,
        )
        return False
    return True


def record_jsearch_call() -> None:
    data = _load()
    data["jsearch"] += 1
    _save(data)


def can_call_apollo() -> bool:
    """Check the Apollo counter before every call — never exceed the monthly cap."""
    data = _load()
    if data["apollo"] >= config.MAX_MONTHLY_APOLLO_CALLS:
        logger.warning(
            "Monthly Apollo limit reached — skipping. (%d/%d calls used this month)",
            data["apollo"], config.MAX_MONTHLY_APOLLO_CALLS,
        )
        return False
    return True


def record_apollo_call() -> None:
    data = _load()
    data["apollo"] += 1
    _save(data)

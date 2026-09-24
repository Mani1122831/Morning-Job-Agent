"""Smart Filter Agent.

Filters raw jobs down to ones relevant to AI Engineering roles, based on
skill keywords, location keywords, and an optional free-text search term.
"""

from __future__ import annotations

from typing import List

from models.schemas import FilterPreferences, Job
from utils.helpers import contains_any_keyword
from utils.logger import get_logger

logger = get_logger(__name__)


def _job_haystack(job: Job) -> str:
    """Build the searchable text blob for a job (title, tags, description)."""
    return " ".join([job.title, job.company, job.description, " ".join(job.tags)])


def filter_jobs(jobs: List[Job], preferences: FilterPreferences) -> List[Job]:
    """Filter a list of jobs according to the given preferences.

    A job is kept if it matches at least one skill keyword. If
    `require_location_match` is True, it must *also* match at least one
    location keyword. A non-empty `free_text_search` further narrows the
    result to jobs whose text contains that phrase.

    Args:
        jobs: Raw jobs to filter.
        preferences: Filtering criteria.

    Returns:
        The filtered list of jobs, preserving original order.
    """
    matched: List[Job] = []

    for job in jobs:
        haystack = _job_haystack(job)
        location_haystack = f"{job.location} {haystack}"

        skill_match = contains_any_keyword(haystack, preferences.keywords)
        if not skill_match:
            continue

        if preferences.require_location_match:
            location_match = contains_any_keyword(location_haystack, preferences.locations)
            if not location_match:
                continue

        if preferences.free_text_search.strip():
            if preferences.free_text_search.strip().lower() not in haystack.lower():
                continue

        matched.append(job)

    logger.info("Filter Agent kept %d of %d job(s).", len(matched), len(jobs))
    return matched
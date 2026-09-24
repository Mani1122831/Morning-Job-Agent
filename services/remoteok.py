"""Client for the RemoteOK public jobs API.

RemoteOK exposes a free, unauthenticated JSON API at
https://remoteok.com/api. The architecture here is deliberately a thin
adapter (`fetch_remoteok_jobs`) around the raw HTTP call plus a
normalization step (`_normalize_entry`), so that adding LinkedIn, Indeed,
or Naukri later is a matter of writing a sibling module with the same
`List[Job]` return contract — no changes required elsewhere.
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from config import settings
from models.schemas import Job
from utils.helpers import clean_html, make_job_id, utc_now_iso
from utils.logger import get_logger

logger = get_logger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; MorningJobAgent/1.0; "
    "+https://github.com/morning-job-agent)"
)


class JobFetchError(Exception):
    """Raised when the job board cannot be reached or returns bad data."""


def _normalize_entry(entry: Dict[str, Any]) -> Job | None:
    """Convert one raw RemoteOK API entry into a validated `Job`.

    Args:
        entry: A single dict from the RemoteOK API response.

    Returns:
        A `Job` instance, or None if the entry is not an actual job
        posting (RemoteOK's first array element is metadata, not a job).
    """
    title = str(entry.get("position") or entry.get("title") or "").strip()
    company = str(entry.get("company") or "").strip()
    slug = str(entry.get("slug") or "")
    url = str(entry.get("url") or (f"https://remoteok.com/remote-jobs/{slug}" if slug else ""))

    if not title or not company or not url:
        return None

    tags_raw = entry.get("tags") or []
    tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()]

    salary_min = entry.get("salary_min")
    salary_max = entry.get("salary_max")
    if salary_min and salary_max:
        salary = f"${int(salary_min):,} - ${int(salary_max):,}"
    else:
        salary = "Not disclosed"

    location = str(entry.get("location") or "Remote").strip() or "Remote"
    description = clean_html(str(entry.get("description") or ""))
    posted_at = str(entry.get("date") or "")

    job_id = make_job_id(source="remoteok", title=title, company=company, url=url)

    return Job(
        id=job_id,
        source="remoteok",
        title=title,
        company=company,
        location=location,
        salary=salary,
        tags=tags,
        description=description,
        url=url,
        posted_at=posted_at,
        fetched_at=utc_now_iso(),
    )


def fetch_remoteok_jobs(limit: int | None = None) -> List[Job]:
    """Fetch and normalize job postings from the RemoteOK API.

    Args:
        limit: Maximum number of jobs to return. Defaults to
            `settings.max_jobs_per_run`.

    Returns:
        A list of validated `Job` objects. Returns an empty list (never
        raises to the caller for network issues) so the UI can show a
        friendly "no jobs found" state instead of crashing.
    """
    effective_limit = limit if limit is not None else settings.max_jobs_per_run
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

    logger.info("Searching RemoteOK...")
    try:
        response = requests.get(
            settings.remoteok_url,
            headers=headers,
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        raw_data = response.json()
    except requests.exceptions.Timeout as exc:
        logger.error("RemoteOK request timed out: %s", exc)
        return []
    except requests.exceptions.ConnectionError as exc:
        logger.error("RemoteOK connection failed: %s", exc)
        return []
    except requests.exceptions.HTTPError as exc:
        logger.error("RemoteOK returned an HTTP error: %s", exc)
        return []
    except ValueError as exc:
        # response.json() raised — malformed payload.
        logger.error("RemoteOK response was not valid JSON: %s", exc)
        return []
    except requests.exceptions.RequestException as exc:
        logger.error("Unexpected RemoteOK request failure: %s", exc)
        return []

    if not isinstance(raw_data, list):
        logger.error("Unexpected RemoteOK payload shape: %s", type(raw_data))
        return []

    jobs: List[Job] = []
    for entry in raw_data:
        if not isinstance(entry, dict):
            continue
        try:
            job = _normalize_entry(entry)
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the run
            logger.warning("Skipping malformed job entry: %s", exc)
            continue
        if job is not None:
            jobs.append(job)
        if len(jobs) >= effective_limit:
            break

    logger.info("Fetched %d job(s) from RemoteOK.", len(jobs))
    return jobs
"""Job Search Agent.

Responsible for retrieving raw job postings from configured sources and
handing off a clean `List[Job]`. Currently backed by RemoteOK; the
`SOURCE_FETCHERS` registry is the extension point for LinkedIn, Indeed,
or Naukri without touching any other agent.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from models.schemas import Job
from services.remoteok import fetch_remoteok_jobs
from utils.logger import get_logger

logger = get_logger(__name__)

# Registry mapping source name -> fetch function. Adding a new job board
# later is: write `services/linkedin.py::fetch_linkedin_jobs`, register it
# here, and it's live everywhere this agent is used.
SOURCE_FETCHERS: Dict[str, Callable[[], List[Job]]] = {
    "remoteok": fetch_remoteok_jobs,
}


def search_jobs(sources: List[str] | None = None) -> List[Job]:
    """Search all (or a subset of) configured job sources.

    Args:
        sources: Optional list of source names to query, e.g. ["remoteok"].
            Defaults to every registered source.

    Returns:
        A combined, de-duplicated list of `Job` objects across sources.
    """
    selected = sources or list(SOURCE_FETCHERS.keys())
    seen_ids: set[str] = set()
    results: List[Job] = []

    for source_name in selected:
        fetcher = SOURCE_FETCHERS.get(source_name)
        if fetcher is None:
            logger.warning("Unknown job source '%s' requested; skipping.", source_name)
            continue
        try:
            jobs = fetcher()
        except Exception as exc:  # noqa: BLE001 - one source failing must not stop the rest
            logger.error("Source '%s' failed: %s", source_name, exc)
            continue
        for job in jobs:
            if job.id not in seen_ids:
                seen_ids.add(job.id)
                results.append(job)

    logger.info("Job Search Agent found %d unique job(s).", len(results))
    return results
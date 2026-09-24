"""
RemoteOK source adapter.

Kept separate from the existing services/remoteok.py so the existing
workflow remains backward compatible.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from config import settings
from models.schemas import Job


def fetch_remoteok_jobs(
    limit: int | None = None,
) -> list[Job]:
    """Fetch and normalize RemoteOK job listings."""
    response = requests.get(
        settings.remoteok_url,
        headers={
            "User-Agent": "MorningJobAgent/1.0",
            "Accept": "application/json",
        },
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError(
            "RemoteOK returned an unexpected response format."
        )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    jobs: list[Job] = []

    for raw in payload:
        if not isinstance(raw, dict):
            continue

        title = raw.get("position")
        if not title:
            continue

        tags = [
            str(tag).strip()
            for tag in raw.get("tags", []) or []
            if str(tag).strip()
        ]

        jobs.append(
            Job(
                id=str(
                    raw.get("id")
                    or raw.get("slug")
                    or raw.get("url")
                ),
                source="remoteok",
                title=str(title),
                company=str(
                    raw.get("company")
                    or "Unknown Company"
                ),
                location=str(
                    raw.get("location")
                    or "Remote"
                ),
                salary=str(
                    raw.get("salary")
                    or "Not disclosed"
                ),
                tags=tags,
                description=str(
                    raw.get("description")
                    or ""
                ),
                url=str(
                    raw.get("url")
                    or ""
                ),
                posted_at=str(
                    raw.get("date")
                    or ""
                ),
                fetched_at=now,
            )
        )

        if limit and len(jobs) >= limit:
            break

    return jobs

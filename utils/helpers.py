"""Small, dependency-light helper functions used across the codebase."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable


def clean_html(raw_html: str) -> str:
    """Strip HTML tags and collapse whitespace from a raw HTML string.

    Args:
        raw_html: HTML-flavored text (as returned by some job APIs).

    Returns:
        Plain text with tags removed and whitespace normalized.
    """
    if not raw_html:
        return ""
    from bs4 import BeautifulSoup

    text = BeautifulSoup(raw_html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


def make_job_id(*, source: str, title: str, company: str, url: str) -> str:
    """Create a stable, deterministic ID for a job posting.

    Used to de-duplicate jobs across scraper runs so the same posting is
    never written to `data/jobs.csv` twice.

    Args:
        source: The job board the posting came from, e.g. "remoteok".
        title: Job title.
        company: Hiring company name.
        url: Canonical job URL.

    Returns:
        A 16-character hex digest uniquely identifying the posting.
    """
    key = f"{source}|{title.strip().lower()}|{company.strip().lower()}|{url.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def contains_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    """Case-insensitive check for whether any keyword appears in text.

    Args:
        text: Text to search within (e.g. job title + description).
        keywords: Iterable of keywords/phrases to look for.

    Returns:
        True if at least one keyword is found as a substring of text.
    """
    if not text:
        return False
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords if keyword)


def truncate(text: str, max_length: int = 600) -> str:
    """Truncate text to a maximum length, appending an ellipsis if cut.

    Args:
        text: Source text.
        max_length: Maximum number of characters to keep.

    Returns:
        The original text if short enough, otherwise a truncated copy.
    """
    if not text or len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "\u2026"
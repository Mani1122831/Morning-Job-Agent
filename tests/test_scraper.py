"""Tests for services.remoteok.

Covers:
    * The scraper returns a list.
    * Normalized jobs contain all required fields.
    * Network failures are handled gracefully (empty list, no exception).
"""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from models.schemas import Job
from services import remoteok

_SAMPLE_PAYLOAD: List[Dict[str, Any]] = [
    {"legal": "This is metadata, not a job, per the RemoteOK API contract."},
    {
        "position": "AI Engineer",
        "company": "Acme AI",
        "slug": "acme-ai-engineer",
        "url": "https://remoteok.com/remote-jobs/acme-ai-engineer",
        "tags": ["python", "langchain", "rag"],
        "salary_min": 90000,
        "salary_max": 130000,
        "location": "Remote",
        "description": "<p>Build <b>RAG</b> pipelines with LangChain.</p>",
        "date": "2026-09-20T00:00:00+00:00",
    },
    {
        "position": "",
        "company": "Broken Co",
        "url": "",
    },
]


class _FakeResponse:
    """Minimal stand-in for `requests.Response` used in tests."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


def test_fetch_remoteok_jobs_returns_list(monkeypatch) -> None:
    """The scraper must always return a list, never raise on success."""

    def fake_get(*args, **kwargs):
        return _FakeResponse(_SAMPLE_PAYLOAD)

    monkeypatch.setattr(remoteok.requests, "get", fake_get)

    jobs = remoteok.fetch_remoteok_jobs()

    assert isinstance(jobs, list)


def test_fetch_remoteok_jobs_required_fields(monkeypatch) -> None:
    """Every returned job must be a valid Job with all required fields set."""

    def fake_get(*args, **kwargs):
        return _FakeResponse(_SAMPLE_PAYLOAD)

    monkeypatch.setattr(remoteok.requests, "get", fake_get)

    jobs = remoteok.fetch_remoteok_jobs()

    # The metadata row and the malformed row (empty title/url) must be skipped.
    assert len(jobs) == 1

    job = jobs[0]
    assert isinstance(job, Job)
    assert job.title == "AI Engineer"
    assert job.company == "Acme AI"
    assert job.url.startswith("https://")
    assert "python" in job.tags
    assert job.salary == "$90,000 - $130,000"
    assert "RAG" in job.description  # HTML tags stripped, text preserved


def test_fetch_remoteok_jobs_handles_network_failure(monkeypatch) -> None:
    """A connection error must be swallowed, returning an empty list."""

    def fake_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError("simulated network failure")

    monkeypatch.setattr(remoteok.requests, "get", fake_get)

    jobs = remoteok.fetch_remoteok_jobs()

    assert jobs == []


def test_fetch_remoteok_jobs_handles_timeout(monkeypatch) -> None:
    """A timeout must be swallowed, returning an empty list."""

    def fake_get(*args, **kwargs):
        raise requests.exceptions.Timeout("simulated timeout")

    monkeypatch.setattr(remoteok.requests, "get", fake_get)

    jobs = remoteok.fetch_remoteok_jobs()

    assert jobs == []


def test_fetch_remoteok_jobs_handles_bad_json(monkeypatch) -> None:
    """A response that fails to parse as JSON must not crash the caller."""

    class _BadJsonResponse(_FakeResponse):
        def json(self) -> Any:
            raise ValueError("simulated malformed JSON")

    def fake_get(*args, **kwargs):
        return _BadJsonResponse(None)

    monkeypatch.setattr(remoteok.requests, "get", fake_get)

    jobs = remoteok.fetch_remoteok_jobs()

    assert jobs == []


def test_fetch_remoteok_jobs_handles_unexpected_shape(monkeypatch) -> None:
    """A non-list JSON payload (e.g. an error dict) must not crash the caller."""

    def fake_get(*args, **kwargs):
        return _FakeResponse({"error": "rate limited"})

    monkeypatch.setattr(remoteok.requests, "get", fake_get)

    jobs = remoteok.fetch_remoteok_jobs()

    assert jobs == []
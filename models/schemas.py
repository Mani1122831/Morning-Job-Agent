"""Pydantic v2 data models shared across the agents, services, and UI layers."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Job(BaseModel):
    """A single raw job posting, normalized from a job board's API."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., description="Stable, deterministic identifier for de-duplication.")
    source: str = Field(default="remoteok", description="Job board the posting came from.")
    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    location: str = Field(default="Remote")
    salary: str = Field(default="Not disclosed")
    tags: List[str] = Field(default_factory=list)
    description: str = Field(default="")
    url: str = Field(..., min_length=1)
    posted_at: str = Field(default="", description="ISO-8601 timestamp, if known.")
    fetched_at: str = Field(default="", description="ISO-8601 timestamp of when we scraped it.")

    @field_validator("url")
    @classmethod
    def _url_must_look_valid(cls, value: str) -> str:
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("Job URL must start with http:// or https://")
        return value


class JobSummary(BaseModel):
    """AI-generated enrichment for a job posting, produced by Gemini."""

    model_config = ConfigDict(str_strip_whitespace=True)

    required_skills: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    experience_level: str = Field(default="Not specified")
    summary: str = Field(default="", description="Two-sentence plain-English summary.")
    interview_tips: List[str] = Field(default_factory=list)
    generated_by: str = Field(default="gemini")


class JobWithSummary(BaseModel):
    """A job posting joined with its AI-generated summary."""

    job: Job
    summary: Optional[JobSummary] = None

    @property
    def has_summary(self) -> bool:
        """Whether Gemini enrichment succeeded for this job."""
        return self.summary is not None


class FilterPreferences(BaseModel):
    """User-configurable filtering criteria applied by the Filter Agent."""

    keywords: List[str] = Field(
        default_factory=lambda: [
            "AI Engineer",
            "Machine Learning",
            "GenAI",
            "Python",
            "LangChain",
            "RAG",
        ]
    )
    locations: List[str] = Field(
        default_factory=lambda: ["Remote", "Hyderabad", "Bengaluru"]
    )
    free_text_search: str = Field(default="", description="Optional additional keyword search.")
    require_location_match: bool = Field(
        default=False,
        description="If True, a job must also match a location keyword, not just a skill keyword.",
    )
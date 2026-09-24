"""
Data models used by the autonomous Morning Job Agent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _normalise_text_list(value: Any) -> list[str]:
    """
    Convert Gemini JSON arrays containing strings or dictionaries
    into a clean list of strings.
    """
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if not isinstance(value, list):
        return [str(value).strip()] if str(value).strip() else []

    result: list[str] = []

    for item in value:
        if item is None:
            continue

        if isinstance(item, str):
            text = item.strip()
            if text:
                result.append(text)
            continue

        if isinstance(item, dict):
            parts: list[str] = []

            preferred_order = [
                "degree",
                "course",
                "institution",
                "college",
                "university",
                "year",
                "graduation_year",
                "cgpa",
                "percentage",
                "score",
                "description",
                "name",
                "title",
            ]

            used_keys: set[str] = set()

            for key in preferred_order:
                if key in item and item[key] not in (None, ""):
                    parts.append(f"{key.replace('_', ' ').title()}: {item[key]}")
                    used_keys.add(key)

            for key, val in item.items():
                if key in used_keys or val in (None, ""):
                    continue

                parts.append(
                    f"{str(key).replace('_', ' ').title()}: {val}"
                )

            text = " | ".join(parts).strip()

            if text:
                result.append(text)

            continue

        text = str(item).strip()

        if text:
            result.append(text)

    return result


class ResumeProfile(BaseModel):
    """Structured information extracted from a user's resume."""

    full_name: str = ""
    email: str = ""
    phone: str = ""

    education: list[str] = Field(default_factory=list)
    years_experience: float = 0.0

    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    cloud_skills: list[str] = Field(default_factory=list)

    target_roles: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)

    # Gemini sometimes returns structured objects instead of strings.
    # These validators convert them into safe displayable strings.
    @field_validator(
        "education",
        "skills",
        "technologies",
        "cloud_skills",
        "target_roles",
        "projects",
        "certifications",
        mode="before",
    )
    @classmethod
    def normalise_lists(cls, value: Any) -> list[str]:
        return _normalise_text_list(value)


class UserPreferences(BaseModel):
    """Per-user job search and automation preferences."""

    full_name: str = ""
    phone: str = ""

    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    locations: list[str] = Field(
        default_factory=lambda: ["Remote"]
    )

    remote_only: bool = False
    min_match_score: float = 85.0

    auto_apply_enabled: bool = False

    digest_enabled: bool = True
    digest_hour: int = 8


class JobMatchResult(BaseModel):
    """Explainable job-to-user matching result."""

    match_score: float = 0.0

    skill_score: float = 0.0
    role_score: float = 0.0
    location_score: float = 0.0
    experience_score: float = 0.0

    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)

    role_fit: bool = False
    location_fit: bool = False

    explanation: str = ""


class ApplicationResult(BaseModel):
    """Result returned by the application agent."""

    job_id: str
    status: str

    message: str = ""
    application_url: str = ""
    confirmation_text: str = ""
"""
Deterministic and explainable resume-to-job matching.
"""

from __future__ import annotations

import re
from typing import Iterable

from models.agent_models import (
    JobMatchResult,
    ResumeProfile,
    UserPreferences,
)


def _normalize(text: str) -> str:
    """Normalize a phrase for matching."""
    return re.sub(
        r"[^a-z0-9+#.\s-]",
        " ",
        str(text).lower(),
    ).strip()


def _terms(values: Iterable[str]) -> set[str]:
    """Normalize a collection of skill/role/location terms."""
    return {
        _normalize(v)
        for v in values
        if str(v).strip()
    }


def match_job_to_profile(
    job,
    profile: ResumeProfile,
    preferences: UserPreferences,
) -> JobMatchResult:
    """Compute an explainable fit score from explicit user preferences."""
    job_text = _normalize(
        " ".join(
            [
                str(getattr(job, "title", "")),
                str(getattr(job, "description", "")),
                " ".join(getattr(job, "tags", []) or []),
            ]
        )
    )

    skill_terms = _terms(
        list(profile.skills)
        + list(profile.technologies)
        + list(preferences.skills)
    )

    matched = sorted(
        term
        for term in skill_terms
        if term and term in job_text
    )
    missing = sorted(
        term
        for term in skill_terms
        if term and term not in job_text
    )

    skill_fit = (
        len(matched) / max(len(skill_terms), 1)
        if skill_terms
        else 0.0
    )

    role_terms = _terms(
        list(profile.target_roles)
        + list(preferences.target_roles)
    )
    job_title = _normalize(
        getattr(job, "title", "")
    )
    role_fit = (
        any(role in job_title for role in role_terms)
        if role_terms
        else True
    )

    location = _normalize(
        getattr(job, "location", "")
    )
    locations = _terms(preferences.locations)

    location_fit = (
        any(
            ("remote" in location and wanted == "remote")
            or (
                wanted != "remote"
                and wanted
                and wanted in location
            )
            for wanted in locations
        )
        if locations
        else True
    )

    if preferences.remote_only:
        location_fit = "remote" in location

    # Experience is intentionally treated as "fit/unknown" because job
    # descriptions often use free text rather than reliable structured fields.
    experience_fit = True

    score = (
        skill_fit * 55
        + (20 if role_fit else 0)
        + (15 if location_fit else 0)
        + (10 if experience_fit else 0)
    )
    score = round(
        max(0, min(100, score)),
        1,
    )

    explanation = (
        f"{len(matched)} matched skills; "
        f"{'role match' if role_fit else 'role mismatch'}; "
        f"{'location match' if location_fit else 'location mismatch'}"
    )

    return JobMatchResult(
        job_id=str(getattr(job, "id", "")),
        match_score=score,
        matched_skills=matched,
        missing_skills=missing,
        role_fit=role_fit,
        location_fit=location_fit,
        experience_fit=experience_fit,
        explanation=explanation,
        recommended_action=(
            "AUTO_APPLY"
            if score >= preferences.min_match_score
            else "REVIEW"
        ),
    )

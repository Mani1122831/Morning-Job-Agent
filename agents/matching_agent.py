"""
Matching agent facade.
"""

from __future__ import annotations

from models.agent_models import ResumeProfile, UserPreferences
from services.matching_service import (
    match_job_to_profile as _match_job_to_profile,
)


def match_job_to_profile(
    job,
    profile: ResumeProfile,
    preferences: UserPreferences,
):
    """Return an explainable job match result."""
    return _match_job_to_profile(
        job,
        profile,
        preferences,
    )

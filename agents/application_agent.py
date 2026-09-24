"""
Application orchestration agent.
"""

from __future__ import annotations

from database.application_storage import (
    create_application,
    mark_submitted,
)
from models.agent_models import JobMatchResult, UserPreferences
from services.application_service import apply_to_supported_job


def _cover_letter(
    job,
    preferences: UserPreferences,
) -> str:
    """Generate a short factual cover note from user-provided skills."""
    role = str(getattr(job, "title", "the role"))
    company = str(
        getattr(job, "company", "the company")
    )
    skills = ", ".join(
        preferences.skills[:8]
    ) or "relevant technical skills"

    return (
        "Dear Hiring Team,\n\n"
        f"I am interested in the {role} position at {company}. "
        f"My background includes {skills}, and I am interested "
        "in contributing to the role.\n\n"
        "Thank you for your consideration.\n"
    )


def run_application_agent(
    *,
    user_id: int,
    user: dict,
    item,
    match_result: JobMatchResult,
    resume_record: dict,
    preferences: UserPreferences,
) -> dict:
    """Run one user-authorized application attempt."""
    job = item.job

    if match_result.match_score < preferences.min_match_score:
        return {
            "status": "BLOCKED",
            "job": job.title,
            "message": (
                "Below the configured match threshold."
            ),
        }

    application_id = create_application(
        user_id=user_id,
        job_id=str(job.id),
        company=str(job.company),
        role=str(job.title),
        job_url=str(job.url),
        match_score=match_result.match_score,
        status="READY",
        resume_filename=resume_record["filename"],
    )

    result = apply_to_supported_job(
        job=job,
        user=user,
        resume_path=resume_record["path"],
        full_name=preferences.full_name,
        phone=preferences.phone,
        cover_letter=_cover_letter(
            job,
            preferences,
        ),
    )

    if result["status"] == "SUBMITTED":
        mark_submitted(
            application_id,
            result["applied_at"],
        )
    else:
        create_application(
            user_id=user_id,
            job_id=str(job.id),
            company=str(job.company),
            role=str(job.title),
            job_url=str(job.url),
            match_score=match_result.match_score,
            status=result["status"],
            resume_filename=resume_record["filename"],
            error_message=result.get(
                "message",
                "",
            ),
        )

    return {
        "application_id": application_id,
        "status": result["status"],
        "job": job.title,
        "company": job.company,
        "message": result.get(
            "message",
            "",
        ),
    }

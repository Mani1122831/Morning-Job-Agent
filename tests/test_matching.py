from models.agent_models import ResumeProfile, UserPreferences
from services.matching_service import match_job_to_profile


class Job:
    id = "job-1"
    title = "AI Engineer"
    company = "Example"
    location = "Remote"
    tags = ["Python", "RAG", "LangChain"]
    description = "Build AI systems with Python and RAG."


def test_match_score_is_bounded():
    result = match_job_to_profile(
        Job(),
        ResumeProfile(
            skills=["Python", "RAG"],
            target_roles=["AI Engineer"],
        ),
        UserPreferences(
            skills=["Python", "RAG"],
            target_roles=["AI Engineer"],
            locations=["Remote"],
        ),
    )

    assert 0 <= result.match_score <= 100
    assert result.role_fit is True

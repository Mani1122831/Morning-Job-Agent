"""Gemini Summarizer Agent.

Calls Google Gemini for each job to extract required skills, technologies,
experience level, a two-sentence summary, and interview prep tips. Output
is parsed and validated into `JobSummary` Pydantic models. If Gemini is
not configured or the call fails (invalid key, quota, network, bad JSON),
a deterministic fallback summary is produced instead — the pipeline never
crashes and the UI always has something to show.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from models.schemas import Job, JobSummary, JobWithSummary
from utils.helpers import truncate
from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPT_TEMPLATE = """You are an expert technical recruiter analyzing a job posting.

Return ONLY a JSON object (no markdown fences, no commentary) with exactly
these keys:
- "required_skills": array of short strings
- "technologies": array of short strings
- "experience_level": short string (e.g. "Entry-level", "2-4 years", "Senior")
- "summary": exactly two sentences summarizing the role in plain English
- "interview_tips": array of 3-5 short, actionable interview preparation tips

Job title: {title}
Company: {company}
Tags: {tags}
Description: {description}
"""


def _extract_json(raw_text: str) -> Optional[dict]:
    """Extract a JSON object from a model response, tolerating code fences.

    Args:
        raw_text: Raw text returned by the Gemini API.

    Returns:
        A parsed dict, or None if no valid JSON object could be found.
    """
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _fallback_summary(job: Job) -> JobSummary:
    """Build a rule-based summary when Gemini is unavailable or fails.

    Args:
        job: The job to summarize.

    Returns:
        A best-effort `JobSummary` built from the job's own tags/title.
    """
    return JobSummary(
        required_skills=job.tags[:6] or ["Not specified"],
        technologies=job.tags[:6] or ["Not specified"],
        experience_level="Not specified",
        summary=truncate(
            f"{job.title} at {job.company}, located in {job.location}. "
            f"See the full listing for role details and requirements.",
            300,
        ),
        interview_tips=[
            "Research the company's product and recent engineering blog posts.",
            "Review the core technologies listed in the job tags before the call.",
            "Prepare concrete examples of past projects relevant to this role.",
        ],
        generated_by="fallback",
    )


def _call_gemini(job: Job, model) -> Optional[JobSummary]:
    """Invoke the Gemini model for a single job and parse its response.

    Args:
        job: The job to summarize.
        model: An initialized `google.generativeai.GenerativeModel`.

    Returns:
        A validated `JobSummary`, or None if the call/parse failed.
    """
    prompt = _PROMPT_TEMPLATE.format(
        title=job.title,
        company=job.company,
        tags=", ".join(job.tags) if job.tags else "None listed",
        description=truncate(job.description, 3000) or "No description provided.",
    )

    response = model.generate_content(prompt)
    text = getattr(response, "text", "") or ""
    data = _extract_json(text)
    if data is None:
        logger.warning("Gemini response for '%s' was not parseable JSON.", job.title)
        return None

    try:
        return JobSummary(
            required_skills=list(data.get("required_skills", []) or []),
            technologies=list(data.get("technologies", []) or []),
            experience_level=str(data.get("experience_level", "Not specified")),
            summary=str(data.get("summary", "")),
            interview_tips=list(data.get("interview_tips", []) or []),
            generated_by="gemini",
        )
    except Exception as exc:  # noqa: BLE001 - validation errors become a fallback, not a crash
        logger.warning("Gemini summary for '%s' failed validation: %s", job.title, exc)
        return None


def summarize_jobs(jobs: List[Job]) -> List[JobWithSummary]:
    """Generate AI summaries for a batch of jobs.

    Args:
        jobs: Jobs to summarize (typically post-filtering).

    Returns:
        A list of `JobWithSummary`, one per input job, in the same order.
        Every job receives a summary — either from Gemini or the
        deterministic fallback — so downstream code never handles `None`.
    """
    from config import settings

    if not jobs:
        return []

    model = None
    if settings.gemini_configured:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
        except Exception as exc:  # noqa: BLE001 - bad key/quota/import issues all land here
            logger.error("Gemini initialization failed, using fallback summaries: %s", exc)
            model = None
    else:
        logger.info("GEMINI_API_KEY not set; using fallback summaries for all jobs.")

    results: List[JobWithSummary] = []
    for job in jobs:
        summary: Optional[JobSummary] = None
        if model is not None:
            try:
                summary = _call_gemini(job, model)
            except Exception as exc:  # noqa: BLE001 - quota errors, network errors, etc.
                logger.error("Gemini call failed for '%s': %s", job.title, exc)
                summary = None
        if summary is None:
            summary = _fallback_summary(job)
        results.append(JobWithSummary(job=job, summary=summary))

    logger.info("Summarizer Agent produced %d summary(ies).", len(results))
    return results
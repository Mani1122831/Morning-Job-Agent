"""
Gemini-powered resume analysis using the current Google GenAI SDK.
"""

from __future__ import annotations

import json
import re

from google import genai

from config import settings
from models.agent_models import ResumeProfile


class ResumeAnalysisError(RuntimeError):
    """Raised when Gemini resume analysis fails."""


def _extract_json(text: str) -> dict:
    """Extract a JSON object from Gemini output."""
    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    ).strip()

    match = re.search(
        r"\{.*\}",
        cleaned,
        flags=re.DOTALL,
    )

    if not match:
        raise ResumeAnalysisError(
            "Gemini returned no JSON object."
        )

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ResumeAnalysisError(
            "Gemini returned malformed JSON."
        ) from exc


def analyze_resume(resume_text: str) -> ResumeProfile:
    """
    Analyze a resume and extract only facts explicitly present in it.
    """
    if not resume_text.strip():
        raise ResumeAnalysisError(
            "Resume text is empty."
        )

    api_key = settings.gemini_api_key.strip()

    if not api_key:
        raise ResumeAnalysisError(
            "GEMINI_API_KEY is not configured."
        )

    try:
        client = genai.Client(
            api_key=api_key
        )

        prompt = f"""
You are a strict resume information extraction engine.

Extract ONLY information explicitly present in the resume.
Do not invent, guess, or infer facts.

Return ONLY valid JSON using exactly this structure:

{{
  "full_name": "",
  "email": "",
  "phone": "",
  "education": [],
  "years_experience": 0,
  "skills": [],
  "technologies": [],
  "cloud_skills": [],
  "target_roles": [],
  "projects": [],
  "certifications": []
}}

Resume:
{resume_text}
"""

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )

        response_text = getattr(
            response,
            "text",
            None,
        )

        if not response_text:
            raise ResumeAnalysisError(
                "Gemini returned an empty response."
            )

        data = _extract_json(response_text)

        return ResumeProfile.model_validate(data)

    except ResumeAnalysisError:
        raise

    except Exception as exc:
        raise ResumeAnalysisError(
            f"Resume AI analysis failed: {exc}"
        ) from exc
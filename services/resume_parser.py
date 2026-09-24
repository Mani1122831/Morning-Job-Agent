"""
Resume PDF/DOCX text extraction.
"""

from __future__ import annotations

import io
from pathlib import Path

from docx import Document
from pypdf import PdfReader


class ResumeParseError(ValueError):
    """Raised when resume parsing fails."""


def extract_resume_text(file_bytes: bytes, filename: str) -> str:
    """Extract readable text from an uploaded PDF or DOCX."""
    if not file_bytes:
        raise ResumeParseError("The uploaded resume is empty.")

    extension = Path(filename).suffix.lower()

    try:
        if extension == ".pdf":
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
        elif extension == ".docx":
            doc = Document(io.BytesIO(file_bytes))
            text = "\n".join(
                p.text
                for p in doc.paragraphs
                if p.text.strip()
            )
        else:
            raise ResumeParseError(
                "Only PDF and DOCX resumes are supported."
            )
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError(
            f"Unable to read the resume: {exc}"
        ) from exc

    text = text.strip()
    if len(text) < 50:
        raise ResumeParseError(
            "The resume contains too little readable text."
        )

    return text[:30000]

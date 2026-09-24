import pytest

from services.resume_parser import (
    ResumeParseError,
    extract_resume_text,
)


def test_unsupported_resume_type():
    with pytest.raises(ResumeParseError):
        extract_resume_text(
            b"resume content",
            "resume.txt",
        )

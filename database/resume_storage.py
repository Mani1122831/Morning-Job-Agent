"""
Per-user resume file and profile storage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from models.agent_models import ResumeProfile

BASE_DIR = Path("uploads/resumes")


def _safe_filename(filename: str) -> str:
    """Sanitize an uploaded filename."""
    name = Path(filename).name
    name = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        name,
    )
    return name or "resume"


def save_user_resume(
    user_id: int,
    filename: str,
    file_bytes: bytes,
    profile: ResumeProfile,
) -> Path:
    """Save a resume and profile under one user's directory."""
    user_dir = BASE_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    file_path = user_dir / _safe_filename(filename)
    file_path.write_bytes(file_bytes)

    (user_dir / "profile.json").write_text(
        json.dumps(
            profile.model_dump(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return file_path


def get_user_resume(user_id: int) -> dict | None:
    """Get the latest resume and profile for a user."""
    user_dir = BASE_DIR / str(user_id)
    profile_file = user_dir / "profile.json"

    if not user_dir.exists() or not profile_file.exists():
        return None

    files = [
        p
        for p in user_dir.iterdir()
        if p.is_file() and p.name != "profile.json"
    ]

    if not files:
        return None

    latest = max(
        files,
        key=lambda p: p.stat().st_mtime,
    )

    profile = ResumeProfile.model_validate(
        json.loads(
            profile_file.read_text(
                encoding="utf-8"
            )
        )
    )

    return {
        "path": str(latest),
        "filename": latest.name,
        "profile": profile,
    }

"""
Per-user application tracking stored in SQLite.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path("database/users.db")


def _connection() -> sqlite3.Connection:
    """Open the application database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_application_table() -> None:
    """Create the applications table if needed."""
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                application_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                job_id TEXT NOT NULL,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                job_url TEXT NOT NULL,
                match_score REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                applied_at TEXT,
                resume_filename TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                UNIQUE(user_id, job_id)
            )
            """
        )
        conn.commit()


def init_feature_tables() -> None:
    """Initialize all new user-feature tables."""
    from database.user_preferences import init_user_data_table

    init_user_data_table()
    init_application_table()


def create_application(
    user_id: int,
    job_id: str,
    company: str,
    role: str,
    job_url: str,
    match_score: float,
    status: str,
    resume_filename: str = "",
    error_message: str = "",
) -> str:
    """Create or update an application and return its stable ID."""
    init_application_table()

    with _connection() as conn:
        existing = conn.execute(
            """
            SELECT application_id
            FROM applications
            WHERE user_id=? AND job_id=?
            """,
            (user_id, job_id),
        ).fetchone()

        application_id = (
            str(existing["application_id"])
            if existing
            else str(uuid.uuid4())
        )

        conn.execute(
            """
            INSERT INTO applications (
                application_id, user_id, job_id, company, role,
                job_url, match_score, status, resume_filename,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, job_id) DO UPDATE SET
                company=excluded.company,
                role=excluded.role,
                job_url=excluded.job_url,
                match_score=excluded.match_score,
                status=excluded.status,
                resume_filename=excluded.resume_filename,
                error_message=excluded.error_message
            """,
            (
                application_id,
                user_id,
                job_id,
                company,
                role,
                job_url,
                float(match_score),
                status,
                resume_filename,
                error_message,
            ),
        )
        conn.commit()

    return application_id


def mark_submitted(
    application_id: str,
    applied_at: str,
) -> None:
    """Mark a verified submission as submitted."""
    with _connection() as conn:
        conn.execute(
            """
            UPDATE applications
            SET status='SUBMITTED',
                applied_at=?,
                error_message=''
            WHERE application_id=?
            """,
            (applied_at, application_id),
        )
        conn.commit()


def get_user_applications(
    user_id: int,
) -> list[dict[str, Any]]:
    """Return only applications belonging to one user."""
    init_application_table()

    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT application_id, job_id, company, role,
                   job_url, match_score, status, applied_at,
                   resume_filename, error_message
            FROM applications
            WHERE user_id=?
            ORDER BY COALESCE(applied_at, application_id) DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]

"""
Per-user job preferences stored in the existing database/users.db.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from models.agent_models import UserPreferences

DB_PATH = Path("database/users.db")


def _connection() -> sqlite3.Connection:
    """Open the application database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_user_data_table() -> None:
    """Create the user preferences table if needed."""
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                target_roles TEXT NOT NULL DEFAULT '[]',
                skills TEXT NOT NULL DEFAULT '[]',
                locations TEXT NOT NULL DEFAULT '["Remote"]',
                remote_only INTEGER NOT NULL DEFAULT 0,
                min_match_score REAL NOT NULL DEFAULT 85,
                auto_apply_enabled INTEGER NOT NULL DEFAULT 0,
                digest_enabled INTEGER NOT NULL DEFAULT 1,
                digest_hour INTEGER NOT NULL DEFAULT 8
            )
            """
        )
        conn.commit()


def get_user_preferences(user_id: int) -> UserPreferences:
    """Get one user's preferences."""
    init_user_data_table()

    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM user_preferences WHERE user_id=?",
            (user_id,),
        ).fetchone()

    if row is None:
        prefs = UserPreferences()
        save_user_preferences(
            user_id=user_id,
            full_name=prefs.full_name,
            phone=prefs.phone,
            target_roles=prefs.target_roles,
            skills=prefs.skills,
            locations=prefs.locations,
            remote_only=prefs.remote_only,
            min_match_score=prefs.min_match_score,
            auto_apply_enabled=prefs.auto_apply_enabled,
            digest_enabled=prefs.digest_enabled,
            digest_hour=prefs.digest_hour,
        )
        return prefs

    return UserPreferences(
        full_name=row["full_name"],
        phone=row["phone"],
        target_roles=json.loads(row["target_roles"]),
        skills=json.loads(row["skills"]),
        locations=json.loads(row["locations"]),
        remote_only=bool(row["remote_only"]),
        min_match_score=float(row["min_match_score"]),
        auto_apply_enabled=bool(row["auto_apply_enabled"]),
        digest_enabled=bool(row["digest_enabled"]),
        digest_hour=int(row["digest_hour"]),
    )


def save_user_preferences(
    user_id: int,
    full_name: str,
    phone: str,
    target_roles: list[str],
    skills: list[str],
    locations: list[str],
    remote_only: bool,
    min_match_score: float,
    auto_apply_enabled: bool,
    digest_enabled: bool,
    digest_hour: int,
) -> None:
    """Create or update one user's preferences."""
    init_user_data_table()

    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO user_preferences (
                user_id, full_name, phone, target_roles, skills,
                locations, remote_only, min_match_score,
                auto_apply_enabled, digest_enabled, digest_hour
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                phone=excluded.phone,
                target_roles=excluded.target_roles,
                skills=excluded.skills,
                locations=excluded.locations,
                remote_only=excluded.remote_only,
                min_match_score=excluded.min_match_score,
                auto_apply_enabled=excluded.auto_apply_enabled,
                digest_enabled=excluded.digest_enabled,
                digest_hour=excluded.digest_hour
            """,
            (
                user_id,
                full_name.strip(),
                phone.strip(),
                json.dumps(target_roles),
                json.dumps(skills),
                json.dumps(locations),
                int(remote_only),
                float(max(0, min(100, min_match_score))),
                int(auto_apply_enabled),
                int(digest_enabled),
                int(max(0, min(23, digest_hour))),
            ),
        )
        conn.commit()


"""
Autonomous background worker.

Run:
    python -m automation.daily_job

A real deployment should invoke this command from an external scheduler
(cron, GitHub Actions, cloud scheduler, task runner, etc.).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agents.application_agent import run_application_agent
from agents.matching_agent import match_job_to_profile
from agents.summarizer_agent import summarize_jobs
from config import settings
from database.application_storage import init_feature_tables
from database.resume_storage import get_user_resume
from database.user_preferences import get_user_preferences
from services.job_sources.remoteok_source import (
    fetch_remoteok_jobs,
)
from utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path("database/users.db")


def _send_digest(
    recipient: str,
    jobs: list[dict],
) -> tuple[bool, str]:
    """Reuse a simple SMTP sender for background jobs."""
    if not jobs:
        return False, "No matched jobs."

    host = settings.smtp_host
    port = settings.smtp_port
    username = settings.smtp_user
    password = settings.smtp_password

    if not host or not username or not password:
        return False, "SMTP sender credentials are not configured."

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    message = MIMEMultipart("alternative")
    message["Subject"] = (
        f"Morning Job Agent — {len(jobs)} matched jobs"
    )
    message["From"] = username
    message["To"] = recipient

    rows = []
    for job in jobs:
        rows.append(
            f"""
            <tr>
              <td style="padding:14px;border-bottom:1px solid #eee">
                <strong>{job['role']}</strong><br>
                {job['company']}<br>
                Match: {job['match_score']:.0f}%<br>
                Status: {job.get('status', 'MATCHED')}<br>
                <a href="{job['url']}">View job</a>
              </td>
            </tr>
            """
        )

    html = f"""
    <html>
      <body style="font-family:Arial,sans-serif">
        <h2>🌅 Morning Job Agent</h2>
        <p>{len(jobs)} matched job(s) were found.</p>
        <table style="width:100%;border-collapse:collapse">
          {''.join(rows)}
        </table>
      </body>
    </html>
    """

    message.attach(
        MIMEText(html, "html")
    )

    try:
        with smtplib.SMTP(
            host,
            port,
            timeout=20,
        ) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            server.login(
                username,
                password,
            )
            server.send_message(message)

        return True, (
            f"Digest emailed to {recipient}."
        )

    except smtplib.SMTPException as exc:
        logger.error(
            "Background digest failed: %s",
            exc,
        )
        return False, str(exc)


def _users() -> list[dict]:
    """Return registered users."""
    init_feature_tables()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, username, email FROM users"
        ).fetchall()

    return [dict(row) for row in rows]


def run_daily_for_user(
    user: dict,
) -> dict:
    """Run search → match → summarize → apply → email for one user."""
    user_id = int(user["id"])
    prefs = get_user_preferences(user_id)
    resume = get_user_resume(user_id)

    if not resume:
        return {
            "status": "SKIPPED",
            "reason": "No resume profile configured.",
        }

    jobs = fetch_remoteok_jobs(
        limit=settings.max_jobs_per_run
    )

    matches = []

    for job in jobs:
        result = match_job_to_profile(
            job,
            resume["profile"],
            prefs,
        )
        if result.match_score >= prefs.min_match_score:
            matches.append(
                (job, result)
            )

    # Gemini summarization remains part of the existing project.
    enriched = summarize_jobs(
        [job for job, _ in matches],
        limit=settings.max_jobs_per_run,
    )

    enriched_by_id = {
        str(item.job.id): item
        for item in enriched
    }

    digest_rows = []
    applications = []

    for job, match_result in matches:
        item = enriched_by_id.get(
            str(job.id)
        )

        digest_row = {
            "role": job.title,
            "company": job.company,
            "match_score": match_result.match_score,
            "url": job.url,
            "status": "MATCHED",
        }

        if (
            prefs.auto_apply_enabled
            and len(applications)
            < settings.max_auto_apply_per_user
            and item is not None
        ):
            application = run_application_agent(
                user_id=user_id,
                user=user,
                item=item,
                match_result=match_result,
                resume_record=resume,
                preferences=prefs,
            )
            applications.append(application)
            digest_row["status"] = application["status"]

        digest_rows.append(digest_row)

    email_sent = False
    email_message = ""

    if prefs.digest_enabled:
        email_sent, email_message = _send_digest(
            user["email"],
            digest_rows,
        )

    return {
        "status": "COMPLETED",
        "jobs_found": len(jobs),
        "jobs_matched": len(matches),
        "applications_processed": len(applications),
        "email_sent": email_sent,
        "email_message": email_message,
    }


def main() -> None:
    """Run the autonomous workflow for each registered user."""
    for user in _users():
        try:
            result = run_daily_for_user(user)
            logger.info(
                "Daily result for user %s: %s",
                user["id"],
                result,
            )
        except Exception:
            logger.exception(
                "Daily workflow failed for user %s",
                user["id"],
            )


if __name__ == "__main__":
    main()

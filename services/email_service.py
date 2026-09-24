"""Optional SMTP email digest for newly found jobs.

If SMTP credentials are not configured, `send_job_digest` returns a
structured result explaining why nothing was sent, rather than raising —
callers (CLI, scheduler, Streamlit UI) can surface that message to the
user without any special-casing.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from config import settings
from models.schemas import JobWithSummary
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EmailResult:
    """Outcome of an attempted email send."""

    sent: bool
    message: str


def _build_html_body(jobs: List[JobWithSummary]) -> str:
    """Render a simple HTML email body listing the given jobs.

    Args:
        jobs: Jobs (optionally with AI summaries) to include.

    Returns:
        An HTML string suitable for use as an email body.
    """
    rows = []
    for item in jobs:
        summary_html = ""
        if item.summary is not None:
            summary_html = f"<p style='color:#555'>{item.summary.summary}</p>"
        rows.append(
            f"""
            <tr>
              <td style="padding:12px;border-bottom:1px solid #eee">
                <strong>{item.job.title}</strong> — {item.job.company}<br/>
                <span style="color:#888">{item.job.location} · {item.job.salary}</span>
                {summary_html}
                <a href="{item.job.url}">View job</a>
              </td>
            </tr>
            """
        )
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif">
        <h2>Morning Job Agent — {len(jobs)} new AI Engineer job(s)</h2>
        <table style="width:100%;border-collapse:collapse">{''.join(rows)}</table>
      </body>
    </html>
    """



def send_job_digest(jobs: List[JobWithSummary], recipient_email: str) -> EmailResult:
    """Send an HTML digest email summarizing today's matched jobs."""

    if not jobs:
        return EmailResult(sent=False, message="No jobs to email — digest skipped.")

    if not settings.smtp_configured:
        logger.info("SMTP not configured; skipping email digest.")
        return EmailResult(
            sent=False,
            message=(
                "Email digest skipped: SMTP is not configured. "
                "Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, and EMAIL_RECIPIENT "
                "in your .env file to enable this feature."
            ),
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = f"Morning Job Agent: {len(jobs)} new AI Engineer jobs"
    message["From"] = settings.smtp_user
    message["To"] = recipient_email
    message.attach(MIMEText(_build_html_body(jobs), "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()

            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()

            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(
    settings.smtp_user,
    [recipient_email],
    message.as_string(),
)

        logger.info("Email digest sent to %s.", recipient_email)
        return EmailResult(
    sent=True,
    message=f"Digest emailed to {recipient_email}.",
)
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc)
        return EmailResult(
            sent=False,
            message=f"SMTP {exc.smtp_code}: {exc.smtp_error.decode(errors='ignore')}",
        )

    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending digest: %s", exc)
        return EmailResult(sent=False, message=f"Email failed: {exc}")

    except OSError as exc:
        logger.error("Network error while sending digest: %s", exc)
        return EmailResult(
            sent=False,
            message="Email failed: could not reach the SMTP server.",
        )
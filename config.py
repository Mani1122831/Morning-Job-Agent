"""
Centralized configuration for Morning Job Agent.

Loads environment variables from .env and exposes one immutable
Settings instance for the rest of the application.

Important for the multi-user version:
- SMTP_USER is the account used to SEND email.
- SMTP_PASSWORD is its Gmail App Password.
- EMAIL_RECIPIENT is optional and kept only for backward compatibility.
- Actual digest recipients come from the authenticated user's email.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).resolve().parent

DATA_DIR: Path = BASE_DIR / "data"
JOBS_CSV_PATH: Path = DATA_DIR / "jobs.csv"

LOG_DIR: Path = BASE_DIR / "logs"

ASSETS_DIR: Path = BASE_DIR / "assets"


# ---------------------------------------------------------------------------
# Default application options
# ---------------------------------------------------------------------------

DEFAULT_LOCATION_OPTIONS = [
    "Remote",
    "Hyderabad",
    "Bengaluru",
]

DEFAULT_ROLE_KEYWORDS = [
    "AI Engineer",
    "Machine Learning",
    "GenAI",
    "Python",
    "LangChain",
    "RAG",
]


# ---------------------------------------------------------------------------
# Environment helper functions
# ---------------------------------------------------------------------------

def _get_env(name: str, default: str = "") -> str:
    """Read and clean a string environment variable."""
    return os.getenv(name, default).strip()


def _get_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable safely."""
    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_int(name: str, default: int) -> int:
    """Parse an integer environment variable safely."""
    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    # ---------------- Gemini ----------------

    gemini_api_key: str = field(
        default_factory=lambda: _get_env("GEMINI_API_KEY")
    )

    gemini_model: str = field(
        default_factory=lambda: _get_env(
            "GEMINI_MODEL",
            "gemini-2.5-flash",
        )
    )

    # ---------------- SMTP ----------------

    smtp_host: str = field(
        default_factory=lambda: _get_env(
            "SMTP_HOST",
            "smtp.gmail.com",
        )
    )

    smtp_port: int = field(
        default_factory=lambda: _get_int(
            "SMTP_PORT",
            587,
        )
    )

    smtp_user: str = field(
        default_factory=lambda: _get_env("SMTP_USER")
    )

    smtp_password: str = field(
        default_factory=lambda: _get_env("SMTP_PASSWORD")
    )

    smtp_use_tls: bool = field(
        default_factory=lambda: _get_bool(
            "SMTP_USE_TLS",
            True,
        )
    )

    # Kept for compatibility with older project files.
    # Multi-user email delivery does NOT use this as the recipient.
    email_recipient: str = field(
        default_factory=lambda: _get_env("EMAIL_RECIPIENT")
    )

    # ---------------- Job source ----------------

    remoteok_url: str = field(
        default_factory=lambda: _get_env(
            "REMOTEOK_URL",
            "https://remoteok.com/api",
        )
    )

    request_timeout_seconds: int = field(
        default_factory=lambda: _get_int(
            "REQUEST_TIMEOUT_SECONDS",
            15,
        )
    )

    max_jobs_per_run: int = field(
        default_factory=lambda: _get_int(
            "MAX_JOBS_PER_RUN",
            40,
        )
    )

    # ---------------- Scheduler ----------------

    scheduler_hour: int = field(
        default_factory=lambda: _get_int(
            "SCHEDULER_HOUR",
            8,
        )
    )

    scheduler_minute: int = field(
        default_factory=lambda: _get_int(
            "SCHEDULER_MINUTE",
            0,
        )
    )

    # ---------------- Logging ----------------

    log_level: str = field(
        default_factory=lambda: _get_env(
            "LOG_LEVEL",
            "INFO",
        ).upper()
    )



    # ---------------- Autonomous application ----------------

    auto_apply_enabled: bool = field(
        default_factory=lambda: _get_bool("AUTO_APPLY_ENABLED", False)
    )

    auto_apply_min_match_score: int = field(
        default_factory=lambda: _get_int("AUTO_APPLY_MIN_MATCH_SCORE", 85)
    )

    auto_apply_hosts: str = field(
        default_factory=lambda: _get_env(
            "AUTO_APPLY_HOSTS",
            "boards.greenhouse.io,jobs.lever.co",
        )
    )

    max_auto_apply_per_user: int = field(
        default_factory=lambda: _get_int("MAX_AUTO_APPLY_PER_USER", 5)
    )

    # -----------------------------------------------------------------------
    # Validation / status properties
    # -----------------------------------------------------------------------

    @property
    def gemini_configured(self) -> bool:
        """Return True when a Gemini API key is configured."""
        return bool(self.gemini_api_key)

    @property
    def smtp_configured(self) -> bool:
        """
        Return True when the application has enough sender credentials
        to connect to the SMTP server.

        EMAIL_RECIPIENT is intentionally NOT required because the
        recipient is determined from the authenticated user's account.
        """
        return bool(
            self.smtp_host
            and self.smtp_user
            and self.smtp_password
        )

    @property
    def smtp_sender(self) -> str:
        """Return the configured SMTP sender address."""
        return self.smtp_user

    @property
    def scheduler_configured(self) -> bool:
        """Return whether scheduler settings contain valid ranges."""
        return (
            0 <= self.scheduler_hour <= 23
            and 0 <= self.scheduler_minute <= 59
        )

    @property
    def application_ready(self) -> bool:
        """Return whether the core application configuration is usable."""
        return self.gemini_configured and self.smtp_configured


# ---------------------------------------------------------------------------
# Global settings instance
# ---------------------------------------------------------------------------

settings = Settings()


# ---------------------------------------------------------------------------
# Ensure runtime directories exist
# ---------------------------------------------------------------------------

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

ASSETS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)
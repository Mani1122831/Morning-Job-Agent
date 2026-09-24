"""Application-wide logging configuration.

Every module in this project logs through `get_logger(__name__)` instead of
using `print`. Logs are written both to stdout (for Streamlit Cloud /
Render / Railway log viewers) and to a rotating file under `logs/`.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOG_DIR, settings

_LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


def _configure_root() -> None:
    """Attach handlers to the root logger exactly once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    try:
        file_handler = RotatingFileHandler(
            LOG_DIR / "morning_job_agent.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Read-only filesystems (some hosting platforms) should not crash
        # the app just because file logging is unavailable.
        root.warning("File logging unavailable; continuing with stdout only.")

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name.

    Args:
        name: Typically `__name__` of the calling module.

    Returns:
        A `logging.Logger` instance with handlers already attached.
    """
    _configure_root()
    return logging.getLogger(name)
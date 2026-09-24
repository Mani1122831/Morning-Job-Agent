"""APScheduler-based job runner.

Supports three modes:
    * daily  — runs once per day at `settings.scheduler_hour`:`scheduler_minute`.
    * hourly — runs at the top of every hour.
    * manual — the scheduler is not started; callers trigger runs directly.

The scheduler itself only knows *when* to run — *what* to run is injected
as a callback, keeping this module decoupled from the LangGraph workflow.
"""

from __future__ import annotations

from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

JobCallback = Callable[[], None]


class JobScheduler:
    """Thin wrapper around `BackgroundScheduler` with named run modes."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()
        self._job_id = "morning_job_agent_run"

    def start_daily(self, callback: JobCallback) -> None:
        """Schedule `callback` to run once per day at the configured time.

        Args:
            callback: Zero-argument function to invoke on each trigger.
        """
        trigger = CronTrigger(hour=settings.scheduler_hour, minute=settings.scheduler_minute)
        self._replace_job(callback, trigger)
        logger.info(
            "Daily schedule active: %02d:%02d.", settings.scheduler_hour, settings.scheduler_minute
        )

    def start_hourly(self, callback: JobCallback) -> None:
        """Schedule `callback` to run once every hour.

        Args:
            callback: Zero-argument function to invoke on each trigger.
        """
        trigger = IntervalTrigger(hours=1)
        self._replace_job(callback, trigger)
        logger.info("Hourly schedule active.")

    def _replace_job(self, callback: JobCallback, trigger) -> None:
        """Remove any existing scheduled job and add a new one.

        Args:
            callback: Function to schedule.
            trigger: An APScheduler trigger instance.
        """
        if self._scheduler.get_job(self._job_id):
            self._scheduler.remove_job(self._job_id)
        self._scheduler.add_job(callback, trigger, id=self._job_id, replace_existing=True)
        if not self._scheduler.running:
            self._scheduler.start()

    def stop(self) -> None:
        """Stop the background scheduler if it is running."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    @property
    def next_run_time(self) -> Optional[str]:
        """ISO-formatted next run time, or None if nothing is scheduled."""
        job = self._scheduler.get_job(self._job_id)
        if job is None or job.next_run_time is None:
            return None
        return job.next_run_time.isoformat()


# A module-level singleton keeps Streamlit's rerun model from spawning
# duplicate background schedulers on every script rerun.
scheduler = JobScheduler()
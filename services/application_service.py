"""
Controlled browser application service.

The service is intentionally conservative:
- Only HTTPS allowlisted application hosts are automated.
- RemoteOK pages may be inspected to locate a supported ATS application URL.
- CAPTCHA/MFA/OTP/human verification stops the flow.
- The service only returns SUBMITTED after a visible confirmation.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_ALLOWED_HOSTS = {
    "boards.greenhouse.io",
    "jobs.lever.co",
}


def allowed_hosts() -> set[str]:
    """Read the application-host allowlist from configuration."""
    raw = os.getenv(
        "AUTO_APPLY_HOSTS",
        ",".join(sorted(DEFAULT_ALLOWED_HOSTS)),
    )
    return {
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    }


def _host(url: str) -> str:
    """Return the lowercase host for a URL."""
    return (urlparse(url).hostname or "").lower()


def is_supported_application_url(url: str) -> bool:
    """Return True only for HTTPS allowlisted hosts."""
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and _host(url) in allowed_hosts()
    )


def resolve_application_url(job_url: str) -> str | None:
    """
    Resolve a RemoteOK/job-listing page to a supported ATS application URL.

    If the provided URL is already supported, return it.
    Otherwise inspect the HTML for links to configured supported hosts.
    """
    if is_supported_application_url(job_url):
        return job_url

    try:
        response = requests.get(
            job_url,
            headers={
                "User-Agent": "MorningJobAgent/1.0",
                "Accept": "text/html",
            },
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            if is_supported_application_url(href):
                return href

    except Exception:
        return None

    return None


def _fill_first(
    page,
    selectors: list[str],
    value: str,
) -> bool:
    """Fill the first matching selector."""
    if not value:
        return False

    for selector in selectors:
        locator = page.locator(selector)
        if locator.count():
            try:
                locator.first.fill(value)
                return True
            except Exception:
                continue

    return False


def apply_to_supported_job(
    *,
    job,
    user: dict,
    resume_path: str,
    full_name: str,
    phone: str,
    cover_letter: str,
) -> dict:
    """Attempt a supported ATS application."""
    application_url = resolve_application_url(
        str(getattr(job, "url", ""))
    )

    if not application_url:
        return {
            "status": "BLOCKED",
            "message": (
                "No supported HTTPS application page was found "
                "for this job."
            ),
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "FAILED",
            "message": (
                "Playwright is not installed. "
                "Run `pip install playwright` and "
                "`playwright install`."
            ),
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True
            )
            page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 1000,
                }
            )

            page.goto(
                application_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            body = page.locator("body").inner_text().lower()

            blocking_terms = [
                "captcha",
                "verify you are human",
                "two-factor",
                "two factor",
                "2fa",
                "otp",
                "one-time password",
                "one time password",
            ]

            if any(
                term in body
                for term in blocking_terms
            ):
                browser.close()
                return {
                    "status": "MANUAL_ACTION_REQUIRED",
                    "message": (
                        "CAPTCHA/MFA/OTP/human verification "
                        "was detected."
                    ),
                    "application_url": application_url,
                }

            _fill_first(
                page,
                [
                    'input[name="name"]',
                    'input[name="full_name"]',
                    'input[id*="name"]',
                    'input[autocomplete="name"]',
                ],
                full_name or user.get("username", ""),
            )

            _fill_first(
                page,
                [
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[autocomplete="email"]',
                ],
                user.get("email", ""),
            )

            _fill_first(
                page,
                [
                    'input[type="tel"]',
                    'input[name="phone"]',
                    'input[autocomplete="tel"]',
                ],
                phone,
            )

            file_inputs = page.locator(
                'input[type="file"]'
            )
            if file_inputs.count():
                file_inputs.first.set_input_files(
                    resume_path
                )

            _fill_first(
                page,
                [
                    'textarea[name*="cover"]',
                    'textarea[id*="cover"]',
                    'textarea[placeholder*="cover"]',
                ],
                cover_letter,
            )

            submit_buttons = page.get_by_role(
                "button",
                name=re.compile(
                    r"submit application|submit|apply",
                    re.IGNORECASE,
                ),
            )

            if not submit_buttons.count():
                browser.close()
                return {
                    "status": "MANUAL_ACTION_REQUIRED",
                    "message": (
                        "No supported submit button was found."
                    ),
                    "application_url": application_url,
                }

            submit_buttons.first.click()
            page.wait_for_timeout(2500)

            confirmation = page.locator(
                "body"
            ).inner_text().lower()

            confirmation_phrases = [
                "application submitted",
                "application received",
                "thank you for applying",
                "thanks for applying",
            ]

            verified = any(
                phrase in confirmation
                for phrase in confirmation_phrases
            )

            browser.close()

            if verified:
                return {
                    "status": "SUBMITTED",
                    "message": (
                        "Application confirmation detected."
                    ),
                    "application_url": application_url,
                    "applied_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

            return {
                "status": "MANUAL_ACTION_REQUIRED",
                "message": (
                    "The form was reached, but a valid "
                    "submission confirmation was not detected."
                ),
                "application_url": application_url,
            }

    except Exception as exc:
        return {
            "status": "FAILED",
            "message": f"Application automation failed: {exc}",
            "application_url": application_url,
        }

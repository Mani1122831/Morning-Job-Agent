"""
Morning Job Agent — Premium Multi-User AI Job Assistant.
Run:
    streamlit run app.py
This single-file entry point provides:
- Premium login / registration UI
- SQLite user accounts with salted PBKDF2 password hashing
- Per-user sessions and logout
- LangGraph job workflow integration
- Gemini status display
- RemoteOK-powered job dashboard
- Per-user SMTP email digest
- Scheduler controls
- Robust CSV loading and metrics
"""
from __future__ import annotations
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import sqlite3
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional
import pandas as pd
import streamlit as st
from agents.workflow import run_workflow
from agents.application_agent import run_application_agent
from agents.matching_agent import match_job_to_profile
from agents.resume_agent import analyze_resume
from config import JOBS_CSV_PATH, settings
from database.application_storage import (
    get_user_applications,
    init_feature_tables,
)
from database.resume_storage import get_user_resume, save_user_resume
from database.user_preferences import get_user_preferences, save_user_preferences
from models.agent_models import ResumeProfile
from services.resume_parser import extract_resume_text
from models.schemas import FilterPreferences, Job, JobSummary, JobWithSummary
from services.scheduler import scheduler
from utils.logger import get_logger
logger = get_logger(__name__)
# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
APP_TITLE = "Morning Job Agent"
AUTH_DB_PATH = Path("database/users.db")
PBKDF2_ITERATIONS = 310_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🌅",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ---------------------------------------------------------------------------
# Authentication database
# ---------------------------------------------------------------------------
def _get_db_connection() -> sqlite3.Connection:
    """Return a SQLite connection for the local user database."""
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection
def _init_database() -> None:
    """Create the user table when it does not already exist."""
    with _get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
def _hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    """Hash a password with a random salt using PBKDF2-HMAC-SHA256."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return digest.hex(), salt.hex()
def _verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash."""
    calculated_hash, _ = _hash_password(password, salt_hex)
    return hmac.compare_digest(calculated_hash, password_hash)
def _valid_email(email: str) -> bool:
    """Return True when an email has a basic valid structure."""
    return bool(EMAIL_RE.match(email.strip()))
def _create_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """Create a user account after validating and hashing credentials."""
    username = username.strip()
    email = email.strip().lower()
    if len(username) < 3:
        return False, "Username must contain at least 3 characters."
    if not _valid_email(email):
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    password_hash, salt = _hash_password(password)
    try:
        with _get_db_connection() as connection:
            connection.execute(
                """
                INSERT INTO users (username, email, password_hash, salt)
                VALUES (?, ?, ?, ?)
                """,
                (username, email, password_hash, salt),
            )
            connection.commit()
        return True, "Account created successfully. You can now sign in."
    except sqlite3.IntegrityError:
        return False, "That username or email is already registered."
def _authenticate_user(email: str, password: str) -> Optional[dict]:
    """Authenticate a user and return safe account fields."""
    email = email.strip().lower()
    with _get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT id, username, email, password_hash, salt
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()
    if row is None:
        return None
    if not _verify_password(password, row["password_hash"], row["salt"]):
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
    }
# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _init_session() -> None:
    """Initialize Streamlit authentication session state."""
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("last_run_enriched", [])
    st.session_state.setdefault("last_run_saved", 0)
def _login_user(user: dict) -> None:
    """Persist the authenticated user in the Streamlit session."""
    st.session_state["authenticated"] = True
    st.session_state["user"] = user
def _logout_user() -> None:
    """Clear authentication state and dashboard run state."""
    st.session_state["authenticated"] = False
    st.session_state["user"] = None
    st.session_state["last_run_enriched"] = []
    st.session_state["last_run_saved"] = 0
def _current_user() -> Optional[dict]:
    """Return the currently authenticated user."""
    return st.session_state.get("user")
# ---------------------------------------------------------------------------
# Premium CSS
# ---------------------------------------------------------------------------
def _inject_css() -> None:
    """Inject premium glassmorphism styling for authentication and dashboard."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        :root {
            --bg-1: #05030b;
            --bg-2: #0b0820;
            --panel: rgba(255,255,255,0.065);
            --border: rgba(255,255,255,0.105);
            --text: #f7f5ff;
            --muted: #aaa5bf;
            --purple: #8b5cf6;
            --blue: #3b82f6;
            --cyan: #22d3ee;
        }
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        .stApp {
            position: relative;
            min-height: 100vh;
            background:
                radial-gradient(circle at 50% -12%, rgba(124,58,237,.18), transparent 30%),
                linear-gradient(135deg, #05020f 0%, #09051a 38%, #040713 70%, #020308 100%);
            color: var(--text);
            overflow-x: hidden;
        }
        .stApp::before {
            content: "";
            position: fixed;
            inset: -18%;
            z-index: -2;
            background:
                radial-gradient(circle at 12% 18%, rgba(124,58,237,.28), transparent 22%),
                radial-gradient(circle at 86% 14%, rgba(37,99,235,.23), transparent 20%),
                radial-gradient(circle at 64% 72%, rgba(34,211,238,.13), transparent 22%),
                radial-gradient(circle at 28% 88%, rgba(168,85,247,.12), transparent 22%);
            filter: blur(60px) saturate(125%);
            animation: auroraDrift 22s ease-in-out infinite alternate;
            pointer-events: none;
        }
        .stApp::after {
            content: "";
            position: fixed;
            inset: 0;
            z-index: -1;
            pointer-events: none;
            opacity: .20;
            background-image:
                linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
            background-size: 42px 42px;
            mask-image: linear-gradient(to bottom, rgba(0,0,0,.9), transparent 85%);
        }
        @keyframes auroraDrift {
            0% { transform: translate3d(-2%, -1%, 0) scale(1); }
            50% { transform: translate3d(2%, 1%, 0) scale(1.04); }
            100% { transform: translate3d(-1%, 3%, 0) scale(1.08); }
        }
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(8,6,20,.94), rgba(4,5,14,.90));
            border-right: 1px solid rgba(139,92,246,.12);
            backdrop-filter: blur(18px);
        }
        .hero {
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,.10);
            border-radius: 28px;
            padding: 2.7rem 2.7rem 2.4rem;
            margin-bottom: 1.5rem;
            background:
                linear-gradient(115deg, rgba(124,58,237,.97), rgba(67,56,202,.95) 52%, rgba(37,99,235,.97));
            box-shadow: 0 24px 70px rgba(67,56,202,.28);
        }
        .hero::after {
            content: "";
            position: absolute;
            width: 220px;
            height: 220px;
            right: -75px;
            top: -75px;
            border-radius: 50%;
            background: rgba(255,255,255,.11);
            filter: blur(4px);
        }
        .hero-badge {
            display: inline-flex;
            align-items: center;
            padding: .38rem .85rem;
            border: 1px solid rgba(255,255,255,.18);
            border-radius: 999px;
            background: rgba(255,255,255,.12);
            backdrop-filter: blur(8px);
            color: #fff;
            font-size: .76rem;
            font-weight: 700;
            letter-spacing: .04em;
            margin-bottom: .95rem;
        }
        .hero h1 {
            margin: 0;
            color: #fff;
            font-size: clamp(2rem, 4vw, 2.9rem);
            font-weight: 800;
            line-height: 1.08;
        }
        .hero p {
            max-width: 760px;
            margin: .8rem 0 0;
            color: rgba(255,255,255,.9);
            font-size: 1rem;
            line-height: 1.65;
        }
        .glass-card {
            background: linear-gradient(145deg, rgba(255,255,255,.065), rgba(255,255,255,.028));
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 1.35rem 1.45rem;
            margin-bottom: 1rem;
            backdrop-filter: blur(16px);
            box-shadow: 0 15px 45px rgba(0,0,0,.22);
            transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
        }
        .glass-card:hover {
            transform: translateY(-2px);
            border-color: rgba(139,92,246,.38);
            box-shadow: 0 20px 55px rgba(91,71,177,.18);
        }
        .job-title {
            color: #fff;
            font-size: 1.12rem;
            font-weight: 750;
            margin-bottom: .18rem;
        }
        .job-company {
            color: #c6bcf6;
            font-size: .93rem;
            font-weight: 600;
        }
        .job-meta {
            margin-top: .45rem;
            color: #a9a3be;
            font-size: .82rem;
        }
        .tag-pill {
            display: inline-block;
            margin: .35rem .25rem 0 0;
            padding: .20rem .62rem;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,.10);
            background: linear-gradient(115deg, rgba(124,58,237,.25), rgba(37,99,235,.22));
            color: #e7e0ff;
            font-size: .72rem;
        }
        .account-card {
            padding: 1rem 1.05rem;
            border: 1px solid rgba(139,92,246,.20);
            border-radius: 16px;
            background: linear-gradient(135deg, rgba(124,58,237,.12), rgba(37,99,235,.08));
            margin: .5rem 0 1rem;
        }
        .auth-wrap {
            max-width: 530px;
            margin: 8vh auto 0;
        }
        .auth-card {
            padding: 2rem 2rem 1.6rem;
            border-radius: 26px;
            border: 1px solid rgba(255,255,255,.09);
            background: rgba(10,8,22,.78);
            backdrop-filter: blur(20px);
            box-shadow: 0 30px 90px rgba(0,0,0,.42);
        }
        .auth-logo {
            width: 64px;
            height: 64px;
            display: grid;
            place-items: center;
            margin: 0 auto 1rem;
            border-radius: 18px;
            background: linear-gradient(135deg, #7c3aed, #2563eb);
            box-shadow: 0 12px 35px rgba(99,102,241,.28);
            font-size: 1.8rem;
        }
        .auth-title {
            text-align: center;
            color: #fff;
            font-size: 2rem;
            font-weight: 800;
            margin-bottom: .3rem;
        }
        .auth-subtitle {
            text-align: center;
            color: #aba5be;
            margin-bottom: 1.4rem;
            line-height: 1.5;
        }
        .stButton > button,
        .stDownloadButton > button,
        .stLinkButton > a {
            border-radius: 13px !important;
            border: 1px solid rgba(255,255,255,.10) !important;
            background: linear-gradient(115deg, #7c3aed, #2563eb) !important;
            color: white !important;
            font-weight: 700 !important;
            box-shadow: 0 10px 28px rgba(67,56,202,.20) !important;
            transition: transform .15s ease, box-shadow .15s ease !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stLinkButton > a:hover {
            transform: translateY(-1px);
            box-shadow: 0 16px 36px rgba(67,56,202,.30) !important;
        }
        [data-testid="stMetric"] {
            padding: .9rem 1rem;
            border-radius: 18px;
            border: 1px solid rgba(255,255,255,.08);
            background: rgba(255,255,255,.035);
        }
        [data-testid="stExpander"] {
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            background: rgba(255,255,255,.025);
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        div[data-baseweb="textarea"] > div {
            border-radius: 13px !important;
            background: rgba(255,255,255,.045) !important;
            border-color: rgba(255,255,255,.08) !important;
        }
        .status-good {
            display: inline-block;
            padding: .28rem .65rem;
            border-radius: 999px;
            background: rgba(16,185,129,.12);
            border: 1px solid rgba(16,185,129,.20);
            color: #86efac;
            font-size: .75rem;
            font-weight: 700;
        }
        .muted {
            color: #aaa5bf;
            font-size: .84rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
# ---------------------------------------------------------------------------
# Authentication UI
# ---------------------------------------------------------------------------
def _render_auth_page() -> None:
    """Render a premium login and registration experience."""
    st.markdown(
        """
        <div class="auth-wrap">
            <div class="auth-card">
                <div class="auth-logo">🌅</div>
                <div class="auth-title">Morning Job Agent</div>
                <div class="auth-subtitle">
                    AI-powered job discovery, personalized for every user.
                    <br>Find roles. Understand them. Apply smarter.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, center, _ = st.columns([1, 2, 1])
    with center:
        login_tab, signup_tab = st.tabs(["🔐 Sign in", "✨ Create account"])
        with login_tab:
            st.markdown("#### Welcome back")
            email = st.text_input(
                "Email address",
                placeholder="you@example.com",
                key="auth_login_email",
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                key="auth_login_password",
            )
            if st.button("Sign in to your workspace", use_container_width=True):
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    user = _authenticate_user(email, password)
                    if user:
                        _login_user(user)
                        st.success("Login successful.")
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")
        with signup_tab:
            st.markdown("#### Create your workspace")
            name = st.text_input(
                "Username",
                placeholder="e.g. manikanta",
                key="auth_signup_name",
            )
            email = st.text_input(
                "Email address",
                placeholder="you@example.com",
                key="auth_signup_email",
            )
            password = st.text_input(
                "Create password",
                type="password",
                placeholder="At least 8 characters",
                key="auth_signup_password",
            )
            confirm = st.text_input(
                "Confirm password",
                type="password",
                placeholder="Repeat your password",
                key="auth_signup_confirm",
            )
            if st.button("Create my account", use_container_width=True):
                if password != confirm:
                    st.error("Passwords do not match.")
                else:
                    ok, message = _create_user(name, email, password)
                    if ok:
                        st.success(message)
                    else:
                        st.error(message)
        st.caption(
            "🔒 Your password is stored as a salted PBKDF2 hash. "
            "The app never stores your plaintext password."
        )
# ---------------------------------------------------------------------------
# Dashboard data functions
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_jobs_dataframe(cache_key: float) -> pd.DataFrame:
    """Load jobs.csv safely into a DataFrame."""
    del cache_key
    if not JOBS_CSV_PATH.exists() or JOBS_CSV_PATH.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(JOBS_CSV_PATH)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as exc:
        logger.error("Failed to read jobs.csv: %s", exc)
        return pd.DataFrame()
def _csv_cache_key() -> float:
    """Return jobs.csv modification time for Streamlit cache invalidation."""
    return JOBS_CSV_PATH.stat().st_mtime if JOBS_CSV_PATH.exists() else 0.0
def _dataframe_to_items(df: pd.DataFrame) -> List[JobWithSummary]:
    """Convert saved CSV rows to validated job objects for rendering."""
    items: List[JobWithSummary] = []
    for _, row in df.iterrows():
        try:
            def safe_text(column: str, default: str = "") -> str:
                value = row.get(column, default)
                if pd.isna(value):
                    return default
                return str(value)
            tags_raw = safe_text("tags")
            required_raw = safe_text("required_skills")
            technologies_raw = safe_text("technologies")
            tips_raw = safe_text("interview_tips")
            job = Job(
                id=safe_text("id"),
                source=safe_text("source", "remoteok"),
                title=safe_text("title", "Untitled Role"),
                company=safe_text("company", "Unknown Company"),
                location=safe_text("location", "Remote"),
                salary=safe_text("salary", "Not disclosed"),
                tags=[x for x in tags_raw.split("|") if x],
                description=safe_text("description"),
                url=safe_text("url"),
                posted_at=safe_text("posted_at"),
                fetched_at=safe_text("fetched_at"),
            )
            summary = JobSummary(
                required_skills=[x for x in required_raw.split("|") if x],
                technologies=[x for x in technologies_raw.split("|") if x],
                experience_level=safe_text("experience_level", "Not specified"),
                summary=safe_text("summary"),
                interview_tips=[x for x in tips_raw.split("|") if x],
                generated_by=safe_text("generated_by", "fallback"),
            )
            items.append(JobWithSummary(job=job, summary=summary))
        except Exception as exc:
            logger.warning("Skipping malformed CSV row: %s", exc)
    return items
# ---------------------------------------------------------------------------
# Resume, profile, matching and application features
# ---------------------------------------------------------------------------
def _render_resume_profile(user_id: int) -> ResumeProfile | None:
    """Render per-user resume upload, AI analysis and preferences."""
    st.markdown("## 📄 Resume & AI Profile")
    existing = get_user_resume(user_id)
    profile = (
        existing.get("profile")
        if existing
        else None
    )
    upload = st.file_uploader(
        "Upload your resume",
        type=["pdf", "docx"],
        key="resume_upload",
        help="PDF/DOCX only. Your resume is stored under your account.",
    )
    col1, col2 = st.columns([1.1, 1])
    with col1:
        if upload is not None:
            if upload.size > 5 * 1024 * 1024:
                st.error("Resume must be 5 MB or smaller.")
            elif st.button(
                "🧠 Analyze Resume with Gemini",
                key="analyze_resume_button",
                use_container_width=True,
            ):
                try:
                    raw_text = extract_resume_text(
                        upload.getvalue(),
                        upload.name,
                    )
                    with st.spinner("Reading your resume and building your profile..."):
                        new_profile = analyze_resume(raw_text)
                    save_user_resume(
                        user_id=user_id,
                        filename=upload.name,
                        file_bytes=upload.getvalue(),
                        profile=new_profile,
                    )
                    st.session_state["resume_profile"] = new_profile
                    st.success("Resume analyzed and saved to your account.")
                    st.rerun()
                except Exception as exc:
                    logger.exception("Resume analysis failed.")
                    st.error(f"Resume analysis failed: {exc}")
        if existing:
            st.success(f"Resume ready: {existing['filename']}")
        else:
            st.info("Upload a resume to enable personalized job matching.")
    with col2:
        profile = st.session_state.get("resume_profile", profile)
        if profile:
            st.markdown(
                f"""
                <div class="glass-card">
                    <div class="job-title">✅ AI profile ready</div>
                    <div class="job-meta">
                        {len(profile.skills)} skills ·
                        {len(profile.target_roles)} target roles ·
                        {profile.years_experience:g} years experience
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write("**Skills:**", ", ".join(profile.skills[:12]) or "Not found")
            st.write(
                "**Technologies:**",
                ", ".join(profile.technologies[:10]) or "Not found",
            )
            st.write(
                "**Target roles:**",
                ", ".join(profile.target_roles[:8]) or "Not found",
            )
    prefs = get_user_preferences(user_id)
    with st.expander("⚙️ Personal Job Preferences & Automation", expanded=True):
        full_name = st.text_input(
            "Full name",
            value=prefs.full_name or (profile.full_name if profile else ""),
            key="prefs_full_name",
        )
        phone = st.text_input(
            "Phone",
            value=prefs.phone or (profile.phone if profile else ""),
            key="prefs_phone",
        )
        roles = st.text_input(
            "Target roles (comma separated)",
            value=", ".join(prefs.target_roles or (profile.target_roles if profile else [])),
            key="prefs_roles",
        )
        skills = st.text_input(
            "Skills (comma separated)",
            value=", ".join(prefs.skills or (profile.skills if profile else [])),
            key="prefs_skills",
        )
        locations = st.text_input(
            "Preferred locations (comma separated)",
            value=", ".join(prefs.locations or ["Remote"]),
            key="prefs_locations",
        )
        remote_only = st.checkbox(
            "Remote only",
            value=prefs.remote_only,
            key="prefs_remote_only",
        )
        min_score = st.slider(
            "Minimum match score for auto-apply",
            60,
            100,
            int(prefs.min_match_score),
            5,
            key="prefs_min_score",
        )
        auto_apply = st.checkbox(
            "Enable automatic applications on supported sites",
            value=prefs.auto_apply_enabled,
            key="prefs_auto_apply",
            help=(
                "Applications run only for jobs meeting your explicit criteria. "
                "CAPTCHA/MFA/OTP or an unrecognized form always stops automation."
            ),
        )
        digest_enabled = st.checkbox(
            "Enable morning email digest",
            value=prefs.digest_enabled,
            key="prefs_digest_enabled",
        )
        digest_hour = st.slider(
            "Digest hour (24-hour clock)",
            0,
            23,
            int(prefs.digest_hour),
            key="prefs_digest_hour",
        )
        if st.button(
            "💾 Save Preferences",
            key="save_preferences_button",
            use_container_width=True,
        ):
            save_user_preferences(
                user_id=user_id,
                full_name=full_name,
                phone=phone,
                target_roles=[x.strip() for x in roles.split(",") if x.strip()],
                skills=[x.strip() for x in skills.split(",") if x.strip()],
                locations=[x.strip() for x in locations.split(",") if x.strip()],
                remote_only=remote_only,
                min_match_score=float(min_score),
                auto_apply_enabled=auto_apply,
                digest_enabled=digest_enabled,
                digest_hour=digest_hour,
            )
            st.success("Preferences saved.")
            st.rerun()
    return profile
def _render_resume_matches(user_id: int) -> None:
    """Render explainable resume-to-job matches for the latest agent run."""
    profile = st.session_state.get("resume_profile")
    items = st.session_state.get("last_run_enriched", [])
    if not profile or not items:
        return
    prefs = get_user_preferences(user_id)
    st.markdown("## 🎯 Resume Match Analysis")
    for item in items:
        result = match_job_to_profile(
            item.job,
            profile,
            prefs,
        )
        score = int(round(result.match_score))
        with st.container(border=True):
            st.markdown(
                f"### {item.job.title} · {item.job.company}"
            )
            st.progress(
                max(0.0, min(result.match_score / 100.0, 1.0)),
                text=f"Resume match: {score}%",
            )
            c1, c2, c3 = st.columns(3)
            c1.write(
                f"**Role:** {'✅' if result.role_fit else '❌'}"
            )
            c2.write(
                f"**Location:** {'✅' if result.location_fit else '❌'}"
            )
            experience_fit = result.experience_score > 0
            c3.write(
                f"**Experience:** {'✅' if experience_fit else '❌'}"
            )
            if result.matched_skills:
                st.caption(
                    "Matched skills: " + ", ".join(result.matched_skills[:12])
                )
            if result.missing_skills:
                st.caption(
                    "Not found in job: " + ", ".join(result.missing_skills[:10])
                )
            st.caption(result.explanation)
def _render_application_center(user_id: int) -> None:
    """Render application history and explicit auto-apply control."""
    st.markdown("## 🚀 Application Center")
    applications = get_user_applications(user_id)
    if applications:
        df = pd.DataFrame(applications)
        columns = [
            c
            for c in [
                "company",
                "role",
                "status",
                "match_score",
                "applied_at",
                "error_message",
            ]
            if c in df.columns
        ]
        if columns:
            st.dataframe(
                df[columns],
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("No applications have been recorded yet.")
    prefs = get_user_preferences(user_id)
    resume = get_user_resume(user_id)
    items = st.session_state.get("last_run_enriched", [])
    if not resume:
        st.warning("Upload and analyze your resume before using auto-apply.")
        return
    if not prefs.auto_apply_enabled:
        st.info("Auto-apply is OFF. Enable it in Personal Job Preferences.")
        return
    if not items:
        st.info("Run the agent first to produce jobs for the application queue.")
        return
    if not st.button(
        "🤖 Apply to Eligible Jobs",
        key="apply_eligible_button",
        use_container_width=True,
    ):
        return
    user = _current_user()
    processed = []
    for item in items[:5]:
        match_result = match_job_to_profile(
            item.job,
            resume["profile"],
            prefs,
        )
        if match_result.match_score < prefs.min_match_score:
            continue
        try:
            result = run_application_agent(
                user_id=user_id,
                user=user,
                item=item,
                match_result=match_result,
                resume_record=resume,
                preferences=prefs,
            )
            processed.append(result)
        except Exception as exc:
            logger.exception("Auto-apply failed for %s", item.job.title)
            processed.append(
                {
                    "status": "FAILED",
                    "job": item.job.title,
                    "message": str(exc),
                }
            )
    if processed:
        st.success(
            f"Processed {len(processed)} eligible application(s). "
            "Check the table above for the recorded status."
        )
        st.rerun()
    else:
        st.info("No jobs met the selected match threshold.")
# ---------------------------------------------------------------------------
# Dashboard UI
# ---------------------------------------------------------------------------
def _render_hero() -> None:
    """Render the main dashboard hero."""
    user = _current_user()
    display_name = user["username"] if user else "there"
    st.markdown(
        f"""
        <div class="hero">
            <span class="hero-badge">🤖 AUTONOMOUS AGENT · GEMINI + LANGGRAPH</span>
            <h1>🌅 Morning Job Agent</h1>
            <p>
                Good to see you, <strong>{display_name}</strong>.
                Discover AI Engineer roles, filter them intelligently,
                generate Gemini-powered summaries, and receive your personal
                job digest at your account email.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
def _render_job_card(item: JobWithSummary) -> None:
    """Render one premium job card."""
    job = item.job
    tags_html = "".join(
        f'<span class="tag-pill">{tag}</span>' for tag in job.tags[:10]
    )
    st.markdown(
        f"""
        <div class="glass-card">
            <div class="job-title">{job.title}</div>
            <div class="job-company">{job.company}</div>
            <div class="job-meta">
                📍 {job.location}
                &nbsp; · &nbsp;
                💰 {job.salary}
            </div>
            <div>{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_a, col_b = st.columns([1, 4])
    with col_a:
        if job.url:
            st.link_button("Open Job ↗", job.url, use_container_width=True)
    with col_b:
        with st.expander("✨ AI Summary & Interview Prep"):
            if item.summary is None:
                st.info("No AI summary is available for this role.")
                return
            summary = item.summary
            if summary.summary:
                st.markdown(f"**Summary:** {summary.summary}")
            st.markdown(
                f"**Experience level:** {summary.experience_level}"
            )
            if summary.required_skills:
                st.markdown(
                    "**Required skills:** "
                    + ", ".join(summary.required_skills)
                )
            if summary.technologies:
                st.markdown(
                    "**Technologies:** "
                    + ", ".join(summary.technologies)
                )
            if summary.interview_tips:
                st.markdown("**Interview prep tips:**")
                for tip in summary.interview_tips:
                    st.markdown(f"- {tip}")
            st.caption(f"Generated by: {summary.generated_by}")
def _render_sidebar() -> FilterPreferences:
    """Render filters, scheduler controls, and account controls."""
    with st.sidebar:
        st.markdown("## 🎯 Job Preferences")
        keyword_options = [
            "AI Engineer",
            "Machine Learning",
            "GenAI",
            "Python",
            "LangChain",
            "RAG",
        ]
        selected_keywords = st.multiselect(
            "Skill keywords",
            keyword_options,
            default=keyword_options,
        )
        location_options = ["Remote", "Hyderabad", "Bengaluru"]
        selected_locations = st.multiselect(
            "Locations",
            location_options,
            default=location_options,
        )
        require_location = st.checkbox(
            "Require location match",
            value=False,
        )
        free_text = st.text_input(
            "Additional keyword search",
            placeholder="e.g. vector database",
        )
        st.markdown("---")
        st.markdown("### ⏰ Scheduler")
        mode = st.radio(
            "Run mode",
            ["Manual", "Daily 8:00 AM", "Hourly"],
            index=0,
        )
        if mode == "Daily 8:00 AM":
            scheduler.start_daily(lambda: run_workflow(FilterPreferences()))
            st.caption(f"Next run: {scheduler.next_run_time or 'pending'}")
        elif mode == "Hourly":
            scheduler.start_hourly(lambda: run_workflow(FilterPreferences()))
            st.caption(f"Next run: {scheduler.next_run_time or 'pending'}")
        else:
            scheduler.stop()
        st.markdown("---")
        st.markdown("### 🧑‍💻 My Account")
        user = _current_user()
        if user:
            st.markdown(
                f"""
                <div class="account-card">
                    <strong>👋 {user["username"]}</strong><br>
                    <span class="muted">{user["email"]}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        smtp_ok = bool(getattr(settings, "smtp_configured", False))
        gemini_ok = bool(getattr(settings, "gemini_configured", False))
        st.caption(
            f"Gemini: {'✅ configured' if gemini_ok else '⚠️ fallback mode'}"
        )
        st.caption(
            f"SMTP: {'✅ ready' if smtp_ok else '⚠️ not configured'}"
        )
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            scheduler.stop()
            _logout_user()
            st.rerun()
    return FilterPreferences(
        keywords=selected_keywords or keyword_options,
        locations=selected_locations or location_options,
        free_text_search=free_text,
        require_location_match=require_location,
    )
# ---------------------------------------------------------------------------
# Per-user SMTP digest
# ---------------------------------------------------------------------------
@dataclass
class EmailResult:
    """Result of a digest send attempt."""
    sent: bool
    message: str
def _build_email_html(jobs: List[JobWithSummary]) -> str:
    """Build a clean HTML digest email."""
    rows = []
    for item in jobs:
        summary = item.summary
        summary_text = summary.summary if summary and summary.summary else ""
        rows.append(
            f"""
            <tr>
                <td style="padding:16px 0;border-bottom:1px solid #eaeaea;">
                    <div style="font-size:18px;font-weight:700;">
                        {item.job.title}
                    </div>
                    <div style="color:#5b4bb7;font-weight:600;margin-top:4px;">
                        {item.job.company}
                    </div>
                    <div style="color:#666;margin-top:4px;">
                        📍 {item.job.location} · 💰 {item.job.salary}
                    </div>
                    <p style="color:#444;line-height:1.5;">
                        {summary_text}
                    </p>
                    <a href="{item.job.url}"
                       style="display:inline-block;padding:9px 14px;
                              background:#6d28d9;color:#fff;
                              text-decoration:none;border-radius:8px;">
                        View Job
                    </a>
                </td>
            </tr>
            """
        )
    return f"""
    <!doctype html>
    <html>
      <body style="font-family:Arial,sans-serif;color:#1f2937;
                   max-width:760px;margin:0 auto;padding:30px;">
        <h1 style="color:#4c1d95;">🌅 Morning Job Agent</h1>
        <p style="color:#667085;">
          Your personalized AI job briefing contains
          <strong>{len(jobs)}</strong> matched role(s).
        </p>
        <table style="width:100%;border-collapse:collapse;">
          {''.join(rows)}
        </table>
        <p style="font-size:12px;color:#98a2b3;margin-top:28px;">
          Sent by Morning Job Agent.
        </p>
      </body>
    </html>
    """
def _send_user_digest(jobs: List[JobWithSummary], recipient_email: str) -> EmailResult:
    """Send a digest to the currently authenticated user's email."""
    if not jobs:
        return EmailResult(False, "No jobs are available to email.")
    host = getattr(settings, "smtp_host", None)
    port = int(getattr(settings, "smtp_port", 587))
    username = getattr(settings, "smtp_user", None)
    password = getattr(settings, "smtp_password", None)
    use_tls = bool(getattr(settings, "smtp_use_tls", True))
    if not host or not username or not password:
        return EmailResult(
            False,
            "SMTP is not configured. Check SMTP_HOST, SMTP_USER and "
            "SMTP_PASSWORD in your .env file.",
        )
    message = MIMEMultipart("alternative")
    message["Subject"] = f"Morning Job Agent — {len(jobs)} matched jobs"
    message["From"] = username
    message["To"] = recipient_email
    message.attach(MIMEText(_build_email_html(jobs), "html"))
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.sendmail(username, [recipient_email], message.as_string())
        return EmailResult(
            True,
            f"Digest emailed successfully to {recipient_email}.",
        )
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc)
        code = getattr(exc, "smtp_code", "unknown")
        error_text = (
            exc.smtp_error.decode(errors="ignore")
            if isinstance(exc.smtp_error, bytes)
            else str(exc.smtp_error)
        )
        return EmailResult(False, f"SMTP {code}: {error_text}")
    except smtplib.SMTPException as exc:
        logger.error("SMTP error: %s", exc)
        return EmailResult(False, f"Email failed: {exc}")
    except OSError as exc:
        logger.error("SMTP network error: %s", exc)
        return EmailResult(False, "Email failed: could not reach the SMTP server.")
# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------
def _render_dashboard() -> None:
    """Render the authenticated dashboard."""
    _render_hero()
    preferences = _render_sidebar()
    user = _current_user()
    user_id = int(user["id"]) if user else 0
    profile = _render_resume_profile(user_id)
    col1, col2, _ = st.columns([1, 1, 2])
    with col1:
        run_clicked = st.button(
            "🚀 Run Agent Now",
            use_container_width=True,
        )
    with col2:
        email_clicked = st.button(
            "📧 Email My Digest",
            use_container_width=True,
        )
    if run_clicked:
        with st.spinner("Searching, filtering, and summarizing jobs..."):
            try:
                final_state = run_workflow(preferences)
                st.session_state["last_run_saved"] = final_state.get(
                    "saved_count", 0
                )
                st.session_state["last_run_enriched"] = final_state.get(
                    "enriched_jobs", []
                )
                st.success(
                    f"Found {len(final_state.get('raw_jobs', []))} jobs · "
                    f"{len(final_state.get('filtered_jobs', []))} matched · "
                    f"{final_state.get('saved_count', 0)} newly saved."
                )
                st.cache_data.clear()
            except Exception as exc:
                logger.exception("Workflow execution failed.")
                st.error(f"The agent run failed: {exc}")
    if email_clicked:
        items = st.session_state.get("last_run_enriched", [])
        user = _current_user()
        if not items:
            st.warning("Run the agent first so there is a digest to send.")
        elif not user:
            st.error("Your session has expired. Please sign in again.")
            _logout_user()
            st.rerun()
        else:
            result = _send_user_digest(items, user["email"])
            if result.sent:
                st.success(result.message)
            else:
                st.error(result.message)
    _render_resume_matches(user_id)
    _render_application_center(user_id)
    df = _load_jobs_dataframe(_csv_cache_key())
    st.markdown("### 📊 Saved Jobs")
    metrics = st.columns(3)
    metrics[0].metric("Total saved jobs", len(df))
    generated_count = 0
    if not df.empty and "generated_by" in df.columns:
        generated_count = int(
            (df["generated_by"].astype(str).str.lower() == "gemini").sum()
        )
    metrics[1].metric("Gemini-enriched", generated_count)
    unique_companies = 0
    if not df.empty and "company" in df.columns:
        unique_companies = int(df["company"].nunique())
    metrics[2].metric("Unique companies", unique_companies)
    if df.empty:
        st.info(
            "No jobs saved yet. Click **Run Agent Now** to fetch and process "
            "the latest roles."
        )
        return
    if "fetched_at" in df.columns:
        df = df.sort_values("fetched_at", ascending=False)
    items = _dataframe_to_items(df)
    for item in items:
        _render_job_card(item)
    st.download_button(
        "⬇️ Download jobs.csv",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="jobs.csv",
        mime="text/csv",
        use_container_width=True,
    )
def main() -> None:
    """Initialize the application and render either auth or dashboard."""
    _init_database()
    init_feature_tables()
    _init_session()
    _inject_css()
    if not st.session_state["authenticated"]:
        _render_auth_page()
        return
    _render_dashboard()
if __name__ == "__main__":
    main()

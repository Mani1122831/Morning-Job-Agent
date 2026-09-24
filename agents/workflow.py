"""LangGraph workflow wiring the four agents together.

Graph shape:

    search_node -> filter_node -> summarize_node -> save_node -> END

State flows through a single `WorkflowState` TypedDict. The Streamlit UI
is intentionally *not* a graph node — display is a pure function of the
saved CSV data, invoked by the caller after `run_workflow()` returns.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import List, TypedDict

from langgraph.graph import END, StateGraph

from agents.filter_agent import filter_jobs
from agents.job_agent import search_jobs
from agents.summarizer_agent import summarize_jobs
from config import JOBS_CSV_PATH
from models.schemas import FilterPreferences, Job, JobWithSummary
from utils.logger import get_logger

logger = get_logger(__name__)

_CSV_FIELDS = [
    "id",
    "source",
    "title",
    "company",
    "location",
    "salary",
    "tags",
    "description",
    "url",
    "posted_at",
    "fetched_at",
    "required_skills",
    "technologies",
    "experience_level",
    "summary",
    "interview_tips",
    "generated_by",
]


class WorkflowState(TypedDict, total=False):
    """Shared state threaded through every LangGraph node."""

    preferences: FilterPreferences
    raw_jobs: List[Job]
    filtered_jobs: List[Job]
    enriched_jobs: List[JobWithSummary]
    saved_count: int


def _search_node(state: WorkflowState) -> WorkflowState:
    """Graph node: fetch raw jobs from all configured sources."""
    state["raw_jobs"] = search_jobs()
    return state


def _filter_node(state: WorkflowState) -> WorkflowState:
    """Graph node: apply the Smart Filter Agent to raw jobs."""
    preferences = state.get("preferences", FilterPreferences())
    state["filtered_jobs"] = filter_jobs(state.get("raw_jobs", []), preferences)
    return state


def _summarize_node(state: WorkflowState) -> WorkflowState:
    """Graph node: enrich filtered jobs with Gemini summaries."""
    state["enriched_jobs"] = summarize_jobs(state.get("filtered_jobs", []))
    return state


def _save_node(state: WorkflowState) -> WorkflowState:
    """Graph node: persist enriched jobs to `data/jobs.csv`, de-duplicated."""
    state["saved_count"] = save_jobs_to_csv(state.get("enriched_jobs", []))
    return state


def _build_graph():
    """Construct and compile the LangGraph state machine.

    Returns:
        A compiled LangGraph app ready to `.invoke()`.
    """
    graph = StateGraph(WorkflowState)
    graph.add_node("search", _search_node)
    graph.add_node("filter", _filter_node)
    graph.add_node("summarize", _summarize_node)
    graph.add_node("save", _save_node)

    graph.set_entry_point("search")
    graph.add_edge("search", "filter")
    graph.add_edge("filter", "summarize")
    graph.add_edge("summarize", "save")
    graph.add_edge("save", END)

    return graph.compile()


def load_existing_ids(csv_path: Path = JOBS_CSV_PATH) -> set[str]:
    """Read the IDs of jobs already persisted to CSV.

    Args:
        csv_path: Path to the jobs CSV file.

    Returns:
        Set of job IDs already present on disk (empty if the file is new).
    """
    if not csv_path.exists():
        return set()
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return {row["id"] for row in reader if row.get("id")}
    except (OSError, csv.Error, KeyError) as exc:
        logger.error("Could not read existing jobs.csv, treating as empty: %s", exc)
        return set()


def save_jobs_to_csv(items: List[JobWithSummary], csv_path: Path = JOBS_CSV_PATH) -> int:
    """Append new, de-duplicated jobs to the CSV store.

    Args:
        items: Enriched jobs to persist.
        csv_path: Destination CSV path.

    Returns:
        The number of newly written rows (existing IDs are skipped).
    """
    if not items:
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_existing_ids(csv_path)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    new_rows = 0
    try:
        with csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
            if not file_exists:
                writer.writeheader()

            for item in items:
                if item.job.id in existing_ids:
                    continue
                summary = item.summary
                writer.writerow(
                    {
                        "id": item.job.id,
                        "source": item.job.source,
                        "title": item.job.title,
                        "company": item.job.company,
                        "location": item.job.location,
                        "salary": item.job.salary,
                        "tags": "|".join(item.job.tags),
                        "description": item.job.description,
                        "url": item.job.url,
                        "posted_at": item.job.posted_at,
                        "fetched_at": item.job.fetched_at,
                        "required_skills": "|".join(summary.required_skills) if summary else "",
                        "technologies": "|".join(summary.technologies) if summary else "",
                        "experience_level": summary.experience_level if summary else "",
                        "summary": summary.summary if summary else "",
                        "interview_tips": "|".join(summary.interview_tips) if summary else "",
                        "generated_by": summary.generated_by if summary else "",
                    }
                )
                existing_ids.add(item.job.id)
                new_rows += 1
    except OSError as exc:
        logger.error("Failed to write jobs.csv: %s", exc)
        return 0

    logger.info("Saved %d new job(s) to %s.", new_rows, csv_path)
    return new_rows


def run_workflow(preferences: FilterPreferences | None = None) -> WorkflowState:
    """Execute the full search -> filter -> summarize -> save pipeline.

    Args:
        preferences: Filtering criteria. Defaults to `FilterPreferences()`.

    Returns:
        The final `WorkflowState`, including raw, filtered, and enriched
        jobs plus the count of newly saved rows.
    """
    app = _build_graph()
    initial_state: WorkflowState = {"preferences": preferences or FilterPreferences()}
    final_state = app.invoke(initial_state)
    logger.info(
        "Workflow complete: %d raw -> %d filtered -> %d enriched -> %d saved.",
        len(final_state.get("raw_jobs", [])),
        len(final_state.get("filtered_jobs", [])),
        len(final_state.get("enriched_jobs", [])),
        final_state.get("saved_count", 0),
    )
    return final_state
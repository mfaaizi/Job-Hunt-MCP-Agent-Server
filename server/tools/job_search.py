"""
MCP tools: search_jobs, get_job_details, list_saved_jobs
Integrates with OpenWeb Ninja's JSearch API: https://api.openwebninja.com/jsearch/search-v2
"""
import json
from typing import Optional

import httpx
from sqlmodel import select

from server.app import mcp
from server.config import settings
from server.db.models import Job
from server.db.session import get_session


def _map_job_payload(payload: dict) -> dict:
    """Maps a single JSearch API job object onto our Job table's columns."""
    is_remote = payload.get("job_is_remote")
    if is_remote is None and payload.get("work_arrangement"):
        is_remote = payload["work_arrangement"] == "remote"

    return {
        "external_job_id": payload.get("job_id"),
        "title": payload.get("job_title") or "Untitled",
        "company": payload.get("employer_name") or "Unknown",
        "location": payload.get("job_location"),
        "employment_type": payload.get("job_employment_type"),
        "is_remote": is_remote,
        "description": payload.get("job_description") or "",
        "apply_link": payload.get("job_apply_link"),
        "source": payload.get("job_publisher"),
        "salary_min": payload.get("job_min_salary"),
        "salary_max": payload.get("job_max_salary"),
        "salary_currency": payload.get("job_salary_currency"),
        "posted_at": payload.get("job_posted_at"),
        "raw_json": json.dumps(payload),
    }


@mcp.tool()
def search_jobs(
    query: str,
    country: str = "us",
    language: str = "en",
    remote_only: Optional[bool] = False,
    date_posted: Optional[str] = None,
) -> dict:
    """
    Search for job postings via JSearch (aggregates Google for Jobs, LinkedIn,
    Indeed, Glassdoor, ZipRecruiter, and more) and save new results locally.

    Args:
        query: Search query. Always include a location in the text itself for
            good results, e.g. "AI engineer in Lahore" or "remote python
            developer", rather than just "AI engineer" alone — that's how the
            underlying Google for Jobs index expects queries. You can also
            filter to a single job board by appending "via linkedin",
            "via indeed", etc. to the query text.
        country: ISO country code (default "us"). Set this to match the
            query's location for non-US searches, e.g. "pk" for Pakistan.
        language: Language code for results (default "en").
        remote_only: If True, only return remote/work-from-home jobs.
        date_posted: Optional recency filter: "today", "3days", "week", or "month".

    Returns:
        A dict with how many jobs were found, how many were newly saved vs.
        already in the database (deduped by JSearch's own job id), and a
        list of the newly saved jobs (id, title, company, location, apply_link).
    """
    if not settings.JSEARCH_API_KEY or "your_" in settings.JSEARCH_API_KEY:
        raise RuntimeError(
            "JSEARCH_API_KEY is not set in .env. Get a key at "
            "https://app.openwebninja.com/api/jsearch and add it to .env."
        )

    params: dict = {"query": query, "country": country, "language": language}
    if remote_only:
        params["work_from_home"] = "true"
    if date_posted:
        params["date_posted"] = date_posted

    response = httpx.get(
        f"{settings.JSEARCH_BASE_URL}/search-v2",
        params=params,
        headers={"x-api-key": settings.JSEARCH_API_KEY},
        timeout=30.0,
    )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"JSearch API returned HTTP {response.status_code}. "
            f"Raw response: {response.text[:1000]}"
        ) from e

    payload = response.json()

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Unexpected JSearch API response — expected a JSON object, got "
            f"{type(payload).__name__}: {str(payload)[:1000]}"
        )

    raw_data = payload.get("data", [])

    # The API's actual response nests the job list one level deeper than the
    # published docs sample shows: {"data": {"jobs": [...], "cursor": "..."}}
    # rather than {"data": [...]}. Handle both shapes defensively in case this
    # changes again.
    if isinstance(raw_data, list):
        jobs_data = raw_data
    elif isinstance(raw_data, dict):
        jobs_data = raw_data.get("jobs", [])
    else:
        jobs_data = []

    if not isinstance(jobs_data, list):
        raise RuntimeError(
            f"Unexpected job list shape in JSearch response — expected a list, got "
            f"{type(jobs_data).__name__}: {str(jobs_data)[:1000]}. "
            f"Full response: {str(payload)[:1000]}"
        )

    saved = []
    skipped_existing = 0

    with get_session() as session:
        for job_payload in jobs_data:
            if not isinstance(job_payload, dict):
                continue  # skip malformed entries rather than crash the whole search

            external_id = job_payload.get("job_id")
            if not external_id:
                continue

            existing = session.exec(
                select(Job).where(Job.external_job_id == external_id)
            ).first()
            if existing:
                skipped_existing += 1
                continue

            job = Job(**_map_job_payload(job_payload))
            session.add(job)
            session.flush()  # populate job.id before we read it below
            saved.append({
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "apply_link": job.apply_link,
            })

    return {
        "query": query,
        "total_found": len(jobs_data),
        "newly_saved": len(saved),
        "already_in_database": skipped_existing,
        "jobs": saved,
    }


@mcp.tool()
def get_job_details(job_id: int) -> dict:
    """
    Retrieve full details for a previously saved job by its local database id
    (the "id" field returned from search_jobs — not JSearch's own job_id string).

    Args:
        job_id: The local database id of the job.

    Returns:
        Full job details including the complete description.
    """
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")

        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "employment_type": job.employment_type,
            "is_remote": job.is_remote,
            "description": job.description,
            "apply_link": job.apply_link,
            "source": job.source,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "posted_at": job.posted_at,
            "fetched_at": job.fetched_at.isoformat(),
        }


@mcp.tool()
def list_saved_jobs(limit: int = 20) -> list[dict]:
    """
    List jobs already saved in the local database from previous searches,
    most recently fetched first.

    Args:
        limit: Max number of jobs to return (default 20).
    """
    with get_session() as session:
        jobs = session.exec(
            select(Job).order_by(Job.fetched_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "apply_link": j.apply_link,
            }
            for j in jobs
        ]

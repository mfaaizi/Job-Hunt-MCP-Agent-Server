"""
MCP tools: log_application, get_application_status, list_pipeline
Manual pipeline tracking — lets the person record real-world progress
(applied, interviewing, offer, rejected, withdrawn) on top of what
tailor_resume/generate_cover_letter already auto-track (saved -> drafted).
"""
from typing import Optional

from sqlmodel import select

from server.agents.cv_store import normalize_optional_str, resolve_cv
from server.app import mcp
from server.db.models import Application, ApplicationStatus, Job
from server.db.session import get_session

_VALID_STATUSES = {s.value for s in ApplicationStatus}


def _application_dict(app: Application, job: Job) -> dict:
    return {
        "job_id": job.id,
        "job_title": job.title,
        "company": job.company,
        "resume_id": app.resume_id,
        "status": app.status.value if hasattr(app.status, "value") else app.status,
        "notes": app.notes,
        "tailored_resume_path": app.tailored_resume_path,
        "cover_letter_path": app.cover_letter_path,
        "apply_link": job.apply_link,
        "created_at": app.created_at.isoformat(),
        "updated_at": app.updated_at.isoformat(),
    }


@mcp.tool()
def log_application(
    job_id: int,
    status: str,
    notes: Optional[str] = None,
    resume_id: Optional[str] = None,
) -> dict:
    """
    Record real-world progress on a job application. Creates the application
    record if it doesn't exist yet (e.g. logging status on a job you haven't
    tailored materials for), or updates it if it does.

    Args:
        job_id: Local database id of the job (from search_jobs / list_saved_jobs).
        status: One of: "saved", "drafted", "applied", "interviewing",
            "offer", "rejected", "withdrawn".
        notes: Optional free-text note (e.g. "recruiter said decision by Friday").
            Replaces any existing note — pass the full note text you want kept,
            not just what's new.
        resume_id: Which resume this application is tied to. Defaults to the
            most recently parsed (active) resume if omitted.

    Returns:
        The updated application record.
    """
    status_normalized = status.strip().lower()
    if status_normalized not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
        )

    cv = resolve_cv(resume_id)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")

        app = session.exec(
            select(Application).where(
                Application.job_id == job_id, Application.resume_id == cv.resume_id
            )
        ).first()

        if not app:
            app = Application(job_id=job_id, resume_id=cv.resume_id)
            session.add(app)
            session.flush()

        app.status = ApplicationStatus(status_normalized)
        notes = normalize_optional_str(notes)
        if notes is not None:
            app.notes = notes

        from datetime import datetime, timezone
        app.updated_at = datetime.now(timezone.utc)

        session.add(app)
        session.flush()

        return _application_dict(app, job)


@mcp.tool()
def get_application_status(job_id: int, resume_id: Optional[str] = None) -> dict:
    """
    Get the current pipeline status for a specific job application.

    Args:
        job_id: Local database id of the job.
        resume_id: Which resume's application to check. Defaults to the most
            recently parsed (active) resume if omitted.

    Returns:
        The application record, or a message indicating no application
        exists yet for this job (nothing has been drafted or logged).
    """
    cv = resolve_cv(resume_id)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")

        app = session.exec(
            select(Application).where(
                Application.job_id == job_id, Application.resume_id == cv.resume_id
            )
        ).first()

        if not app:
            return {
                "job_id": job_id,
                "job_title": job.title,
                "company": job.company,
                "status": None,
                "message": "No application on record for this job yet — nothing has been "
                           "drafted or logged. Use tailor_resume, generate_cover_letter, or "
                           "log_application to start tracking it.",
            }

        return _application_dict(app, job)


@mcp.tool()
def list_pipeline(status_filter: Optional[str] = None, resume_id: Optional[str] = None) -> list[dict]:
    """
    List applications in your pipeline, most recently updated first.

    Args:
        status_filter: Optional — only show applications with this status
            ("saved", "drafted", "applied", "interviewing", "offer",
            "rejected", "withdrawn"). Omit to show everything.
        resume_id: Only show applications tied to this resume. Defaults to
            the most recently parsed (active) resume if omitted.

    Returns:
        Applications sorted by most recently updated first.
    """
    cv = resolve_cv(resume_id)
    status_filter = normalize_optional_str(status_filter)

    if status_filter is not None:
        status_normalized = status_filter.strip().lower()
        if status_normalized not in _VALID_STATUSES:
            raise ValueError(
                f"Invalid status_filter '{status_filter}'. Must be one of: {', '.join(sorted(_VALID_STATUSES))}"
            )
    else:
        status_normalized = None

    with get_session() as session:
        query = select(Application).where(Application.resume_id == cv.resume_id)
        if status_normalized:
            query = query.where(Application.status == ApplicationStatus(status_normalized))
        query = query.order_by(Application.updated_at.desc())

        apps = session.exec(query).all()

        results = []
        for app in apps:
            job = session.get(Job, app.job_id)
            if job:
                results.append(_application_dict(app, job))

        return results

"""
MCP tool: start_application
Opens a job's real apply page in a visible browser and auto-fills whatever
it can confidently identify from your resume. Never submits — hands control
to you for review and completion.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import select

from server.agents.apply_assist import open_and_fill_application
from server.agents.cv_store import resolve_cv
from server.app import mcp
from server.db.models import Application, ApplicationStatus, Job
from server.db.session import get_session


def _get_or_create_application(session, job_id: int, resume_id: str) -> Application:
    existing = session.exec(
        select(Application).where(
            Application.job_id == job_id, Application.resume_id == resume_id
        )
    ).first()
    if existing:
        return existing

    application = Application(job_id=job_id, resume_id=resume_id, status=ApplicationStatus.SAVED)
    session.add(application)
    session.flush()
    return application


@mcp.tool()
async def start_application(job_id: int, resume_id: Optional[str] = None) -> dict:
    """
    Opens a saved job's real apply page in a visible browser window and
    attempts to auto-fill your name, email, and phone (from your parsed
    resume), plus upload your resume file if it can find an upload field.

    This tool NEVER clicks Submit or Apply. The browser window stays open
    after this returns — you review what was filled, complete anything it
    missed or got wrong, and submit it yourself. Real job sites vary hugely
    in form structure; this fills what it confidently can identify and
    leaves the rest for you.

    Args:
        job_id: Local database id of the job (from search_jobs / list_saved_jobs).
        resume_id: Which parsed resume to use for filling. Defaults to the
            most recently parsed (active) resume if omitted.

    Returns:
        A summary of what was filled, what wasn't, and any warnings — check
        this against the actual browser window, since a field reported as
        "not filled" may still need your attention even if the page loaded fine.
    """
    cv = resolve_cv(resume_id)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")
        if not job.apply_link:
            raise ValueError(
                f"Job {job_id} ({job.title} at {job.company}) has no apply_link on record."
            )
        job_title, job_company, apply_link = job.title, job.company, job.apply_link

    # The browser operation is the slow part (real page load, real network) —
    # deliberately outside the DB session above rather than holding it open
    # the whole time.
    fill_result = await open_and_fill_application(
        apply_url=apply_link,
        name=cv.contact.name,
        email=cv.contact.email,
        phone=cv.contact.phone,
        resume_file_path=cv.source_file,
    )

    with get_session() as session:
        app = _get_or_create_application(session, job_id, cv.resume_id)
        if app.status == ApplicationStatus.SAVED:
            app.status = ApplicationStatus.DRAFTED

        note = f"Application-assist opened {apply_link} and attempted auto-fill."
        app.notes = f"{app.notes}\n{note}" if app.notes else note
        app.updated_at = datetime.now(timezone.utc)
        session.add(app)

    return {
        "job_id": job_id,
        "job_title": job_title,
        "company": job_company,
        **fill_result,
        "reminder": "The browser window is open and waiting for you. Review every "
                    "filled field, complete anything missing, and click submit yourself "
                    "when you're satisfied — nothing has been submitted automatically.",
    }

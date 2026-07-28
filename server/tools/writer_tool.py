"""
MCP tools: tailor_resume, generate_cover_letter
Generates application materials for a specific job, saves them to disk, and
tracks progress in the Application table.
"""
from pathlib import Path
from typing import Optional

from sqlmodel import select

from server.agents.cv_store import resolve_cv
from server.agents.writer import generate_cover_letter_content, generate_tailored_resume_content
from server.app import mcp
from server.config import settings
from server.db.models import Application, ApplicationStatus, Job
from server.db.session import get_session


def _application_dir(job_id: int, resume_id: str) -> Path:
    # Short resume id suffix keeps directory names readable while still
    # distinguishing drafts made against different resume versions.
    short_resume_id = resume_id[-8:] if len(resume_id) > 8 else resume_id
    out_dir = settings.APPLICATIONS_DIR / f"job{job_id}_{short_resume_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


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
def tailor_resume(job_id: int, resume_id: Optional[str] = None) -> dict:
    """
    Generate a tailored resume framing (summary, skill ordering, bullet
    selection, project recommendations) for a specific saved job. Only
    rephrases/reorders/selects from the candidate's actual resume data —
    never invents skills or experience. Saves the result as a Markdown file
    and marks the application as "drafted" in the pipeline tracker.

    Args:
        job_id: Local database id of the job (from search_jobs / list_saved_jobs).
        resume_id: Which parsed resume to tailor. Defaults to the most
            recently parsed (active) resume if omitted.

    Returns:
        A dict with the file path the tailored content was saved to, and the
        content itself.
    """
    cv = resolve_cv(resume_id)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")

        content = generate_tailored_resume_content(cv, job)

        out_dir = _application_dir(job_id, cv.resume_id)
        out_path = out_dir / "tailored_resume.md"
        out_path.write_text(content, encoding="utf-8")

        application = _get_or_create_application(session, job_id, cv.resume_id)
        application.tailored_resume_path = str(out_path)
        if application.status == ApplicationStatus.SAVED:
            application.status = ApplicationStatus.DRAFTED
        session.add(application)

        return {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "resume_id": cv.resume_id,
            "saved_to": str(out_path),
            "content": content,
        }


@mcp.tool()
def generate_cover_letter(job_id: int, resume_id: Optional[str] = None) -> dict:
    """
    Generate a cover letter for a specific saved job, grounded only in the
    candidate's actual resume data. Saves the result as a text file and marks
    the application as "drafted" in the pipeline tracker.

    Args:
        job_id: Local database id of the job (from search_jobs / list_saved_jobs).
        resume_id: Which parsed resume to base the letter on. Defaults to the
            most recently parsed (active) resume if omitted.

    Returns:
        A dict with the file path the cover letter was saved to, and the
        content itself.
    """
    cv = resolve_cv(resume_id)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")

        content = generate_cover_letter_content(cv, job)

        out_dir = _application_dir(job_id, cv.resume_id)
        out_path = out_dir / "cover_letter.txt"
        out_path.write_text(content, encoding="utf-8")

        application = _get_or_create_application(session, job_id, cv.resume_id)
        application.cover_letter_path = str(out_path)
        if application.status == ApplicationStatus.SAVED:
            application.status = ApplicationStatus.DRAFTED
        session.add(application)

        return {
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "resume_id": cv.resume_id,
            "saved_to": str(out_path),
            "content": content,
        }

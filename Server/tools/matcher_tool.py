"""
MCP tools: match_job_to_profile, rank_jobs
Scores saved jobs against a parsed resume, using the matcher agent. Results
are cached in the Match table so repeated calls don't re-score for nothing.
"""
from typing import List, Optional, Union

from sqlmodel import select

from server.agents.cv_store import resolve_cv
from server.agents.matcher import (
    compute_skill_overlap,
    get_embeddings_batch,
    score_resume_against_job,
    score_resume_embedding_against_job,
)
from server.app import mcp
from server.db.models import Job, Match
from server.db.session import get_session
from server.utils import coerce_optional_bool


def _score_and_save(
    session,
    cv,
    resolved_resume_id: str,
    job: Job,
    force_rescore: bool,
    resume_embedding: Optional[List[float]] = None,
) -> dict:
    """
    Shared scoring + caching logic for a single job. If resume_embedding is
    provided, reuses it instead of re-embedding the resume text — used by
    rank_jobs to avoid redundant embedding calls when scoring many jobs
    against the same resume in one pass.
    """
    existing = session.exec(
        select(Match).where(
            Match.resume_id == resolved_resume_id, Match.job_id == job.id
        )
    ).first()

    if existing and not force_rescore:
        return {
            "job_id": job.id,
            "job_title": job.title,
            "company": job.company,
            "resume_id": resolved_resume_id,
            "score": existing.score,
            "matched_skills": existing.matched_skills.split(",") if existing.matched_skills else [],
            "missing_skills": existing.missing_skills.split(",") if existing.missing_skills else [],
            "cached": True,
        }

    job_text = f"{job.title}\n{job.description}"

    if resume_embedding is not None:
        score = score_resume_embedding_against_job(resume_embedding, job_text)
    else:
        score = score_resume_against_job(cv.to_matcher_text(), job_text)

    flat_skills = cv.to_rich_dict()["skills"]
    matched, missing = compute_skill_overlap(flat_skills, job_text)

    if existing:
        session.delete(existing)
        session.flush()

    match = Match(
        resume_id=resolved_resume_id,
        job_id=job.id,
        score=score,
        matched_skills=",".join(matched),
        missing_skills=",".join(missing),
    )
    session.add(match)

    return {
        "job_id": job.id,
        "job_title": job.title,
        "company": job.company,
        "resume_id": resolved_resume_id,
        "score": round(score, 4),
        "matched_skills": matched,
        "missing_skills": missing,
        "cached": False,
    }


@mcp.tool()
def match_job_to_profile(job_id: int, resume_id: Optional[str] = None, force_rescore: Union[bool, str, None] = False) -> dict:
    """
    Score how well a saved job matches a parsed resume, using semantic
    similarity (via embeddings) plus a keyword-based skill overlap check.
    Results are cached — calling this again for the same resume/job pair
    returns the cached score instead of re-computing, unless force_rescore
    is set.

    Args:
        job_id: Local database id of the job (from search_jobs / list_saved_jobs).
        resume_id: Which parsed resume to match against. Defaults to the most
            recently parsed (active) resume if omitted.
        force_rescore: If True, recompute even if a cached match already exists.

    Returns:
        A dict with the match score (0.0-1.0), matched skills, missing
        skills (resume skills not mentioned in the job description), and
        whether the result came from cache.
    """
    cv = resolve_cv(resume_id)
    force_rescore = coerce_optional_bool(force_rescore, default=False)

    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"No job found with id={job_id}. Run search_jobs first.")

        return _score_and_save(session, cv, cv.resume_id, job, force_rescore)


@mcp.tool()
def rank_jobs(resume_id: Optional[str] = None, top_n: int = 10) -> list[dict]:
    """
    Score ALL saved jobs against a resume and return them ranked best-fit
    first. Uses cached scores where already computed, scores new jobs
    otherwise — safe to call repeatedly as new jobs get saved.

    Args:
        resume_id: Which parsed resume to match against. Defaults to the most
            recently parsed (active) resume if omitted.
        top_n: Max number of results to return (default 10).

    Returns:
        Jobs sorted by match score descending, each with score and
        matched/missing skills.
    """
    cv = resolve_cv(resume_id)

    # Embed the resume once here, reuse it for every job below — avoids
    # re-embedding identical resume text once per job (previously the main
    # cost in a full re-rank: 2x the necessary Ollama calls).
    resume_embedding = get_embeddings_batch([cv.to_matcher_text()])[0]

    with get_session() as session:
        jobs = session.exec(select(Job)).all()
        results = [
            _score_and_save(session, cv, cv.resume_id, job, force_rescore=False, resume_embedding=resume_embedding)
            for job in jobs
        ]

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_n]

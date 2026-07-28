"""
SQLModel table definitions for the job-agent pipeline.

Three tables:
- Job: raw job postings pulled from JSearch, deduped by external job_id
- Match: score linking a resume_id <-> job_id, produced by the matcher agent
- Application: pipeline tracking (status, tailored materials, timestamps)
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStatus(str, Enum):
    SAVED = "saved"              # shortlisted, not yet applied
    DRAFTED = "drafted"          # tailored resume/cover letter generated
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Job(SQLModel, table=True):
    """A single job posting, as returned by JSearch. Deduped on external_job_id."""

    id: Optional[int] = Field(default=None, primary_key=True)

    # JSearch's own job id — used to dedupe re-fetched search results
    external_job_id: str = Field(index=True, unique=True)

    title: str
    company: str
    location: Optional[str] = None
    employment_type: Optional[str] = None  # e.g. FULLTIME, CONTRACTOR
    is_remote: Optional[bool] = None

    description: str
    apply_link: Optional[str] = None
    source: Optional[str] = None  # e.g. "linkedin", "indeed" (JSearch aggregates multiple)

    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None

    posted_at: Optional[str] = None  # kept as free text — source formats vary
    fetched_at: datetime = Field(default_factory=_utcnow)

    # Raw JSearch payload, stringified, in case we need fields we didn't model explicitly
    raw_json: Optional[str] = None


class Match(SQLModel, table=True):
    """Match score between a parsed resume and a job posting."""

    id: Optional[int] = Field(default=None, primary_key=True)

    resume_id: str = Field(index=True)
    job_id: int = Field(foreign_key="job.id", index=True)

    score: float  # 0.0-1.0 cosine similarity (or whatever the matcher agent produces)
    matched_skills: Optional[str] = None    # comma-separated, for quick display
    missing_skills: Optional[str] = None    # skills in JD not found in resume

    scored_at: datetime = Field(default_factory=_utcnow)


class Application(SQLModel, table=True):
    """Tracks a job through the application pipeline."""

    id: Optional[int] = Field(default=None, primary_key=True)

    job_id: int = Field(foreign_key="job.id", index=True)
    resume_id: str = Field(index=True)

    status: ApplicationStatus = Field(default=ApplicationStatus.SAVED)

    tailored_resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None

    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

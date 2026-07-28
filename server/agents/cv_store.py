"""
CV store: persistence layer for normalized resume JSON.

Design rule: this is the ONLY interface other agents (matcher, writer, etc.)
use to access resume data. They never read the original PDF/DOCX and never
call the parser directly — they call get_active_cv().
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from server.config import settings
from server.models.resume import ResumeCV

# Points at whichever resume_id is currently "active" (most recently parsed).
_ACTIVE_POINTER_FILE = settings.RESUME_STORAGE_DIR / "active_resume.txt"


def _resume_dir(resume_id: str) -> Path:
    return settings.RESUME_STORAGE_DIR / resume_id


def generate_resume_id(source_file: str) -> str:
    """Stable-ish id: filename stem + short timestamp hash, so re-parsing the
    same file twice doesn't silently collide, but ids stay short and readable."""
    stem = Path(source_file).stem.replace(" ", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    short_hash = hashlib.sha1(f"{source_file}{ts}".encode()).hexdigest()[:6]
    return f"{stem}_{ts}_{short_hash}"


def save_cv(cv: ResumeCV, raw_text: str) -> str:
    """
    Persists raw_text.txt and cv.json under data/resumes/<resume_id>/,
    marks this resume as the active one, and returns the resume_id.
    """
    if not cv.resume_id:
        raise ValueError("cv.resume_id must be set before saving")

    out_dir = _resume_dir(cv.resume_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "raw_text.txt").write_text(raw_text, encoding="utf-8")
    (out_dir / "cv.json").write_text(cv.model_dump_json(indent=2), encoding="utf-8")

    _ACTIVE_POINTER_FILE.write_text(cv.resume_id, encoding="utf-8")

    return cv.resume_id


def load_cv(resume_id: str) -> ResumeCV:
    cv_path = _resume_dir(resume_id) / "cv.json"
    if not cv_path.exists():
        raise FileNotFoundError(f"No parsed resume found for resume_id={resume_id}")
    return ResumeCV.model_validate_json(cv_path.read_text(encoding="utf-8"))


def get_active_resume_id() -> Optional[str]:
    if not _ACTIVE_POINTER_FILE.exists():
        return None
    resume_id = _ACTIVE_POINTER_FILE.read_text(encoding="utf-8").strip()
    return resume_id or None


def get_active_cv() -> ResumeCV:
    """
    The main entry point for all other agents. Returns the normalized CV
    for whichever resume was most recently parsed.
    """
    resume_id = get_active_resume_id()
    if not resume_id:
        raise FileNotFoundError(
            "No active resume found. Run parse_resume() at least once before using other tools."
        )
    return load_cv(resume_id)


# Some small local models send the literal string "null" (or similar) instead
# of an actual JSON null when they don't have a value for an optional string
# argument. Since resume_id is typed as Optional[str], "null" passes type
# validation as a normal string and only fails later, confusingly, when no
# resume is actually named "null". Treat these as equivalent to "not provided".
_NULL_LIKE_STRINGS = {"null", "none", "nil", "undefined", ""}


def resolve_cv(resume_id: Optional[str] = None) -> ResumeCV:
    """
    Resolves an optional resume_id argument (as received from an MCP tool
    call) to a ResumeCV — falling back to the active resume if resume_id is
    genuinely absent OR is one of the null-like placeholder strings a model
    might send instead of an actual null. Every tool that accepts a
    resume_id parameter should call this rather than handling the
    None-vs-active logic itself, so this fix applies everywhere at once.
    """
    if resume_id is not None and resume_id.strip().lower() in _NULL_LIKE_STRINGS:
        resume_id = None
    return load_cv(resume_id) if resume_id else get_active_cv()


def list_parsed_resumes() -> list[str]:
    """Returns all resume_ids that have been parsed and saved."""
    if not settings.RESUME_STORAGE_DIR.exists():
        return []
    return sorted(
        p.name for p in settings.RESUME_STORAGE_DIR.iterdir()
        if p.is_dir() and (p / "cv.json").exists()
    )

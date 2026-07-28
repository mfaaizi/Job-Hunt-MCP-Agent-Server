"""
MCP tool: parse_resume
Orchestrates: file -> raw text -> Ollama structuring -> Pydantic validation -> storage.
"""
from pathlib import Path

from server.agents.cv_store import generate_resume_id, save_cv
from server.agents.cv_structurer import structure_resume_text
from server.app import mcp
from server.tools.resume_extractor import (
    extract_contact_fields_fallback,
    extract_contact_links_from_pdf,
    extract_name_fallback,
    extract_resume_text,
)


@mcp.tool()
def parse_resume(file_path: str) -> dict:
    """
    Parse a resume (PDF or DOCX) into a normalized, structured JSON representation.

    This is the entry point for getting your resume into the system. Run this
    once (or whenever your resume changes) before using matching, tailoring,
    or application tools — they all read from the normalized JSON this
    produces rather than the original file.

    Args:
        file_path: Path to the resume file (.pdf or .docx).

    Returns:
        A dict with the resume_id and a rich, directly usable breakdown:
        contact info, a flat skills list, experience, projects, education,
        and strengths. The full nested representation (with skills grouped
        by category, etc.) is always available afterward via
        get_parsed_resume().
    """
    file_path = Path(file_path).expanduser().resolve()

    raw_text = extract_resume_text(file_path)
    cv = structure_resume_text(raw_text, source_file=str(file_path))
    cv.resume_id = generate_resume_id(str(file_path))

    # Contact info is extracted with a priority order, most reliable first:
    #   1. PDF hyperlink annotations (mailto:, tel:, github.com/..., linkedin.com/...)
    #      — reads the actual link target, unaffected by icon-font/glyph mess
    #        in the visible text.
    #   2. Regex over raw text — used only as a backstop for fields hyperlinks
    #      didn't cover (e.g. DOCX files, or a PDF with plain-text contact info).
    #   3. The LLM's own guess — used only if neither of the above found anything.
    # Small local models are unreliable at parsing symbol-heavy header lines,
    # so this order deliberately favors deterministic extraction over the model.
    contact_overrides: dict = {}
    if file_path.suffix.lower() == ".pdf":
        contact_overrides.update(extract_contact_links_from_pdf(file_path))

    fallback = extract_contact_fields_fallback(raw_text)
    for key, value in fallback.items():
        contact_overrides.setdefault(key, value)

    if contact_overrides.get("email"):
        cv.contact.email = contact_overrides["email"]
    if contact_overrides.get("phone"):
        cv.contact.phone = contact_overrides["phone"]
    if contact_overrides.get("github"):
        cv.contact.github = contact_overrides["github"]
    if contact_overrides.get("linkedin"):
        cv.contact.linkedin = contact_overrides["linkedin"]
    if contact_overrides.get("portfolio") and not cv.contact.portfolio:
        cv.contact.portfolio = contact_overrides["portfolio"]

    if not cv.contact.name:
        cv.contact.name = extract_name_fallback(raw_text)

    resume_id = save_cv(cv, raw_text)

    return {
        "resume_id": resume_id,
        "source_file": str(file_path),
        **cv.to_rich_dict(),
    }


@mcp.tool()
def get_parsed_resume(resume_id: str | None = None) -> dict:
    """
    Retrieve a previously parsed resume's full normalized JSON.

    Args:
        resume_id: Specific resume to fetch. If omitted, returns the most
            recently parsed (active) resume.

    Returns:
        The full normalized ResumeCV as a dict.
    """
    from server.agents.cv_store import resolve_cv

    cv = resolve_cv(resume_id)
    return cv.model_dump()


@mcp.tool()
def list_resumes() -> list[str]:
    """List all resume_ids that have been parsed and are available to use."""
    from server.agents.cv_store import list_parsed_resumes

    return list_parsed_resumes()

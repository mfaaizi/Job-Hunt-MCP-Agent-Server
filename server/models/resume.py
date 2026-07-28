"""
Normalized resume schema.
This is the single source of truth other agents (matcher, writer) consume.
No agent other than the resume parser should ever touch the raw PDF/DOCX.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None
    location: Optional[str] = None


class ExperienceEntry(BaseModel):
    title: str
    organization: str
    location: Optional[str] = None
    start_date: Optional[str] = None  # kept as free text (e.g. "June 2025") — resumes rarely use ISO dates
    end_date: Optional[str] = None
    employment_type: Optional[str] = None  # e.g. Hybrid, Remote, Onsite
    bullets: List[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str
    tech_stack: List[str] = Field(default_factory=list)
    bullets: List[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    degree: str
    institution: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None


class SkillCategory(BaseModel):
    category: str
    items: List[str] = Field(default_factory=list)


class StrengthEntry(BaseModel):
    title: str
    description: Optional[str] = None


class ResumeCV(BaseModel):
    """Normalized, structured representation of a resume."""

    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: Optional[str] = None
    experience: List[ExperienceEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    skills: List[SkillCategory] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    strengths: List[StrengthEntry] = Field(default_factory=list)

    # Catch-all for sections future resumes might add (certifications, publications,
    # awards, languages spoken, etc.) that don't fit the fixed fields above.
    # Keeps the schema flexible without requiring a migration every time the resume changes.
    extra_sections: Dict[str, Any] = Field(default_factory=dict)

    # Provenance
    source_file: Optional[str] = None
    parsed_at: Optional[str] = None
    resume_id: Optional[str] = None

    def to_matcher_text(self) -> str:
        """
        Flattens the structured CV into plain text optimized for embedding /
        semantic matching against job descriptions. Used by the matcher agent —
        keeps embedding logic decoupled from the schema shape.
        """
        parts: List[str] = []
        if self.summary:
            parts.append(self.summary)

        for exp in self.experience:
            parts.append(f"{exp.title} at {exp.organization}")
            parts.extend(exp.bullets)

        for proj in self.projects:
            parts.append(f"Project: {proj.name} ({', '.join(proj.tech_stack)})")
            parts.extend(proj.bullets)

        for cat in self.skills:
            parts.append(f"{cat.category}: {', '.join(cat.items)}")

        for edu in self.education:
            parts.append(f"{edu.degree}, {edu.institution}")

        for strength in self.strengths:
            parts.append(f"{strength.title}: {strength.description or ''}")

        return "\n".join(parts)

    def to_rich_dict(self) -> Dict[str, Any]:
        """
        A flatter, more directly usable projection of the CV for MCP tool
        responses — e.g. a single flat skills list instead of categories, and
        experience/project entries with the fields callers most commonly want
        up front. This does NOT replace the full nested representation
        (still available via model_dump() / get_parsed_resume) — it's a
        convenience view on top of it, so nothing here should be treated as
        the source of truth.
        """
        # Flatten skills across categories into one deduped list, preserving
        # first-seen order.
        seen: set = set()
        flat_skills: List[str] = []
        for category in self.skills:
            for item in category.items:
                if item not in seen:
                    seen.add(item)
                    flat_skills.append(item)

        experience = [
            {
                "company": exp.organization,
                "role": exp.title,
                "location": exp.location,
                "start_date": exp.start_date,
                "end_date": exp.end_date,
                "employment_type": exp.employment_type,
                # Not separately captured in most resumes (tech is usually
                # embedded in prose bullets, not a standalone list) — left
                # empty rather than guessed. The bullets below have the detail.
                "technologies": [],
                "bullets": exp.bullets,
            }
            for exp in self.experience
        ]

        projects = [
            {
                "name": proj.name,
                "tech_stack": proj.tech_stack,
                "description": " ".join(proj.bullets),
                "bullets": proj.bullets,
            }
            for proj in self.projects
        ]

        return {
            "contact": self.contact.model_dump(),
            "summary": self.summary,
            "skills": flat_skills,
            "skills_by_category": [c.model_dump() for c in self.skills],
            "experience": experience,
            "projects": projects,
            "education": [e.model_dump() for e in self.education],
            "strengths": [s.model_dump() for s in self.strengths],
        }

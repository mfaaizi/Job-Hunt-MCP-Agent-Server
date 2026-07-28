"""
Writer agent: generates a tailored resume summary/bullet framing and a cover
letter for a specific job, using the local Ollama model.

Integrity rule (important, enforced via the prompt): the writer may only
rephrase, reorder, and select from what's actually in the parsed resume —
never invent skills, achievements, employers, or experience the person
doesn't have. This produces content the person can review and use, not a
fabricated resume.
"""
import json

import ollama

from server.config import settings
from server.db.models import Job
from server.models.resume import ResumeCV

_TAILOR_RESUME_INSTRUCTIONS = """\
You help tailor a resume's framing for a specific job application.

You will be given the candidate's full resume data as JSON, and a target job's
title/company/description. Produce a tailored resume framing in Markdown with
these sections:

## Tailored Summary
A 2-4 sentence professional summary rewritten to emphasize the aspects of the
candidate's real background most relevant to THIS job.

## Recommended Skills Order
A reordered list of the candidate's actual skills (from the resume data only),
most job-relevant first.

## Experience Framing
For each real experience entry, 1-3 bullet points selected/rephrased from
their ACTUAL bullets to emphasize relevance to this job. You may rephrase
wording and choose which existing bullets to lead with, but every claim must
come from the original resume data — do not add new bullets, technologies,
metrics, or achievements not present in the source data.

## Recommended Projects to Highlight
Pick 2-3 of the candidate's real projects most relevant to this job, with a
one-line reason why each is relevant.

CRITICAL RULES:
- Do NOT invent, exaggerate, or add any skill, technology, achievement,
  employer, project, or metric that is not explicitly present in the resume
  JSON provided below. If the resume doesn't support a claim, don't make it.
- You may rephrase and reorder. You may NOT fabricate.
- Output ONLY the Markdown content described above. No preamble, no commentary
  about what you're doing, no code fences.
"""

_COVER_LETTER_INSTRUCTIONS = """\
You write a cover letter for a job application.

You will be given the candidate's full resume data as JSON, and a target
job's title/company/description. Write a concise, professional cover letter
(3-4 short paragraphs) that:
- Opens by naming the role and company.
- Connects 2-3 specific, real pieces of the candidate's background (from the
  resume data) to what the job is asking for.
- Closes with a brief, confident call to action.

CRITICAL RULES:
- Do NOT invent, exaggerate, or add any skill, technology, achievement,
  employer, project, or metric that is not explicitly present in the resume
  JSON provided below. Every specific claim in the letter must be traceable
  to the resume data.
- Keep the tone professional but not stiff. Avoid generic filler phrases like
  "I am a highly motivated individual."
- Output ONLY the cover letter text. No subject line, no markdown headers, no
  preamble, no commentary about what you're doing.
"""


def _build_context(cv: ResumeCV, job: Job) -> str:
    resume_json = json.dumps(cv.to_rich_dict(), indent=2)
    return (
        f"RESUME DATA (JSON):\n{resume_json}\n\n"
        f"TARGET JOB:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'N/A'}\n"
        f"Description:\n{job.description}\n"
    )


def _call_ollama(system_instructions: str, context: str) -> str:
    response = ollama.chat(
        model=settings.OLLAMA_MODEL,
        messages=[
            {"role": "user", "content": f"{system_instructions}\n\n{context}"},
        ],
        options={"temperature": 0.4},
    )
    return response["message"]["content"].strip()


def generate_tailored_resume_content(cv: ResumeCV, job: Job) -> str:
    """Returns Markdown-formatted tailored resume framing for the given job."""
    context = _build_context(cv, job)
    return _call_ollama(_TAILOR_RESUME_INSTRUCTIONS, context)


def generate_cover_letter_content(cv: ResumeCV, job: Job) -> str:
    """Returns plain-text cover letter content for the given job."""
    context = _build_context(cv, job)
    return _call_ollama(_COVER_LETTER_INSTRUCTIONS, context)

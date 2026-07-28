"""
CV structurer agent: takes raw resume text and uses a local Ollama model to
produce JSON matching the ResumeCV schema. Retries with error feedback if
the model's output fails Pydantic validation.
"""
import json
from datetime import datetime, timezone
from typing import Optional

import ollama
from pydantic import ValidationError

from server.config import settings
from server.models.resume import ResumeCV

_SCHEMA_INSTRUCTIONS = """\
You extract structured data from resume text and output ONLY valid JSON matching this shape:

{
  "contact": {"name": str|null, "email": str|null, "phone": str|null, "github": str|null,
              "linkedin": str|null, "portfolio": str|null, "location": str|null},
  "summary": str|null,
  "experience": [{"title": str, "organization": str, "location": str|null,
                   "start_date": str|null, "end_date": str|null,
                   "employment_type": str|null, "bullets": [str, ...]}],
  "projects": [{"name": str, "tech_stack": [str, ...], "bullets": [str, ...]}],
  "skills": [{"category": str, "items": [str, ...]}],
  "education": [{"degree": str, "institution": str, "location": str|null,
                  "start_date": str|null, "end_date": str|null, "gpa": str|null}],
  "strengths": [{"title": str, "description": str|null}],
  "extra_sections": {"<section name>": <any JSON value>}
}

Rules:
- Preserve ALL information present in the resume. Do not summarize, shorten, or omit bullet points.
- Use the resume's own wording for bullets and descriptions verbatim — do not paraphrase.
- If the resume contains a section that doesn't map to the fixed fields above (e.g. certifications,
  publications, languages spoken, awards), put it under "extra_sections" keyed by a descriptive name.
- Dates: keep them as written in the resume (e.g. "June 2025", "2022 - 2026"). Do not reformat to ISO.
- If a field has no data, use null (for scalars) or an empty list/object (for lists/dicts). Never invent data.
- Split comma-separated skill lists under their original category headings (e.g. "Languages:", "AI/ML:").
- Output ONLY the JSON object. No markdown fences, no commentary, no preamble.

Contact header parsing (important — this line is often messy):
- The header line near the top usually looks like: "Name | icon-symbol handle1 | icon-symbol handle2
  | icon-symbol email | icon-symbol phone", separated by "|" characters, with leftover icon-font
  symbols (odd characters like §, #, H, or similar) immediately before each value. IGNORE those
  leading symbol characters — they are rendering artifacts from icon fonts, not part of the data.
- Split the header on "|" into separate tokens. Classify each token by its shape, not its position:
  a token containing "@" is the email; a token that looks like a phone number (digits, spaces, +, -)
  is the phone; a short bare word/handle (no spaces, no @, not a phone number) near the top is
  usually a GitHub or LinkedIn username — put it in "github" or "linkedin" based on which makes more
  sense contextually, or in "portfolio" if neither fits.
- Never dump multiple pieces of contact info into a single field (e.g. do not put "handle | email"
  together into the "email" field — split them apart correctly).
"""


def _build_prompt(raw_text: str) -> str:
    return f"{_SCHEMA_INSTRUCTIONS}\n\nRESUME TEXT:\n\"\"\"\n{raw_text}\n\"\"\""


def _call_ollama(prompt: str, repair_note: Optional[str] = None) -> str:
    messages = [{"role": "user", "content": prompt}]
    if repair_note:
        messages.append({
            "role": "user",
            "content": f"Your previous output was invalid JSON for this reason: {repair_note}\n"
                       f"Return the corrected, complete JSON object only.",
        })

    response = ollama.chat(
        model=settings.OLLAMA_MODEL,
        messages=messages,
        format="json",
        options={"temperature": 0.1},
    )
    return response["message"]["content"]


def structure_resume_text(raw_text: str, source_file: str, max_retries: int = 2) -> ResumeCV:
    """
    Runs raw resume text through the local Ollama model and returns a
    validated ResumeCV. Retries with the validation error fed back to the
    model if the first attempt doesn't parse/validate.
    """
    prompt = _build_prompt(raw_text)
    last_error: Optional[str] = None

    for attempt in range(max_retries + 1):
        raw_output = _call_ollama(prompt, repair_note=last_error)

        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as e:
            last_error = f"Output was not valid JSON: {e}"
            continue

        try:
            cv = ResumeCV.model_validate(data)
        except ValidationError as e:
            last_error = f"JSON did not match required schema: {e}"
            continue

        cv.source_file = source_file
        cv.parsed_at = datetime.now(timezone.utc).isoformat()
        return cv

    raise RuntimeError(
        f"Failed to structure resume into valid JSON after {max_retries + 1} attempts. "
        f"Last error: {last_error}"
    )

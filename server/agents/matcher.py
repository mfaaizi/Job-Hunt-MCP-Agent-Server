"""
Matcher agent: scores how well a resume fits a job posting.

Uses Ollama embeddings for semantic similarity (cosine similarity between
resume text and job description), plus a simple keyword overlap check for
skills. Deliberately reuses the Ollama instance already running for resume
parsing — no separate ML library (e.g. sentence-transformers/torch) needed.
"""
import math
from typing import List, Tuple

import ollama

from server.config import settings


def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Get embeddings for multiple texts in a single Ollama call."""
    response = ollama.embed(model=settings.EMBEDDING_MODEL, input=texts)
    return list(response.embeddings)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_skill_overlap(skills: List[str], job_text: str) -> Tuple[List[str], List[str]]:
    """
    Simple case-insensitive substring match between the resume's flat skills
    list and the job description text. Deliberately simple and fast — this
    complements the embedding similarity score rather than replacing it, and
    gives the caller a concrete, explainable list rather than just a number.
    """
    job_text_lower = job_text.lower()
    matched = [s for s in skills if s.lower() in job_text_lower]
    missing = [s for s in skills if s.lower() not in job_text_lower]
    return matched, missing


def score_resume_against_job(resume_text: str, job_text: str) -> float:
    """Returns a 0.0-1.0 similarity score between resume text and job text."""
    embeddings = get_embeddings_batch([resume_text, job_text])
    similarity = cosine_similarity(embeddings[0], embeddings[1])
    # Cosine similarity is mathematically in [-1, 1]; same-domain text pairs
    # in practice score positive, but clamp defensively either way.
    return max(0.0, min(1.0, similarity))


def score_resume_embedding_against_job(resume_embedding: List[float], job_text: str) -> float:
    """
    Same as score_resume_against_job, but takes an already-computed resume
    embedding instead of re-embedding the resume text. Used when scoring many
    jobs against the same resume in one call (e.g. rank_jobs) — embeds the
    resume once, reuses it for every job, instead of re-embedding it
    redundantly on every single comparison.
    """
    job_embedding = get_embeddings_batch([job_text])[0]
    similarity = cosine_similarity(resume_embedding, job_embedding)
    return max(0.0, min(1.0, similarity))

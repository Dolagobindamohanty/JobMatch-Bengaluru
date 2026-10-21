"""Lazy Hugging Face powered semantic search and grounded job assistance.

The module deliberately has no import-time dependency on ``huggingface_hub`` or
an API token.  This keeps local database work, the existing resume flows, and
test collection usable when AI dependencies are not installed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable
from typing import Any

from jobmatch_bengaluru.classifiers import extract_skills


HF_TOKEN_ENV = "HF_TOKEN"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CHAT_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# Tests can replace this symbol with a fake without importing huggingface_hub.
InferenceClient = None


def embedding_model() -> str:
    return os.getenv("HF_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def chat_model() -> str:
    return os.getenv("HF_CHAT_MODEL", DEFAULT_CHAT_MODEL)


def provider_configured() -> bool:
    """Return whether the required provider credential is available."""
    return bool(os.getenv(HF_TOKEN_ENV, "").strip())


def _client():
    if not provider_configured():
        raise RuntimeError("Hugging Face provider is not configured")
    global InferenceClient
    if InferenceClient is None:
        try:
            from huggingface_hub import InferenceClient as _InferenceClient
        except ImportError as error:
            raise RuntimeError("Hugging Face client dependency is unavailable") from error
        InferenceClient = _InferenceClient
    # The token is passed only to the SDK; it is never included in logs or API
    # responses.
    return InferenceClient(token=os.environ[HF_TOKEN_ENV].strip())


def _flatten_numbers(value: Any) -> list[float]:
    """Convert nested Python/numpy-like arrays into one finite float vector."""
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (str, bytes)) or value is None:
        return []
    if isinstance(value, Iterable):
        result: list[float] = []
        for item in value:
            result.extend(_flatten_numbers(item))
        return result
    try:
        number = float(value)
    except (TypeError, ValueError):
        return []
    return [number] if math.isfinite(number) else []


def _normalize(values: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude == 0:
        return values
    return [value / magnitude for value in values]


def embed_text(text: str) -> list[float]:
    """Generate and L2-normalize one embedding through Hugging Face."""
    response = _client().feature_extraction(text or "", model=embedding_model())
    values = _flatten_numbers(response)
    if not values:
        raise RuntimeError("Hugging Face returned an empty embedding")
    return _normalize(values)


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if not left_values or not right_values:
        return 0.0
    size = min(len(left_values), len(right_values))
    numerator = sum(left_values[index] * right_values[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left_values[:size]))
    right_norm = math.sqrt(sum(value * value for value in right_values[:size]))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def job_embedding_text(job: dict[str, Any]) -> str:
    skills = job.get("skills") or []
    if not isinstance(skills, list):
        skills = []
    return "\n".join((
        f"Title: {job.get('title', '')}",
        f"Company: {job.get('company', '')}",
        f"Location: {job.get('location', '')}",
        f"Skills: {', '.join(str(skill) for skill in skills)}",
        f"Description: {job.get('description', '')}",
    ))


def job_content_hash(job: dict[str, Any]) -> str:
    existing = job.get("content_hash")
    if existing:
        return str(existing)
    payload = "\x1f".join(str(job.get(key, "")) for key in
                            ("title", "location", "description", "url"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semantic_rank(query: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank jobs by semantic similarity and add explainable skill overlap."""
    query_vector = embed_text(query)
    query_skills = set(extract_skills(query))
    ranked = []
    for job in jobs:
        vector = job.get("_embedding")
        if vector is None:
            vector = embed_text(job_embedding_text(job))
        skills = job.get("skills") or []
        if not isinstance(skills, list):
            skills = []
        normalized_skills = {str(skill).strip().casefold() for skill in skills if str(skill).strip()}
        matched = sorted(query_skills & normalized_skills)
        item = {key: value for key, value in job.items() if not key.startswith("_")}
        item["similarity_score"] = cosine_similarity(query_vector, vector)
        item["matched_skills"] = matched
        ranked.append(item)
    ranked.sort(key=lambda item: (-item["similarity_score"],
                                  str(item.get("company", "")).casefold(),
                                  str(item.get("job_id", ""))))
    return ranked


GROUNDING_SYSTEM_PROMPT = """You are JobMatch Bengaluru's grounded job-search copilot.
Answer only from the supplied job context. Never invent or infer salary,
requirements, seniority, company facts, locations, or application details.
If the context does not answer the question, say that the available job
context is insufficient. Keep recommendations tied to the supplied postings.
When mentioning a job, include its exact source application URL from context.
Do not ask for, process, or refer to a resume; this copilot works without one."""


def _safe_context(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = ("source", "company", "job_id", "title", "location", "url", "skills",
              "similarity_score", "matched_skills")
    return [{field: job.get(field) for field in fields if field in job} for job in jobs]


def _message_content(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message", {})
            return str(message.get("content", ""))
        return str(response.get("content", ""))
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        if isinstance(message, dict):
            return str(message.get("content", ""))
        return str(getattr(message, "content", ""))
    return str(getattr(response, "content", ""))


def grounded_answer(query: str, jobs: list[dict[str, Any]]) -> str:
    """Ask the chat model to answer using only safe, retrieved job fields."""
    context = json.dumps(_safe_context(jobs), ensure_ascii=False, sort_keys=True)
    response = _client().chat.completions.create(
        model=chat_model(),
        messages=[
            {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
            {"role": "user", "content": f"Question: {query}\nJob context JSON:\n{context}"},
        ],
        temperature=0.1,
        max_tokens=500,
    )
    answer = _message_content(response).strip()
    return answer or "The available job context is insufficient to answer that question."

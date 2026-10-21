"""Local-first semantic search and grounded job assistance.

FastEmbed and its model are loaded only when local semantic search is used.
Hugging Face remains an optional hosted provider for deployments that have a
token and want hosted chat responses.
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
AI_PROVIDER_ENV = "AI_PROVIDER"
AI_EMBEDDING_MODE_ENV = "AI_EMBEDDING_MODE"
AI_CHAT_MODE_ENV = "AI_CHAT_MODE"
AI_LOCAL_EMBEDDING_MODEL_ENV = "AI_LOCAL_EMBEDDING_MODEL"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_CHAT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_EMBEDDING_PROVIDER = "hf-inference"
DEFAULT_CHAT_PROVIDER = "auto"

# Tests can replace this symbol with a fake without importing huggingface_hub.
InferenceClient = None
# FastEmbed is intentionally imported lazily. Tests can replace this symbol
# with a fake without installing the package or downloading a model.
TextEmbedding = None
_local_embedding_instance = None
_local_embedding_instance_model = None
_local_embedding_instance_class = None


def _configured_mode(environment_name: str) -> str | None:
    configured = os.getenv(environment_name)
    if configured is None:
        return None
    configured = configured.strip().lower()
    return configured if configured in {"local", "huggingface"} else "local"


def _legacy_provider_mode() -> str | None:
    configured = os.getenv(AI_PROVIDER_ENV)
    if configured is None:
        return None
    configured = configured.strip().lower()
    return configured if configured in {"local", "huggingface"} else "local"


def embedding_mode() -> str:
    """Return the embedding mode, local by default and independent of chat."""
    return (_configured_mode(AI_EMBEDDING_MODE_ENV) or
            _legacy_provider_mode() or "local")


def chat_mode() -> str:
    """Return the optional chat mode without changing semantic search."""
    return (_configured_mode(AI_CHAT_MODE_ENV) or
            _legacy_provider_mode() or "local")


def provider_mode() -> str:
    """Compatibility alias for callers that historically meant embeddings."""
    return embedding_mode()


def embedding_model() -> str:
    if embedding_mode() == "local":
        return os.getenv(AI_LOCAL_EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL)
    return os.getenv("HF_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def chat_model() -> str:
    return os.getenv("HF_CHAT_MODEL", DEFAULT_CHAT_MODEL)


def embedding_provider() -> str:
    return os.getenv("HF_EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER)


def chat_provider() -> str:
    return os.getenv("HF_CHAT_PROVIDER", DEFAULT_CHAT_PROVIDER)


def _fastembed_class():
    global TextEmbedding
    if TextEmbedding is None:
        try:
            from fastembed import TextEmbedding as _TextEmbedding
        except Exception:
            return None
        TextEmbedding = _TextEmbedding
    return TextEmbedding


def hosted_chat_available() -> bool:
    return chat_mode() == "huggingface" and bool(os.getenv(HF_TOKEN_ENV, "").strip())


def embedding_configured() -> bool:
    """Return whether the configured embedding mode can be used."""
    if embedding_mode() == "local":
        return _fastembed_class() is not None
    return bool(os.getenv(HF_TOKEN_ENV, "").strip())


def chat_configured() -> bool:
    """Return whether optional hosted chat has a token when enabled."""
    if chat_mode() == "local":
        return True
    return bool(os.getenv(HF_TOKEN_ENV, "").strip())


def provider_configured() -> bool:
    """Compatibility alias for embedding configuration."""
    return embedding_configured()


def provider_status() -> dict[str, Any]:
    """Return safe provider state without exposing credentials or exceptions."""
    return {
        # Keep the old fields for clients released before the split modes.
        "provider": embedding_mode(),
        "configured": embedding_configured(),
        "embedding_mode": embedding_mode(),
        "embedding_configured": embedding_configured(),
        "chat_mode": chat_mode(),
        "chat_configured": chat_configured(),
        "embedding_model": embedding_model(),
        "chat_model": chat_model(),
        "hosted_chat": hosted_chat_available(),
    }


def status() -> dict[str, Any]:
    """Compatibility name for callers that want provider status directly."""
    return provider_status()


def _client(provider: Any = None, *, purpose: str = "embedding"):
    configured = embedding_configured() if purpose == "embedding" else chat_configured()
    if not configured:
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
    kwargs: dict[str, Any] = {"token": os.environ[HF_TOKEN_ENV].strip()}
    if provider:
        kwargs["provider"] = provider
    return InferenceClient(**kwargs)


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


def _local_embed_text(text: str) -> list[float]:
    global _local_embedding_instance, _local_embedding_instance_model
    global _local_embedding_instance_class
    embedding_class = _fastembed_class()
    if embedding_class is None:
        raise RuntimeError("Local embedding provider is unavailable")
    model_name = embedding_model()
    if (_local_embedding_instance is None or
            _local_embedding_instance_model != model_name or
            _local_embedding_instance_class is not embedding_class):
        _local_embedding_instance = embedding_class(model_name=model_name)
        _local_embedding_instance_model = model_name
        _local_embedding_instance_class = embedding_class
    try:
        response = next(iter(_local_embedding_instance.embed([text or ""])))
    except (StopIteration, TypeError, ValueError) as error:
        raise RuntimeError("Local embedding provider returned no embedding") from error
    values = _flatten_numbers(response)
    if not values:
        raise RuntimeError("Local embedding provider returned an empty embedding")
    return _normalize(values)


def embed_text(text: str) -> list[float]:
    """Generate and L2-normalize one local or hosted embedding."""
    if embedding_mode() == "local":
        return _local_embed_text(text)
    response = _client(embedding_provider()).feature_extraction(
        text or "", model=embedding_model()
    )
    values = _flatten_numbers(response)
    if not values:
        raise RuntimeError("Hugging Face returned an empty embedding")
    return _normalize(values)


def embedding_cache_key() -> str:
    """Identify both provider and model so cached vectors cannot cross modes."""
    if embedding_mode() == "local":
        return f"local:{embedding_model()}"
    return f"huggingface:{embedding_provider()}:{embedding_model()}"


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
    """Use hosted chat when enabled, falling back to a local grounded summary."""
    if chat_mode() == "local":
        return local_grounded_summary(jobs)

    context = json.dumps(_safe_context(jobs), ensure_ascii=False, sort_keys=True)
    try:
        response = _client(chat_provider(), purpose="chat").chat.completions.create(
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
    except Exception:
        # Hosted chat is an enhancement; semantic retrieval and its grounded
        # answer remain available when a provider rejects or cannot serve a call.
        return local_grounded_summary(jobs)


def local_grounded_summary(jobs: list[dict[str, Any]]) -> str:
    """Build the deterministic, public-field-only copilot answer."""
    context = _safe_context(jobs)
    if not context:
        return "Local grounded summary (not LLM-generated): No retrieved jobs were available."
    lines = [
        "Local grounded summary (not LLM-generated):",
        f"Retrieved {len(context)} job(s) for this search.",
    ]
    for index, job in enumerate(context, start=1):
        details = []
        if job.get("title"):
            details.append(f"Title: {job['title']}")
        if job.get("company"):
            details.append(f"Company: {job['company']}")
        if job.get("location"):
            details.append(f"Location: {job['location']}")
        skills = job.get("skills") or []
        if isinstance(skills, list) and skills:
            details.append("Skills: " + ", ".join(str(skill) for skill in skills))
        lines.append(f"{index}. " + " | ".join(details))
        if job.get("url"):
            lines.append(f"   Apply: {job['url']}")
    return "\n".join(lines)

"""Backend tests for the local-first, resume-independent AI layer."""

import json
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient

import blr_jobs_pipeline as pipeline
from api.app import main
from jobmatch_bengaluru import ai


class FakeChat:
    def __init__(self, response):
        self.completions = self
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeInferenceClient:
    calls = []
    chat = None

    def __init__(self, token, provider=None):
        assert token == "test-token"
        self.chat = self.__class__.chat

    def feature_extraction(self, text, model):
        self.__class__.calls.append((text, model))
        if "python" in text.lower():
            return [[3.0, 0.0]]
        return [[0.0, 4.0]]


class FakeTextEmbedding:
    instances = 0
    calls = []

    def __init__(self, model_name):
        self.model_name = model_name
        self.__class__.instances += 1

    def embed(self, texts):
        for text in texts:
            self.__class__.calls.append((text, self.model_name))
            if "python" in text.lower():
                yield [3.0, 0.0]
            else:
                yield [0.0, 4.0]


def _seed_jobs(path):
    connection = sqlite3.connect(path)
    pipeline.init_db(connection)
    connection.execute(
        """INSERT INTO jobs
           (source, company, job_id, title, location, url, posted, description,
            first_seen, last_seen, active, is_ai, role_category, experience_level,
            skills, content_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("test", "Acme", "1", "Python Engineer", "Bengaluru", "https://apply/1",
         "2026-01-01", "Build Python services", "2026-01-01", "2026-01-01", 1, 0,
         "software_engineering", "mid", json.dumps(["python"]), "hash-1"),
    )
    connection.execute(
        """INSERT INTO jobs
           (source, company, job_id, title, location, url, posted, description,
            first_seen, last_seen, active, is_ai, role_category, experience_level,
            skills, content_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("test", "Beta", "2", "Java Engineer", "Bengaluru", "https://apply/2",
         "2026-01-01", "Build Java services", "2026-01-01", "2026-01-01", 1, 0,
         "software_engineering", "mid", json.dumps(["java"]), "hash-2"),
    )
    connection.commit()
    connection.close()


def test_ai_search_requires_token_and_status_has_no_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "huggingface")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    client = TestClient(main.app)

    response = client.get("/ai/search?q=python")
    assert response.status_code == 503
    status = client.get("/ai/status")
    assert status.status_code == 200
    assert status.json()["provider"] == "huggingface"
    assert status.json()["configured"] is False
    assert "token" not in json.dumps(status.json()).lower()
    assert "secret" not in json.dumps(status.json()).lower()


def test_embedding_normalizes_nested_provider_output(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    FakeInferenceClient.calls = []
    monkeypatch.setattr(ai, "InferenceClient", FakeInferenceClient)
    assert ai.embed_text("python") == [1.0, 0.0]


def test_semantic_search_reuses_job_embedding_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    FakeInferenceClient.calls = []
    monkeypatch.setattr(ai, "InferenceClient", FakeInferenceClient)
    _seed_jobs(main.DB_PATH)
    client = TestClient(main.app)

    first = client.get("/ai/search", params={"q": "python", "limit": 1})
    second = client.get("/ai/search", params={"q": "python", "limit": 1})
    assert first.status_code == second.status_code == 200
    assert first.json()["jobs"][0]["company"] == "Acme"
    assert first.json()["jobs"][0]["matched_skills"] == ["python"]
    assert set(first.json()["jobs"][0]) == {
        "source", "company", "job_id", "title", "location", "url", "skills",
        "similarity_score", "matched_skills",
    }
    # First call: query + two missing jobs. Second call: query only.
    assert len(FakeInferenceClient.calls) == 4
    with sqlite3.connect(main.DB_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ai_job_embeddings").fetchone()[0] == 2


def test_copilot_uses_grounded_prompt_and_exact_response_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    chat = FakeChat(SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Apply at https://apply/1"))]
    ))
    FakeInferenceClient.chat = chat
    FakeInferenceClient.calls = []
    monkeypatch.setattr(ai, "InferenceClient", FakeInferenceClient)
    _seed_jobs(main.DB_PATH)

    response = TestClient(main.app).post(
        "/ai/copilot", json={"query": "Which Python role should I apply to?", "limit": 1}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"answer", "jobs", "model"}
    assert response.json()["jobs"][0]["url"] == "https://apply/1"
    messages = chat.calls[-1]["messages"]
    assert "only from the supplied job context" in messages[0]["content"]
    assert "Never invent" in messages[0]["content"]
    assert "https://apply/1" in messages[1]["content"]
    assert "raw_text" not in messages[1]["content"]
    assert "test-token" not in json.dumps(response.json())


def test_local_status_and_embedding_use_fastembed_without_hf_token(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    FakeTextEmbedding.instances = 0
    FakeTextEmbedding.calls = []
    monkeypatch.setattr(ai, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(ai, "_local_embedding_instance", None)
    monkeypatch.setattr(ai, "_local_embedding_instance_model", None)
    monkeypatch.setattr(ai, "_local_embedding_instance_class", None)

    status = ai.provider_status()
    assert status == {
        "provider": "local",
        "configured": True,
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "chat_model": "Qwen/Qwen2.5-7B-Instruct",
        "hosted_chat": False,
    }
    assert ai.embed_text("python") == [1.0, 0.0]
    assert "test-token" not in json.dumps(status)


def test_local_semantic_search_reuses_job_embedding_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    FakeTextEmbedding.instances = 0
    FakeTextEmbedding.calls = []
    monkeypatch.setattr(ai, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(ai, "_local_embedding_instance", None)
    monkeypatch.setattr(ai, "_local_embedding_instance_model", None)
    monkeypatch.setattr(ai, "_local_embedding_instance_class", None)
    _seed_jobs(main.DB_PATH)

    client = TestClient(main.app)
    first = client.get("/ai/search", params={"q": "python", "limit": 1})
    second = client.get("/ai/search", params={"q": "python", "limit": 1})
    assert first.status_code == second.status_code == 200
    assert first.json()["jobs"][0]["company"] == "Acme"
    assert first.json()["model"] == "BAAI/bge-small-en-v1.5"
    assert FakeTextEmbedding.instances == 1
    assert len(FakeTextEmbedding.calls) == 4
    with sqlite3.connect(main.DB_PATH) as connection:
        assert connection.execute("SELECT model FROM ai_job_embeddings").fetchone()[0] == "local:BAAI/bge-small-en-v1.5"


def test_local_copilot_is_transparent_and_includes_application_url(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(ai, "TextEmbedding", FakeTextEmbedding)
    _seed_jobs(main.DB_PATH)

    response = TestClient(main.app).post(
        "/ai/copilot", json={"query": "Which Python role should I apply to?", "limit": 1}
    )
    assert response.status_code == 200
    assert response.json()["model"] is None
    assert "not LLM-generated" in response.json()["answer"]
    assert "Acme" in response.json()["answer"]
    assert "https://apply/1" in response.json()["answer"]
    assert "test-token" not in json.dumps(response.json())


def test_direct_semantic_ranking_orders_by_similarity(monkeypatch):
    values = {"query": [1.0, 0.0], "first": [1.0, 0.0], "second": [0.0, 1.0]}
    monkeypatch.setattr(ai, "embed_text", lambda text: values[text])
    jobs = [
        {"job_id": "second", "title": "Other", "skills": [] , "_embedding": values["second"]},
        {"job_id": "first", "title": "Python", "skills": ["python"], "_embedding": values["first"]},
    ]
    ranked = ai.semantic_rank("query", jobs)
    assert [job["job_id"] for job in ranked] == ["first", "second"]

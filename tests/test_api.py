import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import main
import blr_jobs_pipeline as pipeline


def test_api_database_url_selects_postgres_adapter_without_live_server(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://example/db")
    monkeypatch.setattr(main, "initialize_postgres", lambda url: sentinel)
    monkeypatch.setattr(main, "PostgresConnection", lambda engine: (engine,))
    assert main.connect() == (sentinel,)


def test_job_api_lists_and_filters(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    connection = sqlite3.connect(db)
    pipeline.init_db(connection)
    job = {
        "job_id": "api-1", "title": "ML Engineer", "location": "Bengaluru",
        "url": "https://jobs/api-1", "posted": "2026-01-04",
        "description": "Python and PyTorch", "is_ai": 1,
        "role_category": "ai_ml", "experience_level": "mid",
        "skills": ["python", "pytorch"],
    }
    pipeline.upsert(connection, "fixture", "Acme", [job], "2026-01-04T00:00:00+00:00")
    connection.close()
    monkeypatch.setattr(main, "DB_PATH", db)
    client = TestClient(main.app)
    response = client.get("/jobs", params={"ai_only": "true", "q": "pytorch"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["jobs"][0]["skills"] == ["python", "pytorch"]


def test_api_root_is_a_friendly_health_entrypoint():
    response = TestClient(main.app).get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_job_api_returns_404_for_missing_job(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    connection = sqlite3.connect(db)
    pipeline.init_db(connection)
    connection.close()
    monkeypatch.setattr(main, "DB_PATH", db)
    response = TestClient(main.app).get("/jobs/fixture/Acme/missing")
    assert response.status_code == 404


def test_refresh_starts_only_when_pipeline_run_is_stale(monkeypatch):
    class Process:
        def poll(self):
            return None

    started = []
    monkeypatch.setattr(main, "_refresh_process", None)
    monkeypatch.setattr(main, "_last_pipeline_refresh", lambda: (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).isoformat())
    monkeypatch.setattr(
        main.subprocess, "Popen",
        lambda *args, **kwargs: started.append((args, kwargs)) or Process(),
    )
    monkeypatch.setattr(main, "REFRESH_INTERVAL_SECONDS", 24 * 60 * 60)

    result = main.refresh_if_stale()
    assert result["status"] == "started"
    assert started and started[0][0][0][0] == main.sys.executable
    assert main.refresh_if_stale() == {"status": "running"}


def test_refresh_requires_configured_token(monkeypatch):
    monkeypatch.setattr(main, "REFRESH_TOKEN", "scheduled-refresh-secret")
    called = []
    monkeypatch.setattr(main, "refresh_if_stale", lambda: called.append(True) or {"status": "started"})
    client = TestClient(main.app)

    missing = client.post("/refresh")
    incorrect = client.post("/refresh", headers={"X-Refresh-Token": "wrong"})

    assert missing.status_code == 401
    assert incorrect.status_code == 401
    assert called == []


def test_refresh_accepts_configured_token(monkeypatch):
    monkeypatch.setattr(main, "REFRESH_TOKEN", "scheduled-refresh-secret")
    monkeypatch.setattr(main, "refresh_if_stale", lambda: {"status": "started"})

    response = TestClient(main.app).post(
        "/refresh", headers={"X-Refresh-Token": "scheduled-refresh-secret"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "started"}


def test_refresh_does_not_require_token_when_unconfigured(monkeypatch):
    monkeypatch.setattr(main, "REFRESH_TOKEN", None)
    monkeypatch.setattr(main, "refresh_if_stale", lambda: {"status": "started"})

    response = TestClient(main.app).post("/refresh")

    assert response.status_code == 200
    assert response.json() == {"status": "started"}


@pytest.fixture(params=["sqlite", "postgres-adapter"])
def skill_client(request, tmp_path, monkeypatch):
    db = tmp_path / "skill_jobs.db"
    with sqlite3.connect(db) as connection:
        pipeline.init_db(connection)
        fixtures = [
            ("1", ["JavaScript"], 1, "Platform Engineer", 1),
            ("2", ["java", "JAVA"], 1, "Platform Engineer", 1),
            ("3", ["  JaVa  ", "Python"], 0, "Platform Engineer", 1),
            ("4", ["JAVA"], 1, "Data Engineer", 1),
            ("5", ["java"], 1, "Platform Engineer", 0),
            ("6", [], 1, "Java Platform Engineer", 1),
            ("7", ["Java", "Python"], 1, "Platform Engineer", 1),
            ("8", ["C++", "100%", "a_b", 'say "hi"'], 0, "Engineer", 1),
        ]
        for job_id, skills, is_ai, title, active in fixtures:
            pipeline.upsert(connection, "fixture", "Acme", [{
                "job_id": job_id, "title": title, "location": "Bengaluru",
                "url": f"https://jobs/{job_id}", "posted": f"2026-01-{job_id.zfill(2)}",
                "description": "Java development", "is_ai": is_ai,
                "role_category": "backend", "experience_level": "mid", "skills": skills,
            }], "2026-01-10T00:00:00+00:00")
            connection.execute("UPDATE jobs SET active=? WHERE job_id=?", (active, job_id))
        # Legacy/malformed values must not be treated as skill arrays or fail a request.
        for job_id, skills in [("1", '["JavaScript"]'), ("6", '{"skill": "java"}')]:
            connection.execute("UPDATE jobs SET skills=? WHERE job_id=?", (skills, job_id))
    monkeypatch.setattr(main, "DATABASE_URL", None)
    monkeypatch.setattr(main, "DB_PATH", db)
    engine = None
    if request.param == "postgres-adapter":
        sqlalchemy = pytest.importorskip("sqlalchemy")
        # Exercise real adapter parameter/boolean translation and SQLAlchemy rows.
        # SQLite is only the transport here; this is not a live PostgreSQL test.
        engine = sqlalchemy.create_engine(f"sqlite:///{db}")
        monkeypatch.setattr(main, "connect", lambda: main.PostgresConnection(engine))
        monkeypatch.setattr(main, "table_exists", lambda connection: True)
    yield TestClient(main.app)
    if engine is not None:
        engine.dispose()


@pytest.mark.parametrize("skill", ["java", "JAVA", "jAvA", "  Java  "])
def test_skill_filter_is_normalized_exact_membership(skill_client, skill):
    response = skill_client.get("/jobs", params={"skill": skill})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert {job["job_id"] for job in data["jobs"]} == {"2", "3", "4", "7"}


@pytest.mark.parametrize("skill", ["jav", "script", "C+", "%", "a", "missing"])
def test_skill_filter_does_not_match_partial_skills(skill_client, skill):
    data = skill_client.get("/jobs", params={"skill": skill}).json()
    assert data["jobs"] == []
    assert data["total"] == data["total_pages"] == 0


@pytest.mark.parametrize("skill", ["C++", "100%", "a_b", 'say "hi"'])
def test_skill_filter_handles_literal_special_characters(skill_client, skill):
    data = skill_client.get("/jobs", params={"skill": skill}).json()
    assert data["total"] == 1
    assert data["jobs"][0]["job_id"] == "8"


@pytest.mark.parametrize("stored", [None, "", "not json", '"java"', '{"skill":"java"}', '[null, 123]'])
def test_skill_filter_ignores_missing_or_malformed_skill_arrays(skill_client, stored):
    with main.connect() as connection:
        connection.execute("UPDATE jobs SET skills=?", (stored,))
    data = skill_client.get("/jobs", params={"skill": "java"}).json()
    assert data["total"] == 0
    assert data["jobs"] == []


def test_skill_filter_combines_search_ai_and_other_filters_before_pagination(skill_client):
    params = {"skill": "Java", "q": "Platform", "ai_only": "true",
              "company": "acme", "role_category": "backend", "experience_level": "mid",
              "page_size": 1}
    first = skill_client.get("/jobs", params=params).json()
    second = skill_client.get("/jobs", params={**params, "page": 2}).json()
    beyond = skill_client.get("/jobs", params={**params, "page": 3}).json()
    assert [first["jobs"][0]["job_id"], second["jobs"][0]["job_id"]] == ["7", "2"]
    for page, data in enumerate([first, second, beyond], 1):
        assert data["total"] == data["total_pages"] == 2
        assert data["page"] == page
        assert data["page_size"] == 1
    assert beyond["jobs"] == []
    assert skill_client.get("/jobs", params={**params, "q": "unmatched"}).json()["total"] == 0


def test_skill_filter_empty_and_omitted_preserve_defaults_and_ai_calls(skill_client):
    unfiltered = skill_client.get("/jobs").json()
    for skill in ["", "   "]:
        assert skill_client.get("/jobs", params={"skill": skill}).json() == unfiltered
    assert main.list_jobs() == unfiltered
    ai = skill_client.get("/jobs/ai")
    assert ai.status_code == 200
    assert ai.json() == main.ai_jobs()
    assert ai.json()["total"] == 5
    assert skill_client.get("/jobs/ai", params={"q": "Data"}).json()["total"] == 1

import sqlite3
from datetime import datetime, timedelta, timezone

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

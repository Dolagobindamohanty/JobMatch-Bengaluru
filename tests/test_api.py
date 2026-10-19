import sqlite3

from fastapi.testclient import TestClient

from api.app import main
import blr_jobs_pipeline as pipeline


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

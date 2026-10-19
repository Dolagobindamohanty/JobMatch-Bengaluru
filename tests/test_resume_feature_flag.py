from fastapi.testclient import TestClient

from api.app import main


def test_production_disables_resume_and_account_operations_before_storage_or_db(
    monkeypatch,
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JOBMATCH_RESUME_ENABLED", raising=False)

    def fail_if_touched():
        raise AssertionError("disabled feature touched storage or database")

    monkeypatch.setattr(main, "connect", fail_if_touched)
    monkeypatch.setattr(main, "_resume_storage", fail_if_touched)
    client = TestClient(main.app)
    requests = [
        ("post", "/resumes", {"files": {"file": ("resume.txt", b"Python")}}),
        ("get", "/resumes/resume-1", {}),
        ("patch", "/resumes/resume-1/skills", {"json": ["python"]}),
        ("delete", "/resumes/resume-1", {}),
        ("get", "/resumes/resume-1/matches", {}),
        ("get", "/resumes/resume-1/gaps", {}),
        ("get", "/resumes/resume-1/suggestions", {}),
        ("get", "/resumes/resume-1/roles", {}),
        ("post", "/resume-versions", {"json": {"label": "v1"}}),
        ("get", "/resume-versions", {}),
        ("post", "/resumes/resume-1/versions", {"json": {"label": "v1"}}),
        ("get", "/resumes/resume-1/versions", {}),
        ("get", "/account", {}),
        ("patch", "/account", {"json": {"display_name": "Alice"}}),
        ("delete", "/account/data", {}),
        ("delete", "/account", {}),
        ("post", "/saved-jobs", {"json": {"source": "x", "company": "y", "job_id": "z"}}),
        ("get", "/saved-jobs", {}),
        ("get", "/applications", {}),
    ]

    for method, path, kwargs in requests:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 503, (method, path, response.text)
        assert response.json()["detail"] == main.FEATURE_DISABLED_DETAIL


def test_production_keeps_health_and_job_browsing_available(monkeypatch, tmp_path):
    import sqlite3
    import blr_jobs_pipeline as pipeline

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JOBMATCH_RESUME_ENABLED", raising=False)
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    connection = sqlite3.connect(main.DB_PATH)
    pipeline.init_db(connection)
    connection.close()
    client = TestClient(main.app)

    assert client.get("/health").status_code == 200
    assert client.get("/jobs").status_code == 200
    assert client.get("/skills/trending").status_code == 200


def test_explicit_resume_flag_overrides_production_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JOBMATCH_RESUME_ENABLED", "true")
    assert main.resume_features_enabled() is True

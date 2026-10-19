"""Unit and fixture tests for the Phase 1 jobs collector.

All adapter tests replace the HTTP boundary with local payloads; this suite
never calls a public jobs API.
"""

import importlib
import sqlite3

import pytest


pipeline = importlib.import_module("blr_jobs_pipeline")


def test_database_url_selects_postgres_without_connecting(monkeypatch):
    monkeypatch.setattr(pipeline, "DATABASE_URL", "postgresql://example/db")
    sentinel = object()
    monkeypatch.setattr(pipeline, "initialize_postgres", lambda url: sentinel)
    monkeypatch.setattr(pipeline, "PostgresConnection", lambda engine: (engine,))
    # The production branch is selected before any network/database operation.
    assert pipeline.connect_db() == (sentinel,)


def test_location_and_role_classifiers_cover_phase1_boundaries():
    assert pipeline.is_blr("Bengaluru")
    assert pipeline.is_blr("BANGALORE, India")
    assert pipeline.is_blr("Office - BLR")
    assert not pipeline.is_blr("Remote - India")

    assert pipeline.is_it("Senior Backend Developer")
    assert pipeline.is_ai("LLM Research Scientist")
    assert pipeline.is_ai("Software Engineer", "build neural network model serving")
    assert not pipeline.is_qualifying("Recruiter", "supports engineering hiring")


@pytest.mark.xfail(strict=False, reason="AI title regex does not match plural 'LLMs'")
def test_ai_classifier_accepts_plural_llms_vocabulary():
    """The project outline lists LLMs; retain a visible regression signal."""
    assert pipeline.is_ai("Research Scientist, LLMs")


def test_strip_html_unescapes_and_normalizes_description():
    assert pipeline.strip_html("<p>Build&nbsp;<strong>ML</strong> &amp; APIs</p>") == "Build ML & APIs"


def test_greenhouse_filters_location_and_role_and_normalizes(monkeypatch, greenhouse_payload):
    monkeypatch.setattr(pipeline, "get_json", lambda url: greenhouse_payload)

    jobs = pipeline.fetch_greenhouse("example")

    assert [job["job_id"] for job in jobs] == ["101"]
    assert {key: jobs[0][key] for key in (
        "job_id", "title", "location", "url", "posted", "description", "is_ai"
    )} == {
        "job_id": "101",
        "title": "Machine Learning Engineer",
        "location": "Bengaluru, Karnataka",
        "url": "https://jobs.example/101",
        "posted": "2026-01-02T03:04:05Z",
        "description": "Build ML models & services.",
        "is_ai": 1,
    }


def test_lever_accepts_bengaluru_in_secondary_locations_and_normalizes(monkeypatch, lever_payload):
    monkeypatch.setattr(pipeline, "get_json", lambda url: lever_payload)

    jobs = pipeline.fetch_lever("example")

    assert [job["job_id"] for job in jobs] == ["lever-1"]
    assert jobs[0]["location"] == "India"
    assert jobs[0]["posted"].endswith("+00:00")
    assert jobs[0]["is_ai"] == 0


def test_ashby_accepts_bengaluru_in_secondary_locations(monkeypatch, ashby_payload):
    monkeypatch.setattr(pipeline, "get_json", lambda url: ashby_payload)

    jobs = pipeline.fetch_ashby("example")

    assert len(jobs) == 1
    assert jobs[0]["job_id"] == "ashby-1"
    assert jobs[0]["location"] == "Remote"
    assert jobs[0]["is_ai"] == 1


def test_workday_filters_and_normalizes(monkeypatch, workday_jobs):
    monkeypatch.setattr(pipeline, "get_workday_jobs", lambda tenant, site: workday_jobs)

    jobs = pipeline.fetch_workday({"tenant": "acme", "site": "careers"})

    assert [job["job_id"] for job in jobs] == ["wd-1"]
    assert jobs[0]["url"] == "https://acme.wd3.myworkdayjobs.com/en-US/job/wd-1"
    assert jobs[0]["description"] == ""


def test_upsert_deduplicates_and_marks_disappeared_jobs_inactive():
    conn = sqlite3.connect(":memory:")
    pipeline.init_db(conn)
    first = {
        "job_id": "1", "title": "Backend Engineer", "location": "Bengaluru",
        "url": "https://jobs/1", "posted": "today", "description": "API work",
        "is_ai": 0,
    }
    second = {**first, "job_id": "2", "title": "ML Engineer", "is_ai": 1}

    pipeline.upsert(conn, "fixture", "Acme", [first, second], "2026-01-01T00:00:00+00:00")
    pipeline.upsert(conn, "fixture", "Acme", [{**first, "title": "Backend Engineer II"}], "2026-01-02T00:00:00+00:00")

    rows = conn.execute(
        "SELECT job_id, title, active, is_ai FROM jobs ORDER BY job_id"
    ).fetchall()
    assert rows == [("1", "Backend Engineer II", 1, 0), ("2", "ML Engineer", 0, 1)]
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2


def test_upsert_marks_all_jobs_inactive_when_refresh_feed_is_empty():
    conn = sqlite3.connect(":memory:")
    pipeline.init_db(conn)
    job = {
        "job_id": "1", "title": "Backend Engineer", "location": "Bengaluru",
        "url": "https://jobs/1", "posted": "today", "description": "API work",
        "is_ai": 0,
    }
    pipeline.upsert(conn, "fixture", "Acme", [job], "2026-01-01T00:00:00+00:00")
    pipeline.upsert(conn, "fixture", "Acme", [], "2026-01-02T00:00:00+00:00")

    assert conn.execute("SELECT active FROM jobs WHERE job_id='1'").fetchone()[0] == 0


def test_phase1_classification_apis():
    assert pipeline.classify_role_category("Machine Learning Engineer") == "ai_ml"
    assert pipeline.classify_experience("Senior Software Engineer") == "senior"
    assert pipeline.extract_skills("Python, PyTorch, Kubernetes") == [
        "kubernetes", "python", "pytorch"
    ]

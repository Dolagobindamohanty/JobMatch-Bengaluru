"""Unit and fixture tests for the Phase 1 jobs collector.

All adapter tests replace the HTTP boundary with local payloads; this suite
never calls a public jobs API.
"""

import importlib
import json
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


def sample_job(**changes):
    return {
        "job_id": "1", "title": "Backend Engineer", "location": "Bengaluru",
        "url": "https://jobs/1", "posted": "today", "description": "API work",
        "is_ai": 0, **changes,
    }


def test_failure_diagnostic_keeps_sqlstate_without_driver_message():
    driver_error = ValueError("postgresql://user:password@host/db")
    driver_error.sqlstate = "42804"
    error = RuntimeError("SQL and parameters with private data")
    error.orig = driver_error
    assert pipeline.failure_diagnostic(error, "persist jobs") == (
        "persist jobs: RuntimeError (SQLSTATE 42804)"
    )


@pytest.mark.parametrize("ai_flag", [0, 1, False, True, None])
def test_postgres_upsert_binds_native_bool_and_text_id(ai_flag):
    """Exercise the actual untyped SQL adapter, rejecting SQLite-only values."""
    pytest.importorskip("sqlalchemy")

    class StrictDriver:
        inserted = False

        def execute(self, statement, values):
            if "INSERT INTO jobs" in str(statement):
                assert type(values["p10"]) is bool, "PostgreSQL BOOLEAN rejects integer binds"
                assert values["p10"] is bool(ai_flag)
                assert type(values["p2"]) is str, "PostgreSQL job_id is TEXT"
                assert values["p2"] == "123"
                self.inserted = True

        def commit(self):
            pass

    class Engine:
        driver = StrictDriver()

        def connect(self):
            return self.driver

    engine = Engine()
    conn = pipeline.PostgresConnection(engine)
    pipeline.upsert(conn, "lever", "example", [sample_job(job_id=123, is_ai=ai_flag)], "now")
    assert engine.driver.inserted


@pytest.mark.parametrize("source", ["greenhouse", "lever", "ashby", "workday"])
def test_all_fetchers_normalize_numeric_ids(monkeypatch, source):
    payloads = {
        "greenhouse": {"jobs": [{"id": 123, "title": "Software Engineer",
                                  "location": {"name": "Bengaluru"}}]},
        "lever": [{"id": 123, "text": "Software Engineer",
                   "categories": {"location": "Bengaluru"}}],
        "ashby": {"jobs": [{"id": 123, "title": "Software Engineer", "location": "Bengaluru"}]},
    }
    monkeypatch.setattr(pipeline, "get_json", lambda url: payloads[source])
    monkeypatch.setattr(pipeline, "get_workday_jobs", lambda tenant, site: [
        {"bulletFields": [123], "title": "Software Engineer", "locationsText": "Bengaluru"}
    ])
    spec = {"tenant": "example", "site": "careers"} if source == "workday" else "example"
    assert pipeline.FETCHERS[source](spec)[0]["job_id"] == "123"


@pytest.mark.parametrize("failure_stage", ["fetch", "company", "insert", "receipt"])
def test_run_rolls_back_failed_board_records_failure_and_continues(
    monkeypatch, tmp_path, capsys, failure_stage,
):
    db = tmp_path / "jobs.sqlite"
    real = sqlite3.connect(db)
    pipeline.init_db(real)
    pipeline.upsert(real, "fixture", "broken", [sample_job(job_id="old")], "2000")
    secret = "postgresql://admin:secret@host/db?token=private"

    class Connection:
        """Mimic PostgreSQL's aborted transaction until rollback is issued."""
        aborted = False
        rollbacks = 0
        closed = False

        def execute(self, sql, params=()):
            assert not self.aborted, "rollback required before further SQL"
            fail = (
                (failure_stage == "company" and "INSERT INTO companies" in sql and params[1] == "broken")
                or (failure_stage == "insert" and "INSERT INTO jobs" in sql and params[2] == "bad")
                or (failure_stage == "receipt" and "SET finished_at=?, jobs_found=?" in sql and params[2] == 1)
            )
            if fail:
                self.aborted = True
                raise RuntimeError(secret)
            return real.execute(sql, params)

        def commit(self):
            assert not self.aborted
            real.commit()

        def rollback(self):
            self.rollbacks += 1
            self.aborted = False
            real.rollback()

        def close(self):
            self.closed = True
            real.close()

    conn = Connection()
    called = []

    def fetch(company):
        called.append(company)
        if company == "broken":
            if failure_stage == "fetch":
                raise RuntimeError(secret)
            return [sample_job(job_id="partial"), sample_job(job_id="bad")]
        return [sample_job(job_id=456)]

    config = tmp_path / "companies.json"
    config.write_text(json.dumps({"fixture": ["broken", "healthy"]}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "connect_db", lambda: conn)
    monkeypatch.setattr(pipeline, "FETCHERS", {"fixture": fetch})
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)

    assert pipeline.run(config) == 0
    assert called[-1] == "healthy"
    assert conn.rollbacks == 1
    assert conn.closed
    with sqlite3.connect(db) as check:
        assert check.execute("SELECT company, job_id, active FROM jobs ORDER BY company").fetchall() == [
            ("broken", "old", 1), ("healthy", "456", 1),
        ]
        runs = check.execute("SELECT company, finished_at, jobs_found, error FROM pipeline_runs ORDER BY id").fetchall()
        assert len(runs) == 2
        assert runs[0][0] == "broken" and runs[0][1] and runs[0][2] == 0
        assert runs[0][3].endswith(": RuntimeError")
        assert runs[1][0] == "healthy" and runs[1][1] and runs[1][2:] == (1, None)
        assert secret not in str(runs)
    output = capsys.readouterr().out
    assert "FAILED" in output and "1 Bengaluru jobs seen" in output
    assert "secret" not in output and "private" not in output


@pytest.mark.parametrize("fails, expected", [(True, 1), (False, 0)])
def test_run_all_failed_is_nonzero_but_successful_empty_feed_is_success(
    monkeypatch, tmp_path, fails, expected,
):
    db = tmp_path / "jobs.sqlite"
    monkeypatch.setattr(pipeline, "connect_db", lambda: sqlite3.connect(db))

    def fetch(company):
        if fails:
            raise ValueError("private feed credentials")
        return []

    monkeypatch.setattr(pipeline, "FETCHERS", {"fixture": fetch})
    monkeypatch.setattr(pipeline.time, "sleep", lambda seconds: None)
    config = tmp_path / "companies.json"
    config.write_text(json.dumps({"fixture": ["one", "two"]}), encoding="utf-8")
    assert pipeline.run(config) == expected
    with sqlite3.connect(db) as check:
        rows = check.execute("SELECT finished_at, error FROM pipeline_runs").fetchall()
    assert len(rows) == 2
    assert all(finished for finished, error in rows)
    assert all(bool(error) is fails for finished, error in rows)

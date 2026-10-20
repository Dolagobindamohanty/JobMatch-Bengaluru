"""Refresh lifecycle checks with no child execution or external database access."""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import main


class Database:
    def __init__(self, active=0, last=None):
        self.active = active
        self.last = last
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql):
        self.queries.append(sql)
        self.row = (self.active,) if "COUNT(*)" in sql else (self.last,)
        return self

    def fetchone(self):
        return self.row


class Process:
    code = None

    def poll(self):
        return self.code


@pytest.fixture
def lifecycle(monkeypatch):
    db = Database(last=datetime.now(timezone.utc).isoformat())
    children = []

    def spawn(*args, **kwargs):
        child = Process()
        children.append((child, args, kwargs))
        return child

    monkeypatch.setattr(main, "connect", lambda: db)
    monkeypatch.setattr(main, "table_exists", lambda connection: True)
    monkeypatch.setattr(main.subprocess, "Popen", spawn)
    monkeypatch.setattr(main, "_refresh_process", None)
    monkeypatch.setattr(main, "_refresh_state", "idle")
    monkeypatch.setattr(main, "_refresh_exit_code", None)
    monkeypatch.setattr(main, "_refresh_lock", threading.Lock())
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://secret@example/jobs")
    monkeypatch.setattr(main, "REFRESH_ON_STARTUP", False)
    monkeypatch.setattr(main, "REFRESH_EMPTY_ON_STARTUP", True)
    monkeypatch.setattr(main, "REFRESH_INTERVAL_SECONDS", 86400)
    return db, children


def test_empty_feed_bypasses_recent_success_and_inherits_logs(lifecycle):
    db, children = lifecycle
    assert main.refresh_if_stale()["status"] == "started"
    assert not any("pipeline_runs" in sql for sql in db.queries)
    assert children[0][2]["stdout"] is None
    assert children[0][2]["stderr"] is None
    assert main.refresh_if_stale() == {"status": "running"}
    assert len(children) == 1


def test_nonempty_feed_keeps_freshness_gate(lifecycle):
    db, children = lifecycle
    db.active = 12
    assert main.refresh_if_stale()["status"] == "fresh"
    assert children == []
    db.last = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert main.refresh_if_stale()["status"] == "started"


@pytest.mark.parametrize("exit_code, expected", [(0, "completed"), (1, "failed"), (-9, "failed")])
def test_public_status_reaps_child_and_exposes_only_safe_fields(lifecycle, monkeypatch, exit_code, expected):
    db, children = lifecycle
    monkeypatch.setattr(main, "REFRESH_TOKEN", "secret-token")
    client = TestClient(main.app)
    assert client.get("/refresh/status").json() == {
        "status": "idle", "last_exit_code": None, "active_job_count": 0,
    }
    main.refresh_if_stale()
    assert client.get("/refresh/status").json()["status"] == "running"
    children[0][0].code = exit_code
    db.active = 7
    expected_payload = {"status": expected, "last_exit_code": exit_code, "active_job_count": 7}
    assert client.get("/refresh/status").json() == expected_payload
    assert client.get("/refresh/status").json() == expected_payload
    assert main._refresh_process is None


def test_completed_empty_refresh_can_be_retried(lifecycle):
    _, children = lifecycle
    main.refresh_if_stale()
    children[0][0].code = 0
    assert main.refresh_if_stale()["status"] == "started"
    assert len(children) == 2
    assert main.refresh_status()["last_exit_code"] == 0


def test_database_failure_is_not_mistaken_for_empty_feed(lifecycle, monkeypatch):
    _, children = lifecycle

    def unavailable():
        raise RuntimeError("secret-password /private/database")

    monkeypatch.setattr(main, "connect", unavailable)
    with pytest.raises(HTTPException) as error:
        main.refresh_if_stale()
    assert error.value.status_code == 503
    assert error.value.detail == "database unavailable"
    assert children == []
    assert TestClient(main.app).get("/refresh/status").json() == {
        "status": "failed", "last_exit_code": None, "active_job_count": None,
    }


def test_spawn_failure_releases_lock_and_can_retry(lifecycle, monkeypatch):
    _, children = lifecycle
    spawn = main.subprocess.Popen

    def unavailable(*args, **kwargs):
        raise OSError("secret /private/script")

    monkeypatch.setattr(main.subprocess, "Popen", unavailable)
    with pytest.raises(HTTPException) as error:
        main.refresh_if_stale()
    assert error.value.detail == "refresh unavailable"
    assert main.refresh_status()["status"] == "failed"
    assert main._refresh_lock.acquire(blocking=False)
    main._refresh_lock.release()
    monkeypatch.setattr(main.subprocess, "Popen", spawn)
    assert main.refresh_if_stale()["status"] == "started"
    assert len(children) == 1


def test_missing_jobs_table_is_an_empty_feed(lifecycle, monkeypatch):
    db, children = lifecycle
    monkeypatch.setattr(main, "table_exists", lambda connection: False)
    assert main.refresh_if_stale()["status"] == "started"
    assert db.queries == []
    assert len(children) == 1


def test_status_database_failure_does_not_hide_running_child(lifecycle, monkeypatch):
    main.refresh_if_stale()

    def unavailable():
        raise RuntimeError("private database detail")

    monkeypatch.setattr(main, "connect", unavailable)
    assert main.refresh_status() == {
        "status": "running", "last_exit_code": None, "active_job_count": None,
    }


def test_startup_database_failure_is_contained(lifecycle, monkeypatch, caplog):
    _, children = lifecycle
    threads = []
    real_thread = threading.Thread

    def unavailable():
        raise RuntimeError("private database detail")

    def start_thread(**kwargs):
        thread = real_thread(**kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setattr(main, "connect", unavailable)
    monkeypatch.setattr(main.threading, "Thread", start_thread)
    main.refresh_on_open()
    threads[0].join(timeout=2)
    assert not threads[0].is_alive()
    assert children == []
    assert main._refresh_state == "failed"
    assert "Startup refresh unavailable" in caplog.text
    assert "private database detail" not in caplog.text


@pytest.mark.parametrize("postgres, empty_enabled, ordinary_enabled, active, expected", [
    (True, True, False, 0, 1),
    (True, True, False, 3, 0),
    (True, False, False, 0, 0),
    (False, True, False, 0, 0),
    (False, True, True, 0, 1),
    (True, False, True, 0, 1),
])
def test_startup_refresh_policy(lifecycle, monkeypatch, postgres, empty_enabled, ordinary_enabled, active, expected):
    db, children = lifecycle
    db.active = active
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://fake/jobs" if postgres else None)
    monkeypatch.setattr(main, "REFRESH_EMPTY_ON_STARTUP", empty_enabled)
    monkeypatch.setattr(main, "REFRESH_ON_STARTUP", ordinary_enabled)
    threads = []
    real_thread = threading.Thread

    def start_thread(**kwargs):
        thread = real_thread(**kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setattr(main.threading, "Thread", start_thread)
    main.refresh_on_open()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert len(children) == expected
    if not postgres and not ordinary_enabled:
        assert db.queries == []


def test_startup_does_not_wait_for_database_and_health_remains_available(lifecycle, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    threads = []
    real_thread = threading.Thread
    connect = main.connect

    def blocked_connect():
        if threading.current_thread().name == "startup-refresh":
            entered.set()
            assert release.wait(timeout=5)
        return connect()

    def start_thread(**kwargs):
        thread = real_thread(**kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setattr(main, "connect", blocked_connect)
    monkeypatch.setattr(main.threading, "Thread", start_thread)
    try:
        main.refresh_on_open()
        assert entered.wait(timeout=2)
        assert main.health()["status"] == "ok"
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=2)


def test_concurrent_refresh_requests_launch_only_one_child(lifecycle):
    _, children = lifecycle
    results = []
    threads = [threading.Thread(target=lambda: results.append(main.refresh_if_stale())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert len(children) == 1
    assert sum(result["status"] == "started" for result in results) == 1

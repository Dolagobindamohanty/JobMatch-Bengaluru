from fastapi.testclient import TestClient

from api.app import main


def test_account_resources_persist_and_are_owned_by_local_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    client = TestClient(main.app)
    alice = {"X-Local-User-ID": "alice"}
    bob = {"X-Local-User-ID": "bob"}

    assert client.patch("/account", headers=alice, json={"display_name": "Alice"}).json()["id"] == "alice"
    saved = client.post("/saved-jobs", headers=alice, json={
        "source": "fixture", "company": "Acme", "job_id": "1", "notes": "follow up"
    })
    assert saved.status_code == 201
    search = client.post("/saved-searches", headers=alice, json={
        "name": "ML", "query": "machine learning", "filters": {"ai_only": True}
    })
    assert search.status_code == 201
    application = client.post("/applications", headers=alice, json={
        "company": "Acme", "job_id": "1", "status": "screening"
    })
    assert application.status_code == 201

    assert len(client.get("/saved-jobs", headers=alice).json()["saved_jobs"]) == 1
    assert client.get("/saved-jobs", headers=bob).json()["saved_jobs"] == []
    assert client.get("/saved-searches", headers=alice).json()["saved_searches"][0]["filters"] == {"ai_only": True}
    assert client.get("/applications", headers=alice).json()["applications"][0]["status"] == "screening"
    assert client.get("/applications", headers=bob).json()["applications"] == []


def test_account_data_deletion_removes_owned_records_and_keeps_other_users(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    client = TestClient(main.app)
    alice = {"X-User-ID": "alice"}
    bob = {"X-User-ID": "bob"}
    for headers in (alice, bob):
        client.post("/saved-jobs", headers=headers, json={"source": "fixture", "company": "Acme", "job_id": headers["X-User-ID"]})

    deleted = client.delete("/account/data", headers=alice)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get("/saved-jobs", headers=alice).json()["saved_jobs"] == []
    assert len(client.get("/saved-jobs", headers=bob).json()["saved_jobs"]) == 1
    # Deletion is idempotent from the caller's perspective and does not leak data.
    assert client.get("/account", headers=alice).json()["id"] == "alice"

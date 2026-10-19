from fastapi.testclient import TestClient

from api.app import main


def test_resume_upload_edit_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(main, "RESUME_DIR", tmp_path / "uploads")
    client = TestClient(main.app)
    response = client.post(
        "/resumes", files={"file": ("resume.txt", b"Python developer with 3 years experience and Docker")}
    )
    assert response.status_code == 201
    resume_id = response.json()["id"]
    assert "python" in response.json()["parsed_profile"]["skills"]

    edited = client.patch(f"/resumes/{resume_id}/skills", json=["Python", "PyTorch"])
    assert edited.status_code == 200
    assert edited.json()["parsed_profile"]["skills"] == ["python", "pytorch"]

    fetched = client.get(f"/resumes/{resume_id}")
    assert fetched.status_code == 200
    assert fetched.json()["parsed_profile"]["skills"] == ["python", "pytorch"]

    deleted = client.delete(f"/resumes/{resume_id}")
    assert deleted.status_code == 200
    assert client.get(f"/resumes/{resume_id}").status_code == 404


def test_resume_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    response = TestClient(main.app).post(
        "/resumes", files={"file": ("resume.txt", b"x" * (5 * 1024 * 1024 + 1))}
    )
    assert response.status_code == 400


def test_resume_uses_private_storage_adapter_and_deletes_blob(tmp_path, monkeypatch):
    class FakeStorage:
        def __init__(self):
            self.blobs = {}
            self.put_calls = []
            self.delete_calls = []

        def put(self, key, content, content_type=None):
            self.put_calls.append((key, content_type))
            self.blobs[key] = content

        def delete(self, key):
            self.delete_calls.append(key)
            self.blobs.pop(key, None)

    storage = FakeStorage()
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(main, "_resume_storage", lambda: storage)
    client = TestClient(main.app)

    response = client.post(
        "/resumes", files={"file": ("private.txt", b"Python developer")}
    )
    assert response.status_code == 201
    resume_id = response.json()["id"]
    assert response.json().keys() == {"id", "filename", "parsed_profile", "created_at"}
    assert len(storage.blobs) == 1
    key = next(iter(storage.blobs))
    assert key.startswith(f"resumes/{resume_id}/")
    assert client.get(f"/resumes/{resume_id}").json().keys() == {
        "id", "user_id", "filename", "created_at", "updated_at", "parsed_profile"
    }

    assert client.delete(f"/resumes/{resume_id}").status_code == 200
    assert storage.delete_calls == [key]
    assert storage.blobs == {}


def test_resume_matches_and_role_summary(tmp_path, monkeypatch):
    import sqlite3
    import blr_jobs_pipeline as pipeline
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(main, "RESUME_DIR", tmp_path / "uploads")
    connection = sqlite3.connect(main.DB_PATH)
    pipeline.init_db(connection)
    pipeline.upsert(connection, "fixture", "Acme", [{
        "job_id": "job-1", "title": "Machine Learning Engineer", "location": "Bengaluru",
        "url": "https://jobs/1", "posted": "2026-01-01", "description": "Python models",
        "is_ai": 1, "role_category": "ai_ml", "experience_level": "mid", "skills": ["python", "pytorch"]
    }], "2026-01-01T00:00:00Z")
    connection.close()
    client = TestClient(main.app)
    resume = client.post("/resumes", files={"file": ("resume.txt", b"Python ML engineer with 3 years experience")}).json()
    response = client.get(f"/resumes/{resume['id']}/matches")
    assert response.status_code == 200
    assert response.json()["matches"][0]["match"]["matched_skills"] == ["python"]
    assert client.get(f"/resumes/{resume['id']}/roles").status_code == 200


def test_resume_gaps_aggregate_top_matches_and_conservatively_categorize(tmp_path, monkeypatch):
    import sqlite3
    import blr_jobs_pipeline as pipeline

    monkeypatch.setattr(main, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(main, "RESUME_DIR", tmp_path / "uploads")
    connection = sqlite3.connect(main.DB_PATH)
    pipeline.init_db(connection)
    jobs = [
        ("job-1", ["python", "docker", "kubernetes"]),
        ("job-2", ["python", "docker"]),
        ("job-3", ["python", "kubernetes"]),
    ]
    for job_id, skills in jobs:
        pipeline.upsert(connection, "fixture", "Acme", [{
            "job_id": job_id, "title": "Software Engineer", "location": "Bengaluru",
            "url": f"https://jobs/{job_id}", "posted": "2026-01-01",
            "description": "Python engineering", "is_ai": 0,
            "role_category": "software_engineering", "experience_level": "mid",
            "skills": skills,
        }], "2026-01-01T00:00:00Z")
    connection.close()

    client = TestClient(main.app)
    resume = client.post(
        "/resumes",
        files={"file": ("resume.txt", b"Python developer with 3 years experience and Docker")},
    ).json()
    resume_id = resume["id"]
    client.patch(f"/resumes/{resume_id}/skills", json=["python"])
    # Gaps intentionally read the existing cache rather than recomputing matches.
    assert client.get(f"/resumes/{resume_id}/matches").status_code == 200

    gaps = client.get(f"/resumes/{resume_id}/gaps", params={"limit": 3})
    assert gaps.status_code == 200
    body = gaps.json()
    assert body["top_matches"] == 3
    assert body["categories"]["add_to_resume"] == ["docker"]
    assert body["categories"]["learn_next"] == ["kubernetes"]
    assert {item["skill"]: item["count"] for item in body["gaps"]} == {
        "docker": 2, "kubernetes": 2,
    }

    suggestions = client.get(f"/resumes/{resume_id}/suggestions", params={"limit": 3})
    assert suggestions.status_code == 200
    suggestion_body = suggestions.json()
    assert [item["category"] for item in suggestion_body["suggestions"]] == [
        "add_to_resume", "learn_next"
    ]
    assert "appears in the resume text" in suggestion_body["suggestions"][0]["suggestion"]
    assert "experience" not in suggestion_body["suggestions"][1]["suggestion"].lower()

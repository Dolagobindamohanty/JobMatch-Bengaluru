import pytest

from api.app.storage import LocalResumeStorage, StorageError, get_resume_storage


def test_storage_defaults_to_local_files(tmp_path, monkeypatch):
    for name in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    storage = get_resume_storage(tmp_path)
    assert isinstance(storage, LocalResumeStorage)
    storage.put("resumes/id/resume.txt", b"private")
    assert (tmp_path / "resumes" / "id" / "resume.txt").read_bytes() == b"private"


def test_partial_s3_configuration_fails_without_leaking_values(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://object.example")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "access-secret")
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)

    with pytest.raises(StorageError, match="Incomplete S3 storage configuration") as error:
        get_resume_storage(__import__("pathlib").Path("uploads"))
    assert "access-secret" not in str(error.value)

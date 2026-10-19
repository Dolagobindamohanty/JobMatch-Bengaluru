"""Job discovery and account API with SQLite local and PostgreSQL production stores."""
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from jobmatch_bengaluru.resume_parser import extract_text, parse_profile
from jobmatch_bengaluru.matching import score_match
from jobmatch_bengaluru.classifiers import extract_skills
from jobmatch_bengaluru.postgres import PostgresConnection, initialize_postgres
from api.app.storage import StorageError, get_resume_storage

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("JOBMATCH_DB_PATH", ROOT / "jobs.db"))
DATABASE_URL = os.getenv("DATABASE_URL")
RESUME_DIR = Path(os.getenv("JOBMATCH_RESUME_DIR", ROOT / "resume_uploads"))
LOCAL_USER_ID = "local-user"
REFRESH_INTERVAL_SECONDS = int(os.getenv("REFRESH_INTERVAL_SECONDS", 24 * 60 * 60))
REFRESH_ON_STARTUP = os.getenv("REFRESH_ON_STARTUP", "false").lower() in {"1", "true", "yes"}
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN") or None
RESUME_FEATURE_FLAG = "JOBMATCH_RESUME_ENABLED"
FEATURE_DISABLED_DETAIL = "Resume and account functionality is temporarily disabled"
_refresh_lock = threading.Lock()
_refresh_process = None


def _cors_origins():
    values = [value.strip().rstrip("/") for value in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")]
    return [value for value in values if value]

app = FastAPI(title="JobMatch Bengaluru API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _last_pipeline_refresh():
    with connect() as connection:
        try:
            row = connection.execute(
                "SELECT MAX(finished_at) FROM pipeline_runs WHERE error IS NULL"
            ).fetchone()
        except Exception:
            row = (None,)
    return row[0] if row else None


def refresh_if_stale():
    """Start one background refresh when the API is opened after 24 hours."""
    global _refresh_process
    with _refresh_lock:
        if _refresh_process is not None and _refresh_process.poll() is None:
            return {"status": "running"}
        last = _last_pipeline_refresh()
        stale = True
        if last:
            try:
                refreshed = datetime.fromisoformat(last.replace("Z", "+00:00"))
                stale = (datetime.now(timezone.utc) - refreshed).total_seconds() >= REFRESH_INTERVAL_SECONDS
            except ValueError:
                stale = True
        if not stale:
            return {"status": "fresh", "last_refresh": last}
        script = ROOT / "blr_jobs_pipeline.py"
        _refresh_process = subprocess.Popen(
            [sys.executable, str(script)], cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        return {"status": "started", "last_refresh": last}


@app.on_event("startup")
def refresh_on_open():
    # Render web services should be available immediately after deploy.  A
    # refresh can outlive the request and compete with a second instance, so
    # scheduled refreshes are opt-in (use a Render cron job or POST /refresh).
    if REFRESH_ON_STARTUP:
        refresh_if_stale()


@app.get("/")
def root():
    """Small human-friendly landing response for the API server root."""
    return {
        "name": "JobMatch Bengaluru API",
        "version": app.version,
        "status": "ok",
        "docs": "/docs",
        "endpoints": ["/health", "/jobs", "/jobs/ai", "/skills/trending", "/refresh"],
    }


def connect():
    if DATABASE_URL:
        return PostgresConnection(initialize_postgres(DATABASE_URL))
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    init_account_tables(connection)
    return connection


class AccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class SavedJobInput(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=200)
    job_id: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class SavedSearchInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(default="", max_length=500)
    filters: dict[str, Any] = Field(default_factory=dict)


class ApplicationInput(BaseModel):
    source: str | None = Field(default=None, max_length=100)
    company: str = Field(min_length=1, max_length=200)
    job_id: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=300)
    status: str = Field(default="applied", max_length=50)
    applied_at: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=4000)


class ResumeVersionInput(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    resume_id: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


def current_user_id(request: Request) -> str:
    """Resolve a local development identity without coupling to an auth vendor."""
    value = request.headers.get("X-Local-User-ID") or request.headers.get("X-User-ID")
    value = (value or LOCAL_USER_ID).strip()
    if not value or len(value) > 128:
        raise HTTPException(status_code=400, detail="Invalid local user identity")
    return value


def resume_features_enabled() -> bool:
    """Return the resume/account feature state with a production-safe default.

    The environment is read per request so deployments and tests can change the
    flag without importing a second FastAPI application. An explicit flag wins;
    otherwise production disables these features and every other environment
    keeps the local-development behavior enabled.
    """
    override = os.getenv(RESUME_FEATURE_FLAG)
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("APP_ENV", "local").strip().lower() != "production"


def require_resume_features() -> None:
    if not resume_features_enabled():
        raise HTTPException(status_code=503, detail=FEATURE_DISABLED_DETAIL)


def init_account_tables(connection):
    """Idempotent SQLite migrations for Phase 6 account-owned data."""
    connection.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, display_name TEXT, email TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS saved_jobs (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, source TEXT NOT NULL,
        company TEXT NOT NULL, job_id TEXT NOT NULL, notes TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(user_id, source, company, job_id))""")
    connection.execute("""CREATE TABLE IF NOT EXISTS saved_searches (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
        query TEXT NOT NULL DEFAULT '', filters_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS applications (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, source TEXT, company TEXT NOT NULL,
        job_id TEXT, job_title TEXT, status TEXT NOT NULL, applied_at TEXT,
        notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS resume_versions (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, resume_id TEXT,
        label TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    for table in ("saved_jobs", "saved_searches", "applications", "resume_versions"):
        connection.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)")
    connection.commit()


def ensure_user(connection, user_id: str):
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        "INSERT INTO users(id, created_at, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(id) DO NOTHING", (user_id, now, now))


def account_row(row):
    return row_to_dict(row) if row else None


def row_to_dict(row):
    """Convert both sqlite3.Row and SQLAlchemy 2 Row objects to a dict."""
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


def parse_skills(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def serialize(row):
    item = row_to_dict(row)
    item["skills"] = parse_skills(item.get("skills"))
    item["is_ai"] = bool(item.get("is_ai"))
    item["active"] = bool(item.get("active"))
    return item


def table_exists(connection):
    if isinstance(connection, PostgresConnection):
        return connection.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?",
            ("jobs",),
        ).fetchone() is not None
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone() is not None


def init_resume_table(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS resumes (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
        file_path TEXT NOT NULL, raw_text TEXT NOT NULL, parsed_json TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    connection.commit()


def _resume_storage():
    """Resolve storage per operation so tests and deployments can configure it safely."""
    return get_resume_storage(RESUME_DIR)


@app.on_event("startup")
def validate_resume_storage():
    # Validate configuration at startup, while keeping boto3 import lazy for
    # local development and test environments.
    if resume_features_enabled():
        _resume_storage()


def init_match_table(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS matches (
        resume_id TEXT NOT NULL, source TEXT NOT NULL, company TEXT NOT NULL,
        job_id TEXT NOT NULL, score REAL NOT NULL, breakdown_json TEXT NOT NULL,
        created_at TEXT NOT NULL, PRIMARY KEY(resume_id, source, company, job_id))""")
    connection.commit()


def _resume_gap_data(resume_id: str, limit: int):
    """Build deterministic skill gaps from the cached match explanations."""
    with connect() as connection:
        init_resume_table(connection)
        init_match_table(connection)
        resume = connection.execute(
            "SELECT raw_text, parsed_json FROM resumes WHERE id=? AND user_id=?",
            (resume_id, LOCAL_USER_ID),
        ).fetchone()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

        profile = json.loads(resume[1])
        parsed_skills = {str(skill).strip().lower() for skill in profile.get("skills", [])}
        raw_skills = set(extract_skills(resume[0]))
        rows = connection.execute(
            """SELECT source, company, job_id, score, breakdown_json
               FROM matches WHERE resume_id=?
               ORDER BY score DESC, company ASC, job_id ASC LIMIT ?""",
            (resume_id, limit),
        ).fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        try:
            breakdown = json.loads(row[4])
        except (TypeError, json.JSONDecodeError):
            breakdown = {}
        # Re-check against the current parsed profile: skills edited after a
        # match was cached must not continue to appear as gaps.
        for skill in breakdown.get("missing_skills", []):
            canonical = str(skill).strip().lower()
            if canonical and canonical not in parsed_skills:
                counts[canonical] = counts.get(canonical, 0) + 1

    gaps = []
    for skill, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        category = "add_to_resume" if skill in raw_skills else "learn_next"
        gaps.append({"skill": skill, "count": count, "category": category})
    categories = {
        "add_to_resume": [item["skill"] for item in gaps if item["category"] == "add_to_resume"],
        "learn_next": [item["skill"] for item in gaps if item["category"] == "learn_next"],
    }
    return {
        "resume_id": resume_id,
        "top_matches": len(rows),
        "gaps": gaps,
        "categories": categories,
    }


def serialize_resume(row):
    item = row_to_dict(row)
    item["parsed_profile"] = json.loads(item.pop("parsed_json"))
    item.pop("file_path", None)
    item.pop("raw_text", None)
    return item


@app.get("/health")
def health():
    try:
        with connect() as connection:
            jobs_table = table_exists(connection)
    except Exception as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {
        "status": "ok",
        "database_backend": "postgresql" if DATABASE_URL else "sqlite",
        "database": "configured" if DATABASE_URL else str(DB_PATH),
        "database_url_configured": bool(os.getenv("DATABASE_URL")),
        "jobs_table": jobs_table,
    }


@app.post("/refresh")
def refresh(request: Request):
    """Manually request a pipeline refresh; the job fetch runs in the background."""
    if REFRESH_TOKEN is not None and not hmac.compare_digest(
        request.headers.get("X-Refresh-Token", ""), REFRESH_TOKEN
    ):
        raise HTTPException(status_code=401, detail="invalid refresh token")
    return refresh_if_stale()


@app.get("/jobs")
def list_jobs(
    q: str = Query("", description="Search title, company, location, description, or skills"),
    ai_only: bool = False,
    company: str | None = None,
    role_category: str | None = None,
    experience_level: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: str = Query("newest", pattern="^(newest|company|title)$"),
):
    with connect() as connection:
        if not table_exists(connection):
            return {"jobs": [], "page": page, "page_size": page_size, "total": 0}
        clauses = ["active=1"]
        values: list[Any] = []
        if ai_only:
            clauses.append("is_ai=1")
        if company:
            clauses.append("LOWER(company) = LOWER(?)")
            values.append(company)
        if role_category:
            clauses.append("role_category = ?")
            values.append(role_category)
        if experience_level:
            clauses.append("experience_level = ?")
            values.append(experience_level)
        if q:
            clauses.append("LOWER(title || ' ' || company || ' ' || location || ' ' || description || ' ' || COALESCE(skills, '')) LIKE LOWER(?)")
            values.append(f"%{q}%")
        where = " AND ".join(clauses)
        order = {"newest": "posted DESC, last_seen DESC", "company": "company, title", "title": "title"}[sort]
        total = connection.execute(f"SELECT COUNT(*) FROM jobs WHERE {where}", values).fetchone()[0]
        offset = (page - 1) * page_size
        rows = connection.execute(
            f"SELECT source, company, job_id, title, location, url AS apply_url, posted AS posted_at, description, active, is_ai, role_category, experience_level, skills FROM jobs WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*values, page_size, offset],
        ).fetchall()
        return {"jobs": [serialize(row) for row in rows], "page": page,
                "page_size": page_size, "total": total,
                "total_pages": (total + page_size - 1) // page_size}


@app.get("/jobs/ai")
def ai_jobs(
    q: str = "", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
):
    return list_jobs(q=q, ai_only=True, page=page, page_size=page_size)


@app.get("/jobs/{source}/{company}/{job_id}")
def get_job(source: str, company: str, job_id: str):
    with connect() as connection:
        row = connection.execute(
            "SELECT source, company, job_id, title, location, url AS apply_url, posted AS posted_at, description, active, is_ai, role_category, experience_level, skills FROM jobs WHERE source=? AND company=? AND job_id=? AND active=1",
            (source, company, job_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize(row)


@app.get("/skills/trending")
def trending_skills(ai_only: bool = False, limit: int = Query(20, ge=1, le=100)):
    with connect() as connection:
        clauses = ["active=1"]
        if ai_only:
            clauses.append("is_ai=1")
        rows = connection.execute(
            f"SELECT skills FROM jobs WHERE {' AND '.join(clauses)}", ()
        ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        for skill in set(parse_skills(row[0])):
            counts[skill] = counts.get(skill, 0) + 1
    return {"skills": [{"name": name, "job_count": count}
                       for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]}


@app.post("/resumes", status_code=201)
async def upload_resume(file: UploadFile = File(...)):
    require_resume_features()
    filename = file.filename or "resume"
    content = await file.read()
    resume_id = str(uuid.uuid4())
    try:
        text = extract_text(filename, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    profile = parse_profile(text)
    storage_key = f"resumes/{resume_id}/{Path(filename).name}"
    storage = _resume_storage()
    try:
        storage.put(storage_key, content, file.content_type)
    except StorageError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    now = datetime.now(timezone.utc).isoformat()
    try:
        with connect() as connection:
            init_resume_table(connection)
            connection.execute("INSERT INTO resumes VALUES (?,?,?,?,?,?,?,?)",
                               (resume_id, LOCAL_USER_ID, filename, storage_key, text,
                                json.dumps(profile), now, now))
    except Exception:
        # Do not leave an unreferenced private object if metadata persistence fails.
        try:
            storage.delete(storage_key)
        except StorageError:
            pass
        raise
    return {"id": resume_id, "filename": filename, "parsed_profile": profile, "created_at": now}


@app.get("/resumes/{resume_id}")
def get_resume(resume_id: str):
    require_resume_features()
    with connect() as connection:
        init_resume_table(connection)
        row = connection.execute("SELECT id,user_id,filename,file_path,raw_text,parsed_json,created_at,updated_at FROM resumes WHERE id=? AND user_id=?",
                                 (resume_id, LOCAL_USER_ID)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Resume not found")
    return serialize_resume(row)


@app.patch("/resumes/{resume_id}/skills")
def update_resume_skills(resume_id: str, skills: list[str]):
    require_resume_features()
    with connect() as connection:
        init_resume_table(connection)
        row = connection.execute("SELECT parsed_json FROM resumes WHERE id=? AND user_id=?",
                                 (resume_id, LOCAL_USER_ID)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Resume not found")
        profile = json.loads(row[0])
        profile["skills"] = sorted({skill.strip().lower() for skill in skills if skill.strip()})
        now = datetime.now(timezone.utc).isoformat()
        connection.execute("UPDATE resumes SET parsed_json=?,updated_at=? WHERE id=?",
                           (json.dumps(profile), now, resume_id))
    return {"id": resume_id, "parsed_profile": profile, "updated_at": now}


@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id: str):
    require_resume_features()
    with connect() as connection:
        init_resume_table(connection)
        row = connection.execute("SELECT file_path FROM resumes WHERE id=? AND user_id=?",
                                 (resume_id, LOCAL_USER_ID)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Resume not found")
    try:
        _resume_storage().delete(row[0])
    except StorageError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    with connect() as connection:
        connection.execute("DELETE FROM resumes WHERE id=?", (resume_id,))
    return {"deleted": True, "id": resume_id}


@app.get("/resumes/{resume_id}/matches")
def resume_matches(resume_id: str, limit: int = Query(20, ge=1, le=100)):
    require_resume_features()
    with connect() as connection:
        init_resume_table(connection)
        init_match_table(connection)
        resume = connection.execute("SELECT raw_text, parsed_json FROM resumes WHERE id=? AND user_id=?",
                                    (resume_id, LOCAL_USER_ID)).fetchone()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        profile = json.loads(resume[1])
        profile["role_categories"] = ["ai_ml"] if any("machine" in title.lower() or "ml" in title.lower() for title in profile.get("job_titles", [])) else []
        jobs = connection.execute("SELECT source,company,job_id,title,location,url,posted,description,is_ai,role_category,experience_level,skills FROM jobs WHERE active=1").fetchall()
        now = datetime.now(timezone.utc).isoformat()
        results = []
        for row in jobs:
            job = row_to_dict(row)
            job["skills"] = parse_skills(job.get("skills"))
            breakdown = score_match(profile, resume[0], job)
            connection.execute("""INSERT INTO matches VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(resume_id,source,company,job_id) DO UPDATE SET
                score=excluded.score, breakdown_json=excluded.breakdown_json, created_at=excluded.created_at""",
                (resume_id, job["source"], job["company"], job["job_id"], breakdown["score"], json.dumps(breakdown), now))
            results.append({**job, "match": breakdown})
        connection.commit()
    results.sort(key=lambda item: item["match"]["score"], reverse=True)
    return {"resume_id": resume_id, "matches": results[:limit], "total": len(results)}


@app.get("/resumes/{resume_id}/gaps")
def resume_gaps(
    resume_id: str,
    limit: int = Query(5, ge=1, le=100, description="Number of cached top matches to aggregate"),
):
    """Return counted missing skills from the cached top match explanations."""
    require_resume_features()
    return _resume_gap_data(resume_id, limit)


@app.get("/resumes/{resume_id}/suggestions")
def resume_suggestions(
    resume_id: str,
    limit: int = Query(5, ge=1, le=100, description="Number of cached top matches to aggregate"),
):
    """Return local, text-grounded suggestions without claiming new experience."""
    require_resume_features()
    data = _resume_gap_data(resume_id, limit)
    suggestions = []
    for gap in data["gaps"]:
        skill = gap["skill"]
        if gap["category"] == "add_to_resume":
            text = (
                f'Consider adding "{skill}" to the parsed skills section; '
                "it already appears in the resume text."
            )
        else:
            text = (
                f'Learn or practice "{skill}" next; it is missing from the parsed '
                f"skills and occurs in {gap['count']} top-match job(s)."
            )
        suggestions.append({
            "skill": skill,
            "category": gap["category"],
            "count": gap["count"],
            "suggestion": text,
        })
    return {"resume_id": resume_id, "suggestions": suggestions}


@app.get("/resumes/{resume_id}/roles")
def resume_roles(resume_id: str):
    require_resume_features()
    data = resume_matches(resume_id, limit=100)
    groups = {}
    for item in data["matches"]:
        role = item.get("role_category") or "other"
        groups.setdefault(role, []).append(item["match"]["score"])
    return {"resume_id": resume_id, "roles": [
        {"role_category": role, "match_score": round(sum(scores) / len(scores), 2), "job_count": len(scores)}
        for role, scores in sorted(groups.items(), key=lambda item: -sum(item[1]) / len(item[1]))
    ]}


# Phase 6 account and tracker endpoints. Identity is deliberately a local
# opaque id; a future auth layer can supply the same request identity without
# changing the persistence model or exposing provider tokens to this API.
@app.get("/account")
def get_account(request: Request):
    require_resume_features()
    user_id = current_user_id(request)
    with connect() as connection:
        ensure_user(connection, user_id)
        row = connection.execute(
            "SELECT id, display_name, email, created_at, updated_at FROM users WHERE id=?", (user_id,)
        ).fetchone()
    return account_row(row)


@app.patch("/account")
def update_account(payload: AccountUpdate, request: Request):
    require_resume_features()
    user_id = current_user_id(request)
    now = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        ensure_user(connection, user_id)
        connection.execute(
            "UPDATE users SET display_name=COALESCE(?, display_name), email=COALESCE(?, email), updated_at=? WHERE id=?",
            (payload.display_name, payload.email, now, user_id),
        )
        row = connection.execute(
            "SELECT id, display_name, email, created_at, updated_at FROM users WHERE id=?", (user_id,)
        ).fetchone()
    return account_row(row)


@app.delete("/account/data")
def delete_account_data(request: Request):
    """Delete all account-owned records and uploaded resume files."""
    require_resume_features()
    user_id = current_user_id(request)
    files = []
    with connect() as connection:
        # Read paths before removing rows; paths never leave the API response.
        if _table_exists(connection, "resumes"):
            files = [row[0] for row in connection.execute(
                "SELECT file_path FROM resumes WHERE user_id=?", (user_id,)
            ).fetchall()]
    try:
        storage = _resume_storage()
        for file_path in files:
            storage.delete(file_path)
    except StorageError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    with connect() as connection:
        if _table_exists(connection, "resumes"):
            connection.execute("DELETE FROM matches WHERE resume_id IN (SELECT id FROM resumes WHERE user_id=?)", (user_id,)) if _table_exists(connection, "matches") else None
            connection.execute("DELETE FROM resumes WHERE user_id=?", (user_id,))
        for table in ("saved_jobs", "saved_searches", "applications", "resume_versions"):
            connection.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        connection.execute("DELETE FROM users WHERE id=?", (user_id,))
    return {"deleted": True}


@app.delete("/account")
def delete_account(request: Request):
    """Convenience alias for a complete local account/data deletion."""
    require_resume_features()
    return delete_account_data(request)


def _table_exists(connection, name: str) -> bool:
    if isinstance(connection, PostgresConnection):
        return connection.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?",
            (name,),
        ).fetchone() is not None
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _saved_job(row):
    item = row_to_dict(row)
    return item


@app.post("/saved-jobs", status_code=201)
def save_job(payload: SavedJobInput, request: Request):
    require_resume_features()
    user_id = current_user_id(request)
    now = datetime.now(timezone.utc).isoformat()
    item_id = str(uuid.uuid4())
    with connect() as connection:
        ensure_user(connection, user_id)
        connection.execute("""INSERT INTO saved_jobs
            (id,user_id,source,company,job_id,notes,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id,source,company,job_id)
            DO UPDATE SET notes=excluded.notes, updated_at=excluded.updated_at""",
            (item_id, user_id, payload.source, payload.company, payload.job_id, payload.notes, now, now))
        row = connection.execute(
            "SELECT id,source,company,job_id,notes,created_at,updated_at FROM saved_jobs WHERE user_id=? AND source=? AND company=? AND job_id=?",
            (user_id, payload.source, payload.company, payload.job_id)).fetchone()
    return _saved_job(row)


@app.get("/saved-jobs")
def list_saved_jobs(request: Request):
    require_resume_features()
    user_id = current_user_id(request)
    with connect() as connection:
        rows = connection.execute(
            "SELECT id,source,company,job_id,notes,created_at,updated_at FROM saved_jobs WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return {"saved_jobs": [_saved_job(row) for row in rows]}


@app.delete("/saved-jobs/{saved_job_id}")
def delete_saved_job(saved_job_id: str, request: Request):
    require_resume_features()
    with connect() as connection:
        result = connection.execute("DELETE FROM saved_jobs WHERE id=? AND user_id=?", (saved_job_id, current_user_id(request)))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Saved job not found")
    return {"deleted": True, "id": saved_job_id}


@app.post("/saved-searches", status_code=201)
def create_saved_search(payload: SavedSearchInput, request: Request):
    require_resume_features()
    user_id, now, item_id = current_user_id(request), datetime.now(timezone.utc).isoformat(), str(uuid.uuid4())
    with connect() as connection:
        ensure_user(connection, user_id)
        connection.execute("INSERT INTO saved_searches VALUES (?,?,?,?,?,?,?)",
                           (item_id, user_id, payload.name, payload.query, json.dumps(payload.filters), now, now))
    return {"id": item_id, "name": payload.name, "query": payload.query, "filters": payload.filters, "created_at": now, "updated_at": now}


@app.get("/saved-searches")
def list_saved_searches(request: Request):
    require_resume_features()
    with connect() as connection:
        rows = connection.execute("SELECT id,name,query,filters_json,created_at,updated_at FROM saved_searches WHERE user_id=? ORDER BY created_at DESC", (current_user_id(request),)).fetchall()
        return {"saved_searches": [{**row_to_dict(row), "filters": json.loads(row["filters_json"])} for row in rows]}


@app.delete("/saved-searches/{search_id}")
def delete_saved_search(search_id: str, request: Request):
    require_resume_features()
    with connect() as connection:
        result = connection.execute("DELETE FROM saved_searches WHERE id=? AND user_id=?", (search_id, current_user_id(request)))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Saved search not found")
    return {"deleted": True, "id": search_id}


@app.post("/applications", status_code=201)
def create_application(payload: ApplicationInput, request: Request):
    require_resume_features()
    user_id, now, item_id = current_user_id(request), datetime.now(timezone.utc).isoformat(), str(uuid.uuid4())
    applied_at = payload.applied_at or now
    with connect() as connection:
        ensure_user(connection, user_id)
        connection.execute("INSERT INTO applications VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, user_id, payload.source, payload.company, payload.job_id, payload.job_title, payload.status, applied_at, payload.notes, now, now))
    return {"id": item_id, **payload.model_dump(exclude_none=False), "applied_at": applied_at, "created_at": now, "updated_at": now}


@app.get("/applications")
def list_applications(request: Request):
    require_resume_features()
    with connect() as connection:
        rows = connection.execute("SELECT id,source,company,job_id,job_title,status,applied_at,notes,created_at,updated_at FROM applications WHERE user_id=? ORDER BY applied_at DESC, created_at DESC", (current_user_id(request),)).fetchall()
    return {"applications": [row_to_dict(row) for row in rows]}


@app.patch("/applications/{application_id}")
def update_application(application_id: str, payload: ApplicationInput, request: Request):
    require_resume_features()
    user_id, now = current_user_id(request), datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        result = connection.execute("""UPDATE applications SET source=?,company=?,job_id=?,job_title=?,status=?,applied_at=?,notes=?,updated_at=? WHERE id=? AND user_id=?""",
            (payload.source, payload.company, payload.job_id, payload.job_title, payload.status, payload.applied_at, payload.notes, now, application_id, user_id))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Application not found")
        row = connection.execute("SELECT id,source,company,job_id,job_title,status,applied_at,notes,created_at,updated_at FROM applications WHERE id=?", (application_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/applications/{application_id}")
def delete_application(application_id: str, request: Request):
    require_resume_features()
    with connect() as connection:
        result = connection.execute("DELETE FROM applications WHERE id=? AND user_id=?", (application_id, current_user_id(request)))
        if not result.rowcount:
            raise HTTPException(status_code=404, detail="Application not found")
    return {"deleted": True, "id": application_id}


@app.post("/resume-versions", status_code=201)
def create_resume_version(payload: ResumeVersionInput, request: Request):
    require_resume_features()
    user_id, now, item_id = current_user_id(request), datetime.now(timezone.utc).isoformat(), str(uuid.uuid4())
    with connect() as connection:
        ensure_user(connection, user_id)
        if payload.resume_id and _table_exists(connection, "resumes") and not connection.execute("SELECT 1 FROM resumes WHERE id=? AND user_id=?", (payload.resume_id, user_id)).fetchone():
            raise HTTPException(status_code=404, detail="Resume not found")
        connection.execute("INSERT INTO resume_versions VALUES (?,?,?,?,?,?,?)", (item_id, user_id, payload.resume_id, payload.label, payload.notes, now, now))
    return {"id": item_id, "resume_id": payload.resume_id, "label": payload.label, "notes": payload.notes, "created_at": now, "updated_at": now}


@app.get("/resume-versions")
def list_resume_versions(request: Request):
    require_resume_features()
    with connect() as connection:
        rows = connection.execute("SELECT id,resume_id,label,notes,created_at,updated_at FROM resume_versions WHERE user_id=? ORDER BY created_at DESC", (current_user_id(request),)).fetchall()
    return {"resume_versions": [row_to_dict(row) for row in rows]}


@app.post("/resumes/{resume_id}/versions", status_code=201)
def create_linked_resume_version(resume_id: str, payload: ResumeVersionInput, request: Request):
    require_resume_features()
    payload.resume_id = resume_id
    return create_resume_version(payload, request)


@app.get("/resumes/{resume_id}/versions")
def list_linked_resume_versions(resume_id: str, request: Request):
    require_resume_features()
    with connect() as connection:
        rows = connection.execute(
            "SELECT id,resume_id,label,notes,created_at,updated_at FROM resume_versions WHERE user_id=? AND resume_id=? ORDER BY created_at DESC",
            (current_user_id(request), resume_id),
        ).fetchall()
    return {"resume_versions": [row_to_dict(row) for row in rows]}

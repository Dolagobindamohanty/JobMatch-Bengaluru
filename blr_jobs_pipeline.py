"""Collect Bengaluru jobs from public Greenhouse, Lever, and Ashby feeds."""
import argparse
import hashlib
import html
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from jobmatch_bengaluru.classifiers import (
    classify_experience, classify_role_category, extract_skills,
)
from jobmatch_bengaluru.postgres import PostgresConnection, initialize_postgres

DB_PATH = os.getenv("JOBMATCH_DB_PATH", str(Path(__file__).resolve().parent / "jobs.db"))
DATABASE_URL = os.getenv("DATABASE_URL")
BLR_PATTERN = re.compile(r"bengaluru|bangalore|\bblr\b", re.I)
AI_TITLE_PATTERN = re.compile(
    r"\b(ai|artificial intelligence|machine learning|ml|deep learning|generative ai|"
    r"genai|llms?|large language model|nlp|natural language|computer vision|robotics|"
    r"recommendation|mlops|prompt engineer|data scientist)\b", re.I)
AI_DESCRIPTION_PATTERN = re.compile(
    r"\b(machine learning|deep learning|generative ai|genai|large language model|"
    r"llm|natural language processing|computer vision|model training|model serving|"
    r"neural network|retrieval augmented generation|\brag\b|mlops)\b", re.I)
IT_TITLE_PATTERN = re.compile(
    r"software|developer|engineering|devops|site reliability|\bsre\b|data|"
    r"cloud|security|cyber|qa|quality assurance|test|infrastructure|network|"
    r"technical|technology|\bit\b|systems?|machine learning|\bai\b|backend|"
    r"frontend|full[- ]stack|mobile|database|platform|architect|programmer",
    re.I,
)
HEADERS = {"User-Agent": "blr-jobs-matcher/0.1 (personal project)"}
TIMEOUT = 20


def is_blr(*locations):
    return any(value and BLR_PATTERN.search(str(value)) for value in locations)


def is_it(title):
    """Keep technology, engineering, data, infrastructure, and support roles."""
    return bool(IT_TITLE_PATTERN.search(title or ""))


def is_ai(title, description=""):
    """Recognize explicit AI/ML roles and technical roles with AI responsibilities."""
    return bool(AI_TITLE_PATTERN.search(title or "") or (
        IT_TITLE_PATTERN.search(title or "") and
        AI_DESCRIPTION_PATTERN.search(description or "")
    ))


def is_qualifying(title, description=""):
    return is_it(title) or is_ai(title, description)


def strip_html(text):
    text = html.unescape(text or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def content_hash(job):
    payload = "\x1f".join(str(job.get(key, "")) for key in
                            ("title", "location", "description", "url"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_json(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_workday_jobs(tenant, site):
    url = f"https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    jobs = []
    offset = 0
    while True:
        response = requests.post(
            url, json={"appliedFacets": {}, "limit": 20, "offset": offset,
                       "searchText": ""}, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        batch = data.get("jobPostings", [])
        jobs.extend(batch)
        offset += len(batch)
        if not batch or offset >= data.get("total", offset):
            return jobs


def fetch_greenhouse(token):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    jobs = []
    for job in data.get("jobs", []):
        location = (job.get("location") or {}).get("name", "")
        description = strip_html(job.get("content", ""))
        if is_blr(location) and is_qualifying(job.get("title", ""), description):
            jobs.append({
                "job_id": str(job["id"]), "title": job.get("title", ""),
                "location": location, "url": job.get("absolute_url", ""),
                "posted": job.get("updated_at", ""),
                "description": description,
                "is_ai": int(is_ai(job.get("title", ""), description)),
                "role_category": classify_role_category(job.get("title", ""), description),
                "experience_level": classify_experience(job.get("title", ""), description),
                "skills": extract_skills(f"{job.get('title', '')} {description}"),
            })
    return jobs


def fetch_lever(slug):
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    jobs = []
    for job in data:
        categories = job.get("categories") or {}
        location = categories.get("location", "")
        all_locations = categories.get("allLocations") or []
        description = job.get("descriptionPlain", "")
        if not (is_blr(location, *all_locations) and
                is_qualifying(job.get("text", ""), description)):
            continue
        created = job.get("createdAt")
        posted = (datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
                  if created else "")
        jobs.append({
            "job_id": str(job["id"]), "title": job.get("text", ""),
            "location": location, "url": job.get("hostedUrl", ""),
            "posted": posted, "description": description,
            "is_ai": int(is_ai(job.get("text", ""), description)),
            "role_category": classify_role_category(job.get("text", ""), description),
            "experience_level": classify_experience(job.get("text", ""), description),
            "skills": extract_skills(f"{job.get('text', '')} {description}"),
        })
    return jobs


def fetch_ashby(name):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{name}")
    jobs = []
    for job in data.get("jobs", []):
        location = job.get("location", "")
        secondary = [item.get("location", "") if isinstance(item, dict) else str(item)
                     for item in job.get("secondaryLocations", [])]
        description = job.get("descriptionPlain", "")
        if is_blr(location, *secondary) and is_qualifying(job.get("title", ""), description):
            jobs.append({
                "job_id": str(job["id"]), "title": job.get("title", ""),
                "location": location, "url": job.get("jobUrl", ""),
                "posted": job.get("publishedAt", ""),
                "description": description,
                "is_ai": int(is_ai(job.get("title", ""), description)),
                "role_category": classify_role_category(job.get("title", ""), description),
                "experience_level": classify_experience(job.get("title", ""), description),
                "skills": extract_skills(f"{job.get('title', '')} {description}"),
            })
    return jobs


def fetch_workday(spec):
    """Fetch a public Workday CXS board using {tenant, site} configuration."""
    tenant = spec["tenant"]
    site = spec["site"]
    jobs = []
    for job in get_workday_jobs(tenant, site):
        location = job.get("locationsText", "")
        title = job.get("title", "")
        if not (is_blr(location) and is_qualifying(title)):
            continue
        external_path = job.get("externalPath", "")
        jobs.append({
            "job_id": str((job.get("bulletFields") or [external_path])[0]),
            "title": title, "location": location,
            "url": f"https://{tenant}.wd3.myworkdayjobs.com{external_path}",
            "posted": job.get("postedOn", ""), "description": "",
            "is_ai": int(is_ai(title)),
            "role_category": classify_role_category(title),
            "experience_level": classify_experience(title),
            "skills": extract_skills(title),
        })
    return jobs


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever,
            "ashby": fetch_ashby, "workday": fetch_workday}


def init_db(conn):
    if isinstance(conn, PostgresConnection):
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        source TEXT, company TEXT, job_id TEXT, title TEXT, location TEXT,
        url TEXT, posted TEXT, description TEXT, first_seen TEXT,
        last_seen TEXT, active INTEGER DEFAULT 1, is_ai INTEGER DEFAULT 0,
        role_category TEXT, experience_level TEXT, skills TEXT, content_hash TEXT,
        PRIMARY KEY (source, company, job_id))""")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "is_ai" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN is_ai INTEGER DEFAULT 0")
    for column in ("role_category", "experience_level", "skills", "content_hash"):
        if column not in columns:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS pipeline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, company TEXT,
        started_at TEXT, finished_at TEXT, jobs_found INTEGER DEFAULT 0,
        jobs_inserted INTEGER DEFAULT 0, jobs_deactivated INTEGER DEFAULT 0,
        error TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS companies (
        source TEXT, company TEXT, board_config TEXT, careers_url TEXT,
        active INTEGER DEFAULT 1, last_fetched_at TEXT,
        PRIMARY KEY (source, company))""")
    conn.commit()


def connect_db():
    """Open the configured production database, or the local SQLite store."""
    if DATABASE_URL:
        return PostgresConnection(initialize_postgres(DATABASE_URL))
    return sqlite3.connect(DB_PATH)


def upsert(conn, source, company, jobs, now, *, commit=True):
    for job in jobs:
        conn.execute("""INSERT INTO jobs
            (source, company, job_id, title, location, url, posted, description,
             first_seen, last_seen, active, is_ai, role_category,
             experience_level, skills, content_hash)
             VALUES (?,?,?,?,?,?,?,?,?,?,TRUE,?,?,?,?,?)
            ON CONFLICT(source, company, job_id) DO UPDATE SET
              title=excluded.title, location=excluded.location, url=excluded.url,
              posted=excluded.posted, description=excluded.description,
              last_seen=excluded.last_seen, active=1, is_ai=excluded.is_ai,
              role_category=excluded.role_category,
              experience_level=excluded.experience_level, skills=excluded.skills,
              content_hash=excluded.content_hash""",
            (source, company, str(job["job_id"]), job["title"], job["location"],
             job["url"], job["posted"], job["description"], now, now,
             bool(job.get("is_ai", False)), job.get("role_category", "other"),
             job.get("experience_level", "mid"), json.dumps(job.get("skills", [])),
             content_hash(job)))
    # Run even when a source returns an empty list: an empty successful feed
    # means previously seen postings are no longer current, and must not stay
    # visible forever in the shared database.
    conn.execute("UPDATE jobs SET active=FALSE WHERE source=? AND company=? AND last_seen<?",
                 (source, company, now))
    if commit:
        conn.commit()


def failure_diagnostic(error, stage):
    """Do not expose driver messages, SQL parameters, URLs, or credentials."""
    diagnostic = f"{stage}: {type(error).__name__}"
    original = getattr(error, "orig", error)
    sqlstate = getattr(original, "sqlstate", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
        diagnostic += f" (SQLSTATE {sqlstate})"
    return diagnostic


def run(config_path):
    with open(config_path, encoding="utf-8") as file:
        config = json.load(file)
    conn = connect_db()
    init_db(conn)
    total = 0
    successful_boards = 0
    for source, companies in config.items():
        fetch = FETCHERS.get(source)
        if not fetch:
            print(f"skip unknown source: {source}")
            continue
        for company in companies:
            config_item = company
            company_name = (company.get("company", company.get("site", "workday"))
                            if isinstance(company, dict) else company)
            now = datetime.now(timezone.utc).isoformat()
            board_config = json.dumps(config_item, sort_keys=True)
            company_upsert = """INSERT INTO companies
                (source, company, board_config, last_fetched_at)
                VALUES (?,?,?,?)
                ON CONFLICT(source, company) DO UPDATE SET
                  board_config=excluded.board_config, last_fetched_at=excluded.last_fetched_at"""
            if isinstance(conn, PostgresConnection):
                # The production schema uses native JSONB and TIMESTAMPTZ;
                # explicit casts keep SQLAlchemy's text parameters portable
                # across psycopg versions and hosted PostgreSQL providers.
                company_upsert = """INSERT INTO companies
                    (source, company, board_config, last_fetched_at)
                    VALUES (?, ?, CAST(? AS JSONB), CAST(? AS TIMESTAMPTZ))
                    ON CONFLICT(source, company) DO UPDATE SET
                      board_config=excluded.board_config, last_fetched_at=excluded.last_fetched_at"""
            run_id = None
            stage = "start run"
            try:
                run_id = conn.execute(
                    "INSERT INTO pipeline_runs(source, company, started_at) VALUES (?,?,?) RETURNING id",
                    (source, company_name, now)).fetchone()[0]
                # Keep the run record durable even if a later write aborts.
                conn.commit()
                stage = "register company"
                conn.execute(company_upsert, (source, company_name, board_config, now))
                stage = "fetch"
                jobs = fetch(config_item)
                stage = "persist jobs"
                # Job changes, deactivation, and success receipt are atomic.
                upsert(conn, source, company_name, jobs, now, commit=False)
                conn.execute("UPDATE pipeline_runs SET finished_at=?, jobs_found=? WHERE id=?",
                             (datetime.now(timezone.utc).isoformat(), len(jobs), run_id))
                conn.commit()
            except Exception as error:
                diagnostic = failure_diagnostic(error, stage)
                print(f"[{source}] {company_name}: FAILED ({diagnostic})")
                try:
                    conn.rollback()
                    finished = datetime.now(timezone.utc).isoformat()
                    if run_id is None:
                        conn.execute("""INSERT INTO pipeline_runs
                            (source, company, started_at, finished_at, error)
                            VALUES (?,?,?,?,?)""",
                            (source, company_name, now, finished, diagnostic))
                    else:
                        conn.execute("UPDATE pipeline_runs SET finished_at=?, error=? WHERE id=?",
                                     (finished, diagnostic, run_id))
                    conn.commit()
                except Exception as record_error:
                    print(f"[{source}] {company_name}: FAILED "
                          f"({failure_diagnostic(record_error, 'record failure')})")
                    conn.rollback()
                continue
            successful_boards += 1
            total += len(jobs)
            print(f"[{source}] {company_name}: {len(jobs)} Bengaluru jobs")
            time.sleep(1)
    conn.close()
    print(f"Done. {total} Bengaluru jobs seen this run.")
    return 0 if successful_boards else 1


def stats():
    conn = connect_db()
    rows = conn.execute("""SELECT source, company, COUNT(*) FROM jobs
        WHERE active=1 GROUP BY source, company ORDER BY 3 DESC""").fetchall()
    for source, company, count in rows:
        print(f"{count:4d}  {source}/{company}")
    print("total active:", sum(row[2] for row in rows))
    ai_count = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE active=1 AND is_ai=1"
    ).fetchone()[0]
    print("active AI/ML jobs:", ai_count)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="companies.json")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    if args.stats:
        stats()
    else:
        raise SystemExit(run(args.config))

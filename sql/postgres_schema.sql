-- Production schema.  Column names intentionally match the SQLite store so
-- the API and cron collector can use one query surface in both environments.
CREATE TABLE IF NOT EXISTS companies (
  source TEXT NOT NULL,
  company TEXT NOT NULL,
  board_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  careers_url TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  last_fetched_at TIMESTAMPTZ,
  PRIMARY KEY (source, company)
);

CREATE TABLE IF NOT EXISTS jobs (
  source TEXT NOT NULL,
  company TEXT NOT NULL,
  job_id TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  posted TEXT,
  description TEXT NOT NULL DEFAULT '',
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  is_ai BOOLEAN NOT NULL DEFAULT FALSE,
  role_category TEXT,
  experience_level TEXT,
  skills TEXT,
  content_hash TEXT,
  PRIMARY KEY (source, company, job_id)
);
CREATE INDEX IF NOT EXISTS jobs_active_idx ON jobs(active);
CREATE INDEX IF NOT EXISTS jobs_ai_idx ON jobs(active, is_ai);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  company TEXT,
  started_at TEXT,
  finished_at TEXT,
  jobs_found INTEGER NOT NULL DEFAULT 0,
  jobs_inserted INTEGER NOT NULL DEFAULT 0,
  jobs_deactivated INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS resumes (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
  file_path TEXT NOT NULL, raw_text TEXT NOT NULL, parsed_json TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matches (
  resume_id TEXT NOT NULL, source TEXT NOT NULL, company TEXT NOT NULL,
  job_id TEXT NOT NULL, score DOUBLE PRECISION NOT NULL,
  breakdown_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (resume_id, source, company, job_id)
);

-- Phase 6 account-owned tables.
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, display_name TEXT, email TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_jobs (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, source TEXT NOT NULL,
  company TEXT NOT NULL, job_id TEXT NOT NULL, notes TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id, source, company, job_id)
);
CREATE TABLE IF NOT EXISTS saved_searches (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
  query TEXT NOT NULL DEFAULT '', filters_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, source TEXT, company TEXT NOT NULL,
  job_id TEXT, job_title TEXT, status TEXT NOT NULL, applied_at TEXT,
  notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resume_versions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, resume_id TEXT,
  label TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_jobs_user ON saved_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_searches_user ON saved_searches(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_resume_versions_user ON resume_versions(user_id);

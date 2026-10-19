CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS companies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('greenhouse','lever','ashby','workday')),
  board_config JSONB NOT NULL,
  careers_url TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  last_fetched_at TIMESTAMPTZ,
  UNIQUE (source, name)
);

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id UUID NOT NULL REFERENCES companies(id),
  source_job_id TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  apply_url TEXT NOT NULL,
  posted_at TIMESTAMPTZ,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  experience_level TEXT,
  role_category TEXT,
  is_ai BOOLEAN NOT NULL DEFAULT FALSE,
  ai_category TEXT,
  content_hash TEXT NOT NULL,
  embedding vector(384),
  UNIQUE (company_id, source_job_id)
);

CREATE INDEX IF NOT EXISTS jobs_active_location_idx ON jobs(active, location);
CREATE INDEX IF NOT EXISTS jobs_ai_idx ON jobs(active, is_ai);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  company_id UUID REFERENCES companies(id),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  jobs_found INTEGER NOT NULL DEFAULT 0,
  jobs_inserted INTEGER NOT NULL DEFAULT 0,
  jobs_deactivated INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT UNIQUE NOT NULL,
  aliases TEXT[] NOT NULL DEFAULT '{}',
  category TEXT,
  is_ai_skill BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS job_skills (
  job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
  skill_id UUID REFERENCES skills(id) ON DELETE CASCADE,
  importance TEXT NOT NULL DEFAULT 'required',
  PRIMARY KEY (job_id, skill_id)
);

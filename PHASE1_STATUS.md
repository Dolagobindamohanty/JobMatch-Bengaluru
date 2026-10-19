# Phase 1 Status

## Completed in this build

- Python package metadata in `pyproject.toml`.
- `jobmatch_bengaluru` package with deterministic role, experience, and skill classifiers.
- PostgreSQL schema in `sql/postgres_schema.sql` for companies, jobs, skills, job skills, and pipeline runs.
- Greenhouse, Lever, Ashby, and Workday adapters in `blr_jobs_pipeline.py`.
- Verified board configuration for Razorpay Greenhouse and BrowserStack Workday.
- Bengaluru/Bangalore/BLR filtering.
- AI/ML tagging with title and description rules.
- Role category classification.
- Experience-level classification.
- Canonical skill extraction with aliases.
- SQLite prototype migration for role, experience, skills, and AI fields.
- Upsert deduplication and inactive-job tracking.
- Pipeline run logging in the local prototype database.
- Fixture-based tests with no network access.

## Verification

```text
python -m pytest tests -q
8 passed, 1 xpassed

python -m py_compile blr_jobs_pipeline.py jobmatch_bengaluru/classifiers.py

python blr_jobs_pipeline.py
[greenhouse] razorpaysoftwareprivatelimited: 2 Bengaluru jobs
[workday] BrowserStack: 0 Bengaluru jobs
Done. 2 Bengaluru jobs seen this run.

python blr_jobs_pipeline.py --stats
total active: 2
active AI/ML jobs: 0
```

## Phase 1 completion boundary

The local Phase 1 path is complete and verified. It now supports all four
planned public feed families in the codebase: Greenhouse, Lever, Ashby, and
Workday CXS. The configuration intentionally contains only boards that were
verified from public employer career pages; unsupported or unverified boards
are not guessed.

The PostgreSQL schema and lazy runtime helpers are ready in:

- `sql/postgres_schema.sql`
- `jobmatch_bengaluru/postgres.py`
- `pyproject.toml` extra `postgres`

PostgreSQL live execution remains an environment setup step because this
workspace does not provide a `DATABASE_URL` or a running PostgreSQL server.
The SQLite prototype is still the executable local runner and now mirrors the
Phase 1 metadata: companies, pipeline runs, role category, experience level,
skills, AI flag, and content hash.

Further coverage expansion is an ongoing data-configuration task, not a reason
to block Phase 2. Add a board only after its official careers page exposes a
public supported feed and its identifier has been verified.

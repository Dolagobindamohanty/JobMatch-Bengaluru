# JobMatch Bengaluru API

Run from the project root after the pipeline has created `jobs.db`:

```bash
uvicorn api.app.main:app --reload
```

The API is read-only in Phase 2 and exposes:

- `GET /health`
- `GET /jobs`
- `GET /jobs/ai`
- `GET /jobs/{source}/{company}/{job_id}`
- `GET /skills/trending`

Use `JOBMATCH_DB_PATH` to point at another SQLite file and
`CORS_ORIGINS` for comma-separated frontend origins.

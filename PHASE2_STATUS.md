# Phase 2 Status

## Implemented

### FastAPI job discovery API

Location: `api/app/main.py`

Endpoints:

- `GET /health`
- `GET /jobs`
- `GET /jobs/ai`
- `GET /jobs/{source}/{company}/{job_id}`
- `GET /skills/trending`

The list endpoint supports:

- Free-text search across title, company, location, description, and skills
- Pagination
- AI-only filtering
- Company filtering
- Role-category filtering
- Experience-level filtering
- Newest/company/title sorting

### Next.js job browser

Location: `web/`

Implemented UI features:

- Job list
- Search
- AI-only toggle
- Job cards
- Skill tags
- AI badge
- Apply links
- Job detail panel
- Loading state
- Empty state
- API error state

### Tests

Added API tests using a temporary local SQLite database. The tests do not call
live job boards.

## Run locally

Start the API from the project root:

```bash
uvicorn api.app.main:app --reload
```

Start the frontend from `web/` after Node.js and npm are installed:

```bash
npm install
npm run dev
```

The frontend defaults to `http://localhost:8000` and can be changed with
`NEXT_PUBLIC_API_BASE_URL`.

## Verification

```text
python -m pytest tests -q
10 passed, 1 xpassed

python -m py_compile api/app/main.py
passed
```

Frontend installation/build could not be run in this environment because
Node.js/npm are unavailable. The frontend package and source files are present
and ready to run on a Node-enabled machine.

## Remaining Phase 2 work

- Connect pagination and filter controls fully to server-side query parameters
  from the frontend.
- Add dedicated route pages for AI jobs and job detail.
- Add API schemas and OpenAPI response models.
- Add PostgreSQL-backed API repository after the Phase 1 PostgreSQL runtime is
  configured.

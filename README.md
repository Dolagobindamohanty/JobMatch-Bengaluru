# JobMatch Bengaluru

JobMatch Bengaluru is a Bengaluru-focused AI job-market intelligence product. It
collects public employer-board postings, classifies IT and AI/ML roles, extracts
skills, supports exact skill discovery, and optionally uses Hugging Face hosted
embeddings for semantic job search and a grounded AI job copilot. Resume parsing
and resume-to-job matching exist behind feature flags but remain disabled in the
current public launch.

## Local development

### API

```powershell
pip install -r api/requirements.txt
uvicorn api.app.main:app --reload
```

### Frontend

```powershell
cd web
npm install
npm run dev
```

The local frontend is normally available at `http://localhost:3000` and the
API at `http://localhost:8000`.

## Production

See [DEPLOYMENT.md](DEPLOYMENT.md). The intended public setup is Vercel for the
Next.js frontend and Render (or another Python host) for the FastAPI backend.

## AI layer

When `HF_TOKEN` is configured on the API, the following endpoints are available:

```text
GET  /ai/status
GET  /ai/search?q=Python%20data%20platform
POST /ai/copilot
```

The semantic layer embeds the query and active jobs, caches job embeddings in the
database, ranks jobs by cosine similarity, and sends only the retrieved public
job context to the chat model. The copilot is grounded to those postings and
must include the source application URLs rather than inventing requirements,
salary, or company facts. Normal keyword/skill search works without an AI token.

## Data sources

The pipeline uses public Greenhouse, Lever, Ashby, and Workday CXS feeds when a
company board has been verified. It does not scrape LinkedIn, Naukri, or
Indeed. See `SOURCE_EXPANSION.md` for current coverage and lawful expansion
paths.

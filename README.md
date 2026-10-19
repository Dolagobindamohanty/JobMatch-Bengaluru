# JobMatch Bengaluru

JobMatch Bengaluru is a Bengaluru-focused IT and AI jobs product. It collects
public employer-board postings, classifies AI/ML roles, extracts skills, parses
resumes, ranks resume-to-job matches, and explains skill gaps.

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

## Data sources

The pipeline uses public Greenhouse, Lever, Ashby, and Workday CXS feeds when a
company board has been verified. It does not scrape LinkedIn, Naukri, or
Indeed. See `SOURCE_EXPANSION.md` for current coverage and lawful expansion
paths.

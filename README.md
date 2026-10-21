# JobMatch Bengaluru

JobMatch Bengaluru is a Bengaluru-focused AI job-market intelligence product. It
collects public employer-board postings, classifies IT and AI/ML roles, extracts
skills, supports exact skill discovery, and provides local semantic search with
a grounded AI job copilot by default. Hugging Face hosted embeddings and chat
are optional when hosted-model credits exist. Resume parsing
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

Local semantic AI is the default no-credit mode. FastEmbed loads the local
`BAAI/bge-small-en-v1.5` embedding model on first AI search, so startup and
ordinary job browsing do not download a model. The following endpoints are
available when the local embedding dependency is installed:

```text
GET  /ai/status
GET  /ai/search?q=Python%20data%20platform
POST /ai/copilot
```

The semantic layer embeds the query and active jobs locally, caches job
embeddings in the database, and ranks jobs by cosine similarity. In local mode
the copilot returns a transparent grounded summary from the retrieved job
fields and exact application URLs; it does not claim to be LLM-generated.

Local embeddings and search stay enabled by default. Hosted Hugging Face chat
is independent and optional: set `AI_CHAT_MODE=huggingface` and provide
`HF_TOKEN` to enable it while leaving embeddings local. If hosted chat is
unavailable or rejected, the copilot returns the local grounded summary. To
explicitly select hosted embeddings as well, set `AI_EMBEDDING_MODE=huggingface`.
The older `AI_PROVIDER=huggingface` setting remains supported as a compatibility
shortcut for enabling both hosted modes. Hosted mode keeps the grounding rules:
it sends only retrieved public job context to the chat model and must include
source application URLs rather than inventing requirements, salary, or company
facts. Normal keyword/skill search works without any AI token.

## Data sources

The pipeline uses public Greenhouse, Lever, Ashby, and Workday CXS feeds when a
company board has been verified. It does not scrape LinkedIn, Naukri, or
Indeed. See `SOURCE_EXPANSION.md` for current coverage and lawful expansion
paths.

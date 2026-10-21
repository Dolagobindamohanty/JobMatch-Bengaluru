# Production deployment

## Architecture

- Frontend: Vercel, rooted at `web/`.
- API: Render web service, rooted at the repository root.
- Database: PostgreSQL for production; SQLite is only the local prototype.

## API deployment on Render

1. Create a Render Web Service from this repository.
2. Use the repository `render.yaml`, or set:

```text
Build command: pip install -r api/requirements.txt
Start command: uvicorn api.app.main:app --host 0.0.0.0 --port $PORT
Health check: /health
```

3. Set `CORS_ORIGINS` to the deployed Vercel URL.
4. Attach the managed PostgreSQL database declared in `render.yaml`; Render
   supplies `DATABASE_URL`. The PostgreSQL helper normalizes Render's legacy
   `postgres://` URL and enables connection pre-pinging.
5. The web service does not run a refresh during startup. GitHub Actions runs
   `.github/workflows/refresh.yml` every six hours (at `00:00`, `06:00`,
   `12:00`, and `18:00` UTC), avoiding slow or competing web boot processes.
   The workflow can also be started manually from the Actions tab.
6. Configure the refresh credentials without putting them in source control:

   - In the GitHub repository, open **Settings → Secrets and variables →
     Actions**.
   - Add a repository **variable** named `RENDER_API_URL` with the Render web
     service URL, for example `https://jobmatch-api.onrender.com` (without a
     trailing slash).
   - Add a repository **secret** named `REFRESH_TOKEN` containing a long,
     random token. GitHub masks this value in workflow logs, and the workflow
     sends it only in the `X-Refresh-Token` request header.
   - On the Render web service, add the environment variable
     `REFRESH_TOKEN` with the exact same token under **Environment**. Render
     should keep it as a secret; do not put it in `render.yaml`, the workflow,
     or committed files. When this variable is absent, `POST /refresh` remains
     available without authentication for local/test compatibility.
   - The workflow calls `POST ${RENDER_API_URL}/refresh` and fails if Render
     returns a non-2xx response.
7. Set `DATABASE_URL` to the Neon PostgreSQL connection string on the Render API
   service. The API and refresh workflow initialize the shared PostgreSQL schema
   automatically; SQLite remains only for local development and the checked-in
   starter snapshot.
8. Resume uploads, matching, skill-gap suggestions, resume versions, and
   account-owned resume workflows are intentionally disabled for the first
   public launch. Render sets `JOBMATCH_RESUME_ENABLED=false`; job browsing,
   health, and scheduled collection remain available.

9. Local semantic AI is the default no-credit mode. The API installs
   `fastembed`, uses `BAAI/bge-small-en-v1.5` by default, and downloads that
   model only when the first semantic search or copilot request needs it. No
   Hugging Face token or hosted-model credits are required for local semantic
   search. To select another local model, set `AI_LOCAL_EMBEDDING_MODEL`.

    Hugging Face hosted chat is optional when hosted-model credits exist. To
    enable hosted chat while keeping semantic embeddings local, set:

```text
AI_CHAT_MODE=huggingface
HF_TOKEN=<Hugging Face token with Inference Providers permission>
HF_CHAT_MODEL=Qwen/Qwen2.5-7B-Instruct
HF_CHAT_PROVIDER=auto
```

Keep `HF_TOKEN` private in Render Environment; never put it in GitHub, the
    frontend, a URL, or a committed file. With the default local modes,
    `/ai/search` and `/ai/copilot` use local embeddings and the copilot returns a
    transparent grounded summary. If hosted chat is enabled but unavailable,
    the same local summary is returned. To explicitly use hosted embeddings,
    set `AI_EMBEDDING_MODE=huggingface` and optionally configure
    `HF_EMBEDDING_MODEL` and `HF_EMBEDDING_PROVIDER`. The older
    `AI_PROVIDER=huggingface` setting remains supported as a compatibility
    shortcut for both hosted modes. The API stores only cached job embeddings,
    not the token or resumes.

   When resume features are ready to be enabled, configure private S3-compatible
   object storage. Cloudflare R2 is recommended because it supports private
   buckets and the S3 API without tying uploads to the Render filesystem. Set
   all four variables below on both the Render web service and cron service:

```text
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=jobmatch-resumes
S3_ACCESS_KEY_ID=<R2 access key>
S3_SECRET_ACCESS_KEY=<R2 secret>
```

   Do not enable public bucket access. The API stores private object keys and
   never returns resume bytes or signed URLs. If these variables are omitted,
   local filesystem storage is used for development only; production startup
   rejects incomplete S3 configuration when resume features are enabled.

## Refresh scheduling without Render Cron

Render Cron requires billing on some plans. This repository uses GitHub Actions
instead, so no Render card is required for scheduled refreshes.

1. In the Render API service, set a private `REFRESH_TOKEN` environment variable
   to a long random value. Save and redeploy the service.
2. In GitHub, open **Settings → Secrets and variables → Actions** for this
   repository.
3. Add a repository variable:

```text
RENDER_API_URL=https://jobmatch-bengaluru-api.onrender.com
```

4. Add a repository secret named `REFRESH_TOKEN` with the exact same value as
   Render's `REFRESH_TOKEN`.
5. The workflow in `.github/workflows/refresh.yml` runs every six hours at
   `00:00`, `06:00`, `12:00`, and `18:00` UTC. Use **Run workflow** for an
   immediate refresh.

The API rejects unauthenticated refresh requests with HTTP 401 whenever
`REFRESH_TOKEN` is configured.

An empty PostgreSQL feed triggers a nonblocking initial collection on API startup,
even with `REFRESH_ON_STARTUP=false`. Set `REFRESH_EMPTY_ON_STARTUP=false` to
disable this bootstrap explicitly. Local SQLite is not bootstrapped by default.
`GET /refresh/status` exposes only lifecycle state, last child exit code, and
active-job count. Collector diagnostics appear in Render server logs without
driver messages or credentials. The scheduled workflow now waits for completion
and requires a nonempty feed instead of treating `started` as success.

## Frontend deployment on Vercel

1. Import the repository into Vercel.
2. Set **Root Directory** to `web` (the Vercel project is a web-root Next.js project).
3. Leave the framework preset as **Next.js**. The `web/vercel.json` file supplies the Next.js build settings; do not set the repository root as the Vercel project root.
4. Set the environment variable for Production (and Preview if that environment has an API):

```text
NEXT_PUBLIC_API_BASE_URL=https://<your-render-api>.onrender.com
```

5. Deploy. Any change to `NEXT_PUBLIC_API_BASE_URL` requires a new frontend deployment because `NEXT_PUBLIC_` values are embedded at build time.

## Current limitation

The frontend reads the API with `GET /jobs`; refresh/collection work is owned by
the separate backend and is not run by the browser. The free Render web service
can spin down when idle, so the first request after inactivity may be delayed.

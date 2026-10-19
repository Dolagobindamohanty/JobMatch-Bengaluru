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
5. The web service does not run a refresh during startup. The Render cron
   service runs the collector every six hours, avoiding slow or competing web
   boot processes.
6. Set `JOBMATCH_DB_PATH` only for a deliberately configured persistent local
   database. The current collector/API data access is still SQLite-backed; the
   PostgreSQL schema is prepared for the remaining data-layer migration.
7. Configure private S3-compatible object storage for resumes. Cloudflare R2 is
   recommended for this project because it supports private buckets and the S3
   API without tying uploads to the Render filesystem. Set all four variables
   below on both the Render web service and cron service:

```text
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=jobmatch-resumes
S3_ACCESS_KEY_ID=<R2 access key>
S3_SECRET_ACCESS_KEY=<R2 secret>
```

   Do not enable public bucket access. The API stores private object keys and
   never returns resume bytes or signed URLs. If these variables are omitted,
   local filesystem storage is used for development only; production startup
   rejects incomplete S3 configuration.

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
the separate backend and is not run by the browser. The codebase is deployment-ready but this workspace cannot create external
Vercel or Render services without the user's connected accounts. The GitHub
repository can be populated first; the provider setup requires the user to
authorize the deployment account.

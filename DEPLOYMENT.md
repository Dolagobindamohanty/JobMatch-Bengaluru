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
4. Set `JOBMATCH_DB_PATH` only for a deliberately configured persistent local
   database. Production should use the PostgreSQL schema and repository path.
5. Set `JOBMATCH_RESUME_DIR` to private durable object storage in production;
   the current local filesystem path is for development only.

## Frontend deployment on Vercel

1. Import the repository into Vercel.
2. Set the project root to `web`.
3. Set the environment variable:

```text
NEXT_PUBLIC_API_BASE_URL=https://<your-render-api>.onrender.com
```

4. Deploy.

## Current limitation

The codebase is deployment-ready but this workspace cannot create external
Vercel or Render services without the user's connected accounts. The GitHub
repository can be populated first; the provider setup requires the user to
authorize the deployment account.

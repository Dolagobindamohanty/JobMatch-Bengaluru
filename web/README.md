# Jobmatch Bengaluru web

Minimal Next.js frontend for browsing the normalized Phase 1 job feed.

```bash
npm install
cp .env.example .env.local
npm run dev
```

On PowerShell, use `Copy-Item .env.example .env.local` for the second step. The UI requests `GET ${NEXT_PUBLIC_API_BASE_URL}/jobs`. It accepts either a JSON array or `{ "jobs": [...] }`. Each job can use the Phase 1 SQLite/API fields (`job_id`, `url`, `posted`, `is_ai`, and JSON `skills`) or the PostgreSQL names (`apply_url`, `posted_at`).

For production, set `NEXT_PUBLIC_API_BASE_URL` to the complete HTTPS URL of the separately deployed API (for example, `https://jobmatch-bengaluru-api.onrender.com`) in Vercel before building. The frontend does not proxy or host the API.

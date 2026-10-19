# Jobmatch Bengaluru web

Minimal Next.js frontend for browsing the normalized Phase 1 job feed.

```bash
npm install
cp .env.example .env.local
npm run dev
```

The UI requests `GET ${NEXT_PUBLIC_API_BASE_URL}/jobs`. It accepts either a JSON array or `{ "jobs": [...] }`. Each job can use the Phase 1 SQLite/API fields (`job_id`, `url`, `posted`, `is_ai`, and JSON `skills`) or the PostgreSQL names (`apply_url`, `posted_at`).

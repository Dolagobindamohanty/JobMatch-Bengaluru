# Jobmatch Bengaluru web

Next.js frontend for discovering Bengaluru technology jobs by skill.

```bash
npm install
cp .env.example .env.local
npm run dev
```

On PowerShell, use `Copy-Item .env.example .env.local` for the second step. The UI requests `GET ${NEXT_PUBLIC_API_BASE_URL}/jobs` with `skill`, `q`, `ai_only`, `page`, and `page_size` query parameters. The endpoint must return `{ "jobs": [...], "total": 123, "total_pages": 7 }`. Skill filtering is an exact, case-insensitive match performed by the API across the entire feed. Search, skill and AI filters combine; changing any filter returns to page 1. Select a skill on a card or in the details panel, or clear it above the results.

Each job can use SQLite/API fields (`job_id`, `url`, `posted`, `is_ai`, and JSON `skills`) or PostgreSQL names (`apply_url`, `posted_at`). The original `fetchJobs(signal?)` client helper still accepts array or `{ "jobs": [...] }` responses and returns a job array; the browser uses `fetchJobsPage(filters, signal?)` for server pagination.

For production, set `NEXT_PUBLIC_API_BASE_URL` to the complete HTTPS URL of the separately deployed API (for example, `https://jobmatch-bengaluru-api.onrender.com`) in Vercel before building. The frontend does not proxy or host the API.

## Checks

Run `npm test`, `npm run typecheck`, and `npm run build`. Tests use Node's built-in runner and the existing TypeScript compiler without additional dependencies. They cover combined request filters, server totals, empty/error/cancelled responses, legacy API compatibility, and atomic filter/page transitions. Browser interaction and screen-reader checks remain manual; no DOM test runner is installed.

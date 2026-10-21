# Bengaluru IT and AI Jobs Pipeline — Project Outline

## 1. Goal

Maintain a refreshable local dataset of public job postings whose location is Bengaluru, Bangalore, or BLR and whose role is related to IT or artificial intelligence.

The project favors correctness and traceability over claiming complete coverage. Every result comes from a configured public employer board and retains the original application URL and full description.

## 2. Scope

### Included

- Bengaluru/Bangalore/BLR in structured location fields.
- IT roles: software engineering, development, cloud, DevOps, SRE, infrastructure, networking, security, QA, testing, systems, technical support, data, platform, architecture, and related technical roles.
- AI roles: artificial intelligence, machine learning, deep learning, generative AI, GenAI, LLMs, NLP, computer vision, robotics, recommender systems, MLOps, prompt engineering, and data science.
- Public Greenhouse, Lever, Ashby, and supported Workday CXS feeds.

### Excluded

- Remote-only, India-wide, multi-location, or non-Bengaluru postings when Bengaluru is not explicit.
- Nontechnical roles unless their title clearly identifies an AI/ML or technical responsibility.
- LinkedIn, Indeed, Naukri, or authenticated/private sources.

## 3. Current architecture

1. `companies.json` configures verified board identifiers.
2. Source fetchers call public Greenhouse, Lever, Ashby, and Workday CXS APIs.
3. Location and role classifiers keep Bengaluru IT/AI jobs.
4. PostgreSQL stores normalized postings, descriptions, timestamps, active state, an AI/ML flag, and cached semantic embeddings when the Hugging Face AI layer is configured.
5. Upserts refresh changed jobs; jobs absent from a successful board refresh become inactive.
6. A failed board is logged and skipped so other companies still refresh.
7. Optional Hugging Face hosted inference provides semantic retrieval and a grounded job copilot; public job context is sent, but resumes and provider credentials are not.

## 4. Data model

Each job stores the source, board/company name, source job ID, title, structured location, application URL, source date, cleaned full description, first-seen and last-seen timestamps, active state, and `is_ai`.

## 5. Matching behavior

- Location matching accepts `Bengaluru`, `Bangalore`, and `BLR` case-insensitively.
- IT matching uses technical title vocabulary.
- AI matching uses explicit AI/ML title vocabulary, or strong AI/ML description vocabulary combined with a technical title.
- AI jobs are included even when their title does not contain a generic IT keyword if the AI classifier is confident.

This remains a transparent heuristic. The next quality improvement is storing match reasons and confidence scores.

## 5A. AI job intelligence

- Semantic search embeds the natural-language query and active job records, then ranks them by cosine similarity.
- Job embeddings are cached by source, company, job ID, content hash, and model so unchanged postings are not re-embedded on every request.
- The copilot uses retrieval-augmented generation: it receives only the top public job records and must ground answers in those records and their application URLs.
- The copilot is not an autonomous web-scraping agent. The retrieval and source boundaries are deliberate; a future agent can call these search/detail tools after authentication, rate limits, and evaluation are in place.

## 6. Build phases

### Phase 1 — Working collector

- Greenhouse, Lever, Ashby, and Workday fetchers.
- Bengaluru location filtering.
- IT and AI/ML matching.
- SQLite upsert and inactivation.
- Stats and error isolation.

### Phase 2 — Coverage expansion

- Verify 15–20 Bengaluru-heavy product companies through their official careers links.
- Add only confirmed Greenhouse, Lever, Ashby, or Workday board identifiers.
- Add custom fetchers for Google, Amazon, Microsoft, Apple, Workday, SAP, and other proprietary career systems.

### Phase 3 — Quality and usability

- Add `match_type` and `match_reason` fields.
- Add CSV/JSON export and filters for AI-only, active-only, company, and date.
- Add retry/backoff, request caching, structured run logs, and tests.

### Phase 4 — Operations

- Add a daily scheduled run.
- Keep historical snapshots and change detection.
- Add a lightweight local dashboard or static HTML report.

## 7. Acceptance criteria

- A failed board does not stop other boards.
- A verified Bengaluru AI/ML posting is retained with `is_ai=1`.
- Non-Bengaluru postings are excluded.
- Nontechnical Bengaluru postings are excluded.
- A disappeared posting becomes inactive after a successful board refresh.
- Re-running does not duplicate postings.
- `--stats` reports total active jobs and active AI/ML jobs.

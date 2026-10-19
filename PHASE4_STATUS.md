# Phase 4 Status

## Implemented

- Explainable skill score (50%).
- Token-overlap semantic score (25%) as a deterministic local baseline.
- Experience fit score (15%).
- Role-category/title fit score (10%).
- Matched and missing skills.
- Human-readable match reason.
- Cached match records in SQLite `matches`.
- Ranked endpoint: `GET /resumes/{resume_id}/matches`.
- Role-fit endpoint: `GET /resumes/{resume_id}/roles`.

## Verification

```text
python -m pytest tests -q
15 passed, 1 xpassed
```

The semantic score is deliberately local and explainable for the first
iteration. A future PostgreSQL/pgvector migration can replace it with embedding
similarity without changing the response contract.

## Next work

- Add explicit required/preferred job skills.
- Add embedding generation and pgvector shortlist.
- Add authenticated resume ownership.
- Add Phase 5 skill-gap aggregation and grounded suggestions.

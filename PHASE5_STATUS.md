# Phase 5 Status

## Implemented

- `GET /resumes/{resume_id}/gaps`
- `GET /resumes/{resume_id}/suggestions`
- Top-match missing-skill aggregation
- Frequency counts across top matches
- Conservative `add_to_resume` classification when the term appears in raw resume text but was not parsed
- Conservative `learn_next` classification when the term is absent from raw resume text
- Deterministic grounded suggestions
- No external LLM and no fabricated experience

## Verification

```text
python -m pytest tests -q
16 passed, 1 xpassed
```

Phase 5 suggestions are intentionally local and factual for now. An optional
LLM implementation can be added later behind an explicit provider setting, using
the factual gap counts as its only source of truth.

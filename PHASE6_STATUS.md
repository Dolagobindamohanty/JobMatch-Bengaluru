# Phase 6 Status

## Implemented backend features

- Provider-independent local identity for development.
- Account read/update/delete endpoints.
- Saved jobs.
- Saved searches.
- Applications tracker with status and notes.
- Resume version metadata.
- Complete account/data deletion.
- Ownership filtering for account-owned records.
- Privacy-safe resume responses.

## Daily refresh when the site opens

The API now checks pipeline freshness at startup and through `POST /refresh`.
If the latest successful pipeline run is at least 24 hours old, it starts the
pipeline in the background. A second request while it is running does not start
a duplicate process.

The Next.js home page calls `POST /refresh` before loading jobs, so opening the
site triggers the daily freshness check even when the API process was already
running.

This is intentionally an app-open refresh, not an OS cron/Task Scheduler job.
The API process must be running for the refresh to occur.

## Verification

```text
python -m pytest tests -q
18 passed, 1 xpassed
```

## Current limitation

Authentication is still provider-independent local development identity. The
next production step is replacing the local identity headers with a real auth
provider and private object storage before deployment.

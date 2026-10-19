# Phase 1 Source Coverage

The pipeline is source-extensible, but board identifiers are not guessed. A
company is added only when its official careers page exposes a supported public
feed.

## Enabled and verified

| Company | Source | Board | Result in latest run |
|---|---|---|---:|
| Razorpay Software Private Limited | Greenhouse | `razorpaysoftwareprivatelimited` | 2 Bengaluru IT jobs |
| BrowserStack | Workday CXS | tenant `browserstack`, site `External` | 0 Bengaluru jobs |

## Supported but currently unconfigured

- Lever public postings API
- Ashby public job-board API

No Lever or Ashby identifier was added without an official careers-page
verification. Search-engine results were not sufficient evidence for a board
slug, and guessed slugs create false failures and potentially misleading
coverage claims.

## Intentionally not included in this phase

- LinkedIn, Indeed, and Naukri: no scraping.
- Google, Amazon, Microsoft, Apple, SAP, and similar proprietary career sites:
  they require individual adapters and are outside the four public-feed
  adapters in this phase.
- Adzuna: requires an API application ID and key, which were not provided.

The pipeline logs every configured board independently, so a failed or empty
board cannot stop the other sources.

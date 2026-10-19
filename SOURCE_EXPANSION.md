# Bengaluru Job Source Expansion

The site currently shows two jobs because only one verified configured board
returned Bengaluru roles during the latest run. The adapters are not limited to
Greenhouse, but source coverage must be expanded with real board identifiers or
API credentials; guessing slugs would create false coverage.

## Available immediately

- Greenhouse public board API
- Lever public postings API
- Ashby public job-board API
- Workday CXS public jobs API

The current verified configuration includes Razorpay (`razorpaysoftwareprivatelimited`),
InMobi (`inmobi`), Meesho (`meesho`), and BrowserStack Workday. Each additional
company needs its own verified board identifier in `companies.json`.

## Additional lawful source paths

### Official employer career sites

Add dedicated adapters for large employers whose sites do not use the four
generic feeds. Candidates include Google Careers, Amazon Jobs, Microsoft
Careers, Apple Jobs, SAP Careers, and Flipkart Careers. Each adapter must:

1. use the employer's public search/API response;
2. keep the original application URL;
3. respect the site's terms and rate limits;
4. map structured locations to Bengaluru;
5. be covered by recorded response fixtures.

### Adzuna India API

Adzuna can broaden discovery across public listings, but it requires an
application ID and API key. It should be enabled only through environment
variables, never committed to the repository. Aggregated results must be
deduplicated against official employer links and retain the source URL.

### Other aggregators

Jooble, Arbeitnow, and similar services may require an API key or have limited
India coverage. They should be evaluated individually and added only when a
public API, terms-compatible access path, and Bengaluru location field are
verified.

## Excluded

- LinkedIn, Naukri, and Indeed scraping.
- Search-engine result scraping as a job source.
- Any source that requires bypassing authentication, CAPTCHA, or access controls.

## Operational expectation

Run every configured source independently. A source returning zero is a valid
result; a source failure must be visible in `pipeline_runs` and must not stop
the other sources. Coverage should be shown honestly in the admin/monitoring
surface rather than presenting two jobs as the complete Bengaluru market.

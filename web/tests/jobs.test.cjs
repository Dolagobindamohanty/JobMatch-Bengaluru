const assert = require("node:assert/strict");
const { test, afterEach } = require("node:test");

process.env.NEXT_PUBLIC_API_BASE_URL = "https://jobs.example.test/api";
const { fetchJobs, fetchJobsPage } = require("../lib/api.ts");
const { filterReducer, initialFilters } = require("../lib/job-filters.ts");
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });

test("combines exact skill, text, AI and page filters and uses server totals", async () => {
  const controller = new AbortController();
  global.fetch = async (url, options) => {
    const request = new URL(url);
    assert.equal(request.pathname, "/api/jobs");
    assert.deepEqual(Object.fromEntries(request.searchParams), {
      skill: "C++ / .NET", q: "platform engineer", ai_only: "true", page: "3", page_size: "20",
    });
    assert.equal(options.signal, controller.signal);
    assert.equal(options.cache, "no-store");
    return Response.json({ jobs: [{ job_id: "other-page", title: "Engineer", is_ai: 1, skills: '["C++ / .NET"]' }], total: 41, total_pages: 3 });
  };
  const page = await fetchJobsPage({ skill: "C++ / .NET", q: " platform engineer ", aiOnly: true, page: 3, pageSize: 20 }, controller.signal);
  assert.equal(page.total, 41);
  assert.equal(page.totalPages, 3);
  assert.equal(page.jobs.length, 1);
  assert.equal(page.jobs[0].id, "other-page");
  assert.equal(page.jobs[0].is_ai, true);
  assert.deepEqual(page.jobs[0].skills, ["C++ / .NET"]);
});

test("cleared filters are omitted and an empty server page is valid", async () => {
  global.fetch = async (url) => {
    assert.deepEqual(Object.fromEntries(new URL(url).searchParams), { page: "1", page_size: "20", ai_only: "false" });
    return Response.json({ jobs: [], total: 0, total_pages: 0 });
  };
  assert.deepEqual(await fetchJobsPage({ q: "  ", skill: "" }), { jobs: [], total: 0, totalPages: 0 });
});

test("original fetchJobs keeps its array-returning contract and no query parameters", async () => {
  for (const payload of [[{ job_id: "legacy" }], { jobs: [{ job_id: "legacy" }] }]) {
    global.fetch = async (url) => {
      assert.equal(new URL(url).search, "");
      return Response.json(payload);
    };
    assert.equal((await fetchJobs())[0].id, "legacy");
  }
});

test("aborting an obsolete request propagates cancellation", async () => {
  const controller = new AbortController();
  global.fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  });
  const pending = fetchJobsPage({ skill: "Python" }, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});

test("surfaces service and network failures for retry UI", async () => {
  global.fetch = async () => Response.json({ detail: "Feed unavailable" }, { status: 503 });
  await assert.rejects(fetchJobsPage(), /503.*Feed unavailable/);
  global.fetch = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(fetchJobsPage(), /could not be reached/);
});

test("rejects missing or invalid pagination rather than inventing feed totals", async () => {
  for (const payload of [{ jobs: [] }, { jobs: [], total: -1, total_pages: 2 }, { jobs: [], total: 1, total_pages: 0 }]) {
    global.fetch = async () => Response.json(payload);
    await assert.rejects(fetchJobsPage(), /invalid pagination/);
  }
});

test("each filter change resets pagination while preserving the other filters", () => {
  const state = { query: "engineer", skill: "Python", aiOnly: true, page: 7 };
  for (const [type, value, field] of [["skill", "SQL", "skill"], ["query", "data", "query"], ["aiOnly", false, "aiOnly"], ["skill", "", "skill"]]) {
    assert.deepEqual(filterReducer(state, { type, value }), { ...state, [field]: value, page: 1 });
  }
  assert.deepEqual(filterReducer(state, { type: "page", value: 8 }), { ...state, page: 8 });
  assert.deepEqual(filterReducer(state, { type: "clear" }), initialFilters);
});

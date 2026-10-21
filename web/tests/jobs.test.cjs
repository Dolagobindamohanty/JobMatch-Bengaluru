const assert = require("node:assert/strict");
const { test, afterEach } = require("node:test");

process.env.NEXT_PUBLIC_API_BASE_URL = "https://jobs.example.test/api";
const { askAiCopilot, fetchAiSearch, fetchAiStatus, fetchJobs, fetchJobsPage } = require("../lib/api.ts");
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

test("AI status and semantic search use the public API request shapes", async () => {
  global.fetch = async (url, options) => {
    const request = new URL(url);
    assert.equal(request.pathname, "/api/ai/status");
    assert.equal(options.method, "GET");
    assert.equal(options.cache, "no-store");
    return Response.json({ configured: true, embedding_model: "embed-model", chat_model: "chat-model" });
  };
  assert.deepEqual(await fetchAiStatus(), { configured: true, embeddingModel: "embed-model", chatModel: "chat-model" });

  global.fetch = async (url, options) => {
    const request = new URL(url);
    assert.equal(request.pathname, "/api/ai/search");
    assert.deepEqual(Object.fromEntries(request.searchParams), { q: "python data", limit: "2" });
    assert.equal(options.method, "GET");
    return Response.json({ jobs: [{ job_id: "ai-1", company: "Acme", title: "Data Engineer", url: "https://apply/ai-1", matched_skills: ["python"], similarity_score: 0.9 }] });
  };
  assert.deepEqual(await fetchAiSearch(" python data ", 2), [{
    id: "ai-1", source: "", company: "Acme", title: "Data Engineer", location: "Bengaluru", url: "https://apply/ai-1", posted: "", description: "", is_ai: false, skills: [], role_category: undefined, experience_level: undefined,
    similarityScore: 0.9, matchedSkills: ["python"],
  }]);
});

test("AI copilot posts only the query and limit and parses grounded citations", async () => {
  global.fetch = async (url, options) => {
    assert.equal(new URL(url).pathname, "/api/ai/copilot");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), { query: "Which Python role?", limit: 3 });
    assert.equal(options.body.includes("HF_TOKEN"), false);
    return Response.json({ answer: "Apply to Acme.", model: "chat-model", jobs: [{ job_id: "ai-1", company: "Acme", title: "Python Engineer", url: "https://apply/ai-1", skills: ["Python"] }] });
  };
  const response = await askAiCopilot(" Which Python role? ", 3);
  assert.equal(response.answer, "Apply to Acme.");
  assert.equal(response.model, "chat-model");
  assert.equal(response.jobs[0].id, "ai-1");
  assert.equal(response.jobs[0].url, "https://apply/ai-1");
  assert.deepEqual(response.jobs[0].matchedSkills, []);
});

test("AI copilot keeps an empty citation list safe and surfaces service or shape errors", async () => {
  global.fetch = async () => Response.json({ answer: "No matching roles found.", model: "chat-model", jobs: [] });
  assert.deepEqual((await askAiCopilot("rare skill")).jobs, []);

  global.fetch = async () => Response.json({ detail: "AI provider unavailable" }, { status: 503 });
  await assert.rejects(askAiCopilot("python"), /503.*AI provider unavailable/);

  global.fetch = async () => Response.json({ answer: "missing jobs", model: "chat-model" });
  await assert.rejects(askAiCopilot("python"), /unexpected job list/);
  await assert.rejects(askAiCopilot("   "), /Enter a question/);
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

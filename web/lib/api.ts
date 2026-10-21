export type Job = {
  id: string;
  source: string;
  company: string;
  title: string;
  location: string;
  url: string;
  posted: string;
  description: string;
  is_ai: boolean;
  skills: string[];
  role_category?: string;
  experience_level?: string;
};

type ApiJob = Omit<Partial<Job>, "is_ai" | "skills"> & {
  job_id?: string;
  apply_url?: string;
  posted_at?: string;
  active?: boolean | number;
  is_ai?: boolean | number | string;
  skills?: string[] | string;
};

const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
const API_BASE_URL = configuredApiBaseUrl || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

function getApiUrl(path: string) {
  if (!API_BASE_URL) {
    throw new Error("The API is not configured. Set NEXT_PUBLIC_API_BASE_URL and redeploy the frontend.");
  }

  let baseUrl: URL;
  try {
    baseUrl = new URL(API_BASE_URL);
  } catch {
    throw new Error("The API URL is invalid. Set NEXT_PUBLIC_API_BASE_URL to the full HTTPS API URL.");
  }

  if (baseUrl.protocol !== "http:" && baseUrl.protocol !== "https:") {
    throw new Error("The API URL must start with http:// or https://.");
  }

  return new URL(path.replace(/^\//, ""), `${baseUrl.toString().replace(/\/$/, "")}/`).toString();
}

async function assertOk(response: Response, resource: string) {
  if (response.ok) return;
  let detail = "";
  try {
    const body = await response.json() as { detail?: unknown; message?: unknown };
    const message = body.detail ?? body.message;
    if (typeof message === "string") detail = ` ${message}`;
  } catch {
    // Keep the status-based message when the API does not return JSON.
  }
  throw new Error(`${resource} service returned ${response.status}.${detail}`);
}

export async function requestRefresh(): Promise<void> {
  const response = await fetch(getApiUrl("/refresh"), {
    method: "POST",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  await assertOk(response, "Refresh");
}

function normalizeJob(item: ApiJob, index: number): Job {
  return {
    id: String(item.id ?? item.job_id ?? `${item.company ?? "job"}-${index}`),
    source: item.source ?? "",
    company: item.company ?? "Unknown company",
    title: item.title ?? "Untitled role",
    location: item.location ?? "Bengaluru",
    url: item.url ?? item.apply_url ?? "#",
    posted: item.posted ?? item.posted_at ?? "",
    description: item.description ?? "",
    is_ai: item.is_ai === true || item.is_ai === 1 || item.is_ai === "1",
    skills: Array.isArray(item.skills)
      ? item.skills
      : typeof item.skills === "string"
        ? (() => { try { const parsed: unknown = JSON.parse(item.skills); return Array.isArray(parsed) ? parsed.map(String) : []; } catch { return []; } })()
        : [],
    role_category: item.role_category,
    experience_level: item.experience_level,
  };
}

export type JobFilters = {
  skill?: string;
  q?: string;
  aiOnly?: boolean;
  page?: number;
  pageSize?: number;
};

export type JobsPage = { jobs: Job[]; total: number; totalPages: number };

export type AiProvider = "local" | "huggingface";

export type AiStatus = {
  provider: AiProvider;
  configured: boolean;
  embeddingModel: string;
  chatModel: string;
  hostedChat: boolean;
};

export type AiSearchResult = Job & {
  similarityScore?: number;
  matchedSkills: string[];
};

export type AiCopilotResponse = {
  answer: string;
  jobs: AiSearchResult[];
  model: string;
  mode?: AiProvider;
};

async function requestJobs(params: URLSearchParams, signal?: AbortSignal): Promise<unknown> {
  let response: Response;
  try {
    const query = params.toString();
    response = await fetch(getApiUrl(`/jobs${query ? `?${query}` : ""}`), {
      signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch (reason) {
    if (reason instanceof Error && reason.name === "AbortError") throw reason;
    throw new Error("The jobs API could not be reached. Check the API URL and CORS settings, then try again.");
  }
  await assertOk(response, "Jobs");
  return response.json();
}

function readJobs(payload: unknown): Job[] {
  const items = Array.isArray(payload)
    ? payload
    : payload && typeof payload === "object" && Array.isArray((payload as { jobs?: unknown[] }).jobs)
      ? (payload as { jobs: unknown[] }).jobs
      : null;
  if (!items) throw new Error("The jobs API returned an unexpected response. Try again or contact the API owner.");
  return items.map((item, index) => normalizeJob(item as ApiJob, index));
}

// Keep the original array-returning API for existing consumers.
export async function fetchJobs(signal?: AbortSignal): Promise<Job[]> {
  return readJobs(await requestJobs(new URLSearchParams(), signal));
}

export async function fetchJobsPage(filters: JobFilters = {}, signal?: AbortSignal): Promise<JobsPage> {
  const params = new URLSearchParams({
    page: String(filters.page ?? 1),
    page_size: String(filters.pageSize ?? 20),
    ai_only: String(filters.aiOnly ?? false),
  });
  if (filters.skill) params.set("skill", filters.skill);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  const payload = await requestJobs(params, signal);
  const jobs = readJobs(payload);
  const metadata = payload as { total?: unknown; total_pages?: unknown };
  if (!Number.isSafeInteger(metadata.total) || (metadata.total as number) < 0 ||
      !Number.isSafeInteger(metadata.total_pages) || (metadata.total_pages as number) < 0 ||
      ((metadata.total as number) > 0 && metadata.total_pages === 0)) {
    throw new Error("The jobs API returned invalid pagination details. Try again or contact the API owner.");
  }
  return { jobs, total: metadata.total as number, totalPages: metadata.total_pages as number };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

async function requestAi(path: string, init: RequestInit, resource: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(getApiUrl(path), { ...init, cache: "no-store" });
  } catch (reason) {
    if (reason instanceof Error && reason.name === "AbortError") throw reason;
    throw new Error("The AI service could not be reached. Check the API URL and provider configuration, then try again.");
  }
  await assertOk(response, resource);
  return response.json();
}

export async function fetchAiStatus(signal?: AbortSignal): Promise<AiStatus> {
  const payload = await requestAi("/ai/status", {
    method: "GET",
    signal,
    headers: { Accept: "application/json" },
  }, "AI status");
  if (!isRecord(payload) ||
      (payload.provider !== "local" && payload.provider !== "huggingface") ||
      typeof payload.configured !== "boolean") {
    throw new Error("The AI status response was invalid. Try again or contact the API owner.");
  }
  return {
    provider: payload.provider,
    configured: payload.configured,
    embeddingModel: typeof payload.embedding_model === "string" ? payload.embedding_model : "",
    chatModel: typeof payload.chat_model === "string" ? payload.chat_model : "",
    hostedChat: payload.hosted_chat === true,
  };
}

function readAiJobs(payload: unknown): AiSearchResult[] {
  if (!Array.isArray(payload)) {
    throw new Error("The AI service returned an unexpected job list. Try again or contact the API owner.");
  }
  return payload.map((item, index) => {
    const record = isRecord(item) ? item : {};
    return {
      ...normalizeJob(record as ApiJob, index),
      similarityScore: typeof record.similarity_score === "number" ? record.similarity_score : undefined,
      matchedSkills: Array.isArray(record.matched_skills) ? record.matched_skills.map(String) : [],
    };
  });
}

export async function fetchAiSearch(query: string, limit = 10, signal?: AbortSignal): Promise<AiSearchResult[]> {
  const trimmedQuery = query.trim();
  const params = new URLSearchParams({ q: trimmedQuery, limit: String(limit) });
  const payload = await requestAi(`/ai/search?${params.toString()}`, {
    method: "GET",
    signal,
    headers: { Accept: "application/json" },
  }, "AI search");
  if (!isRecord(payload)) {
    throw new Error("The AI search response was invalid. Try again or contact the API owner.");
  }
  return readAiJobs(payload.jobs);
}

export async function askAiCopilot(query: string, limit = 5, signal?: AbortSignal): Promise<AiCopilotResponse> {
  const trimmedQuery = query.trim();
  if (!trimmedQuery) throw new Error("Enter a question for the AI copilot.");
  const payload = await requestAi("/ai/copilot", {
    method: "POST",
    signal,
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ query: trimmedQuery, limit }),
  }, "AI copilot");
  if (!isRecord(payload) || typeof payload.answer !== "string" ||
      (typeof payload.model !== "string" && payload.model !== null && payload.model !== undefined) ||
      (payload.mode !== undefined && payload.mode !== "local" && payload.mode !== "huggingface")) {
    throw new Error("The AI copilot response was invalid. Try again or contact the API owner.");
  }
  return {
    answer: payload.answer,
    jobs: readAiJobs(payload.jobs),
    model: typeof payload.model === "string" ? payload.model : "",
    mode: payload.mode === "local" || payload.mode === "huggingface" ? payload.mode : undefined,
  };
}

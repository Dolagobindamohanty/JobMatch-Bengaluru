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

export async function fetchJobs(signal?: AbortSignal): Promise<Job[]> {
  let response: Response;
  try {
    response = await fetch(getApiUrl("/jobs"), {
      signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch (reason) {
    if (reason instanceof Error && reason.name === "AbortError") throw reason;
    throw new Error("The jobs API could not be reached. Check the API URL and CORS settings, then try again.");
  }
  await assertOk(response, "Jobs");
  const payload: unknown = await response.json();
  const items = Array.isArray(payload)
    ? payload
    : payload && typeof payload === "object" && Array.isArray((payload as { jobs?: unknown[] }).jobs)
      ? (payload as { jobs: unknown[] }).jobs
      : null;
  if (!items) throw new Error("The jobs API returned an unexpected response. Try again or contact the API owner.");
  return items.map((item, index) => normalizeJob(item as ApiJob, index));
}

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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function requestRefresh(): Promise<void> {
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/refresh`, {
    method: "POST",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Refresh service returned ${response.status}.`);
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
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/jobs`, {
    signal,
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Jobs service returned ${response.status}.`);
  const payload: unknown = await response.json();
  const items = Array.isArray(payload)
    ? payload
    : payload && typeof payload === "object" && Array.isArray((payload as { jobs?: unknown[] }).jobs)
      ? (payload as { jobs: unknown[] }).jobs
      : [];
  return items.map((item, index) => normalizeJob(item as ApiJob, index));
}

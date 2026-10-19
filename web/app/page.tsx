"use client";

import { useEffect, useMemo, useState } from "react";
import { fetchJobs, requestRefresh, type Job } from "../lib/api";

function formatDate(value: string) {
  if (!value) return "Recently posted";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date);
}

function JobCard({ job, selected, onSelect }: { job: Job; selected: boolean; onSelect: () => void }) {
  return (
    <article className={`job-card ${selected ? "selected" : ""}`}>
      <button className="card-main" onClick={onSelect} aria-pressed={selected}>
        <div className="card-topline"><span className="company">{job.company}</span>{job.is_ai && <span className="ai-badge">AI / ML</span>}</div>
        <h2>{job.title}</h2>
        <p className="meta">{job.location} <span>·</span> {formatDate(job.posted)}</p>
        <div className="tags">{job.skills.slice(0, 4).map((skill) => <span className="tag" key={skill}>{skill}</span>)}</div>
      </button>
      <a className="apply-link" href={job.url} target="_blank" rel="noreferrer">Apply <span aria-hidden="true">↗</span></a>
    </article>
  );
}

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [query, setQuery] = useState("");
  const [aiOnly, setAiOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadJobs = () => {
    setLoading(true); setError("");
    fetchJobs().then((items) => { setJobs(items); setSelectedId(items[0]?.id ?? null); }).catch((reason: unknown) => {
      if ((reason as Error)?.name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to load jobs.");
    }).finally(() => setLoading(false));
  };
  useEffect(() => {
    requestRefresh().catch(() => undefined).finally(loadJobs);
  }, []);

  const filteredJobs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return jobs.filter((job) => (!aiOnly || job.is_ai) && (!needle || [job.title, job.company, job.location, ...job.skills].join(" ").toLowerCase().includes(needle)));
  }, [jobs, query, aiOnly]);
  const selectedJob = filteredJobs.find((job) => job.id === selectedId) ?? filteredJobs[0];

  return <main>
    <nav className="nav"><div className="brand"><span className="brand-mark">J</span> jobmatch <span className="brand-place">/ Bengaluru</span></div><span className="nav-note">Curated technology roles</span></nav>
    <header className="hero"><div><p className="eyebrow">PHASE 2 · JOB BROWSER</p><h1>Find your next<br /><em>technical role.</em></h1><p className="hero-copy">A focused feed of active IT and AI opportunities in Bengaluru, sourced from verified employer boards.</p></div><div className="hero-stat"><strong>{jobs.length || "—"}</strong><span>active roles</span></div></header>
    <section className="toolbar" aria-label="Job filters"><label className="search"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, company, or skill" aria-label="Search jobs" /></label><label className={`toggle ${aiOnly ? "on" : ""}`}><input type="checkbox" checked={aiOnly} onChange={(event) => setAiOnly(event.target.checked)} /><span className="toggle-track" /> AI / ML only</label></section>
    {loading ? <div className="state"><div className="spinner" /><p>Loading the latest roles…</p></div> : error ? <div className="state state-error"><strong>We couldn’t load the job feed.</strong><p>{error} Check that the API is running, then try again.</p><button onClick={loadJobs}>Try again</button></div> : <section className="browser"><div className="results-head"><div><span className="eyebrow">OPEN POSITIONS</span><h2>{filteredJobs.length} {filteredJobs.length === 1 ? "role" : "roles"} found</h2></div><span className="result-note">{aiOnly ? "AI / ML roles" : "All technology roles"}</span></div>{filteredJobs.length === 0 ? <div className="empty"><span className="empty-icon">⌁</span><h3>No roles match those filters.</h3><p>Try a broader search or turn off AI / ML only.</p></div> : <div className="browser-grid"><div className="job-list">{filteredJobs.map((job) => <JobCard key={job.id} job={job} selected={selectedJob?.id === job.id} onSelect={() => setSelectedId(job.id)} />)}</div>{selectedJob && <aside className="detail"><div className="detail-label">ROLE DETAILS</div><div className="detail-heading"><span className="company">{selectedJob.company}</span>{selectedJob.is_ai && <span className="ai-badge">AI / ML</span>}</div><h2>{selectedJob.title}</h2><p className="meta">{selectedJob.location} <span>·</span> {formatDate(selectedJob.posted)}</p><a className="primary-apply" href={selectedJob.url} target="_blank" rel="noreferrer">View application <span>↗</span></a><div className="detail-section"><h3>Skills</h3><div className="tags">{selectedJob.skills.length ? selectedJob.skills.map((skill) => <span className="tag" key={skill}>{skill}</span>) : <span className="muted">Skills not listed</span>}</div></div><div className="detail-section"><h3>About the role</h3><p className="description">{selectedJob.description || "The employer has not provided a description for this role."}</p></div></aside>}</div>}</section>}
    <footer>Jobmatch Bengaluru <span>·</span> Built for focused searching</footer>
  </main>;
}

"use client";

import { useEffect, useReducer, useState } from "react";
import { fetchJobsPage, type Job, type JobsPage } from "../lib/api";
import { filterReducer, initialFilters } from "../lib/job-filters";

function formatDate(value: string) {
  if (!value) return "Recently posted";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date);
}

function SkillTags({ skills, activeSkill, onSkill }: { skills: string[]; activeSkill: string; onSkill: (skill: string) => void }) {
  return <div className="tags">{skills.map((skill) => (
    <button type="button" className="tag" key={skill} aria-pressed={activeSkill.toLowerCase() === skill.toLowerCase()} aria-label={`Filter jobs by ${skill}`} onClick={() => onSkill(skill)}>{skill}</button>
  ))}</div>;
}

function JobCard({ job, selected, onSelect, activeSkill, onSkill }: { job: Job; selected: boolean; onSelect: () => void; activeSkill: string; onSkill: (skill: string) => void }) {
  return (
    <article className={`job-card ${selected ? "selected" : ""}`}>
      <div className="card-content">
        <button type="button" className="card-main" onClick={onSelect} aria-pressed={selected} aria-label={`Show details for ${job.title} at ${job.company}`}>
          <div className="card-topline"><span className="company">{job.company}</span>{job.is_ai && <span className="ai-badge">AI / ML</span>}</div>
          <h2>{job.title}</h2>
          <p className="meta">{job.location} <span>·</span> {formatDate(job.posted)}</p>
        </button>
        <SkillTags skills={job.skills.slice(0, 4)} activeSkill={activeSkill} onSkill={onSkill} />
      </div>
      <a className="apply-link" href={job.url} target="_blank" rel="noreferrer">Apply <span aria-hidden="true">↗</span></a>
    </article>
  );
}

export default function Home() {
  const [filters, dispatch] = useReducer(filterReducer, initialFilters);
  const [result, setResult] = useState<JobsPage>({ jobs: [], total: 0, totalPages: 0 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, retry] = useReducer((value: number) => value + 1, 0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchJobsPage({ q: filters.query, skill: filters.skill, aiOnly: filters.aiOnly, page: filters.page, pageSize: 20 }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        // The feed can shrink between page requests; return to its last valid page.
        if (filters.page > Math.max(1, page.totalPages)) {
          dispatch({ type: "page", value: Math.max(1, page.totalPages) });
          return;
        }
        setResult(page);
        setSelectedId((current) => page.jobs.some((job) => job.id === current) ? current : page.jobs[0]?.id ?? null);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load jobs.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [filters, attempt]);

  const selectedJob = result.jobs.find((job) => job.id === selectedId) ?? result.jobs[0];
  const selectSkill = (value: string) => dispatch({ type: "skill", value });
  const hasFilters = Boolean(filters.skill || filters.query || filters.aiOnly);

  return <main>
    <nav className="nav"><div className="brand"><span className="brand-mark">J</span> jobmatch <span className="brand-place">/ Bengaluru</span></div><span className="nav-note">Curated technology roles</span></nav>
    <header className="hero">
      <div><p className="eyebrow">JOBS · SKILLS · BENGALURU</p><h1>Find your next<br /><em>technical role.</em></h1><p className="hero-copy">Explore active IT and AI opportunities in Bengaluru. Choose a skill on any role to discover more jobs that use it.</p></div>
      <div className="hero-stat"><strong>{loading || error ? "—" : result.total.toLocaleString("en-IN")}</strong><span>matching roles</span></div>
    </header>
    <section className="toolbar" aria-label="Job filters">
      <label className="search"><span aria-hidden="true">⌕</span><input value={filters.query} onChange={(event) => dispatch({ type: "query", value: event.target.value })} placeholder="Search title, company, or skill" aria-label="Search jobs" /></label>
      <label className={`toggle ${filters.aiOnly ? "on" : ""}`}><input type="checkbox" checked={filters.aiOnly} onChange={(event) => dispatch({ type: "aiOnly", value: event.target.checked })} /><span className="toggle-track" /> AI / ML only</label>
    </section>
    <div className="active-filters">
      {filters.skill ? <button type="button" className="skill-filter" onClick={() => selectSkill("")} aria-label={`Clear skill filter: ${filters.skill}`}>Skill: {filters.skill} <span aria-hidden="true">×</span></button> : <span className="muted">Select a skill on a job to filter the entire feed.</span>}
      {hasFilters && <button type="button" className="clear-filters" onClick={() => dispatch({ type: "clear" })}>Clear all filters</button>}
    </div>
    <div id="job-results" aria-busy={loading}>
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{loading ? "Loading matching jobs…" : error ? "Jobs could not be loaded." : `${result.total} matching ${result.total === 1 ? "role" : "roles"}. ${result.total ? `Page ${filters.page} of ${result.totalPages}.` : "Try changing your filters."}`}</p>
      {loading ? <div className="state"><div className="spinner" aria-hidden="true" /><p>Loading matching roles…</p></div> : error ? (
        <div className="state state-error" role="alert"><strong>We couldn’t load the job feed.</strong><p>{error}</p><button type="button" onClick={retry}>Try again</button></div>
      ) : <section className="browser" aria-label="Matching jobs">
        <div className="results-head"><div><span className="eyebrow">OPEN POSITIONS</span><h2>{result.total.toLocaleString("en-IN")} {result.total === 1 ? "role" : "roles"} found</h2></div><span className="result-note">{filters.aiOnly ? "AI / ML roles" : "All technology roles"}</span></div>
        {result.jobs.length === 0 ? <div className="empty"><span className="empty-icon" aria-hidden="true">⌁</span><h3>No roles match those filters.</h3><p>Try another skill, a broader search, or turn off AI / ML only.</p>{hasFilters && <button type="button" className="clear-filters" onClick={() => dispatch({ type: "clear" })}>Clear all filters</button>}</div> : <>
          <div className="browser-grid">
            <div className="job-list">{result.jobs.map((job) => <JobCard key={job.id} job={job} selected={selectedJob?.id === job.id} onSelect={() => setSelectedId(job.id)} activeSkill={filters.skill} onSkill={selectSkill} />)}</div>
            {selectedJob && <aside className="detail" aria-label="Selected role details">
              <div className="detail-label">ROLE DETAILS</div><div className="detail-heading"><span className="company">{selectedJob.company}</span>{selectedJob.is_ai && <span className="ai-badge">AI / ML</span>}</div>
              <h2>{selectedJob.title}</h2><p className="meta">{selectedJob.location} <span>·</span> {formatDate(selectedJob.posted)}</p>
              <a className="primary-apply" href={selectedJob.url} target="_blank" rel="noreferrer">View application <span aria-hidden="true">↗</span></a>
              <div className="detail-section"><h3>Skills</h3>{selectedJob.skills.length ? <SkillTags skills={selectedJob.skills} activeSkill={filters.skill} onSkill={selectSkill} /> : <p className="muted">Skills not listed</p>}</div>
              <div className="detail-section"><h3>About the role</h3><p className="description">{selectedJob.description || "The employer has not provided a description for this role."}</p></div>
            </aside>}
          </div>
          <nav className="pagination" aria-label="Job results pages">
            <button type="button" disabled={filters.page <= 1} onClick={() => dispatch({ type: "page", value: filters.page - 1 })} aria-controls="job-results">Previous</button>
            <span>Page {filters.page} of {result.totalPages}</span>
            <button type="button" disabled={filters.page >= result.totalPages} onClick={() => dispatch({ type: "page", value: filters.page + 1 })} aria-controls="job-results">Next</button>
          </nav>
        </>}
      </section>}
    </div>
    <footer>Jobmatch Bengaluru <span>·</span> Built for focused searching</footer>
  </main>;
}

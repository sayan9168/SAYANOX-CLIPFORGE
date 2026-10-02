"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ExternalLink, Loader2, RefreshCw, RotateCcw, Square, Trash2 } from "lucide-react";
import { requestJson } from "../../lib/api";
import type { JobRow } from "../../lib/types";

export function JobBoard() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState("");
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const data = await requestJson<{ jobs: JobRow[] }>("/api/jobs/list?limit=200", { signal: controller.signal });
        if (controller.signal.aborted) return;
        setJobs(data.jobs || []); setError("");
      } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Could not sync jobs."); }
      finally { if (!controller.signal.aborted) setLoading(false); }
      if (!controller.signal.aborted) timer = setTimeout(load, 8000);
    }
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [revision]);
  async function action(id: string, kind: "cancel" | "retry" | "delete") {
    if (kind === "delete" && !window.confirm("Delete this job and its media files? Project metadata is kept, but links to this job will expire.")) return;
    setPending(id); setError(""); setMessage("");
    try {
      await requestJson(`/api/jobs/${kind}?job=${id}`, { method: kind === "delete" ? "DELETE" : "POST" });
      setMessage(kind === "cancel" ? "Cancellation requested. The worker stops safely between stages." : kind === "retry" ? "Job queued for retry." : "Job deleted.");
      setRevision((value) => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Job action failed."); }
    finally { setPending(""); }
  }
  async function cleanup() {
    if (!window.confirm("Remove expired jobs and, if over quota, the oldest inactive jobs? Active work and project metadata will be kept.")) return;
    setPending("cleanup");
    try {
      const result = await requestJson<{ removed: string[]; over_limit: boolean }>("/api/jobs/cleanup", { method: "POST" });
      setMessage(`${result.removed.length} inactive jobs removed.${result.over_limit ? " Storage is still over quota; active jobs and project files were protected." : ""}`);
      setRevision((value) => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Cleanup failed."); }
    finally { setPending(""); }
  }
  const active = (job: JobRow) => ["preparing", "queued", "processing", "cancelling"].includes(job.status);
  const filtered = jobs.filter((job) => (status === "all" || status === "active" && active(job) || status === job.status)
    && `${job.id} ${job.kind} ${job.label || ""}`.toLowerCase().includes(search.toLowerCase()));
  return <section className="jobBoard" aria-label="Worker jobs">
    <div className="jobStats"><div><b>{jobs.filter(active).length}</b><span>Active</span></div><div><b>{jobs.filter((job) => job.status === "completed").length}</b><span>Completed</span></div><div><b>{jobs.filter((job) => job.status === "failed").length}</b><span>Needs attention</span></div><div><b>{jobs.length}</b><span>Recent jobs</span></div></div>
    <div className="toolbar jobFilters"><input aria-label="Search jobs" placeholder="Search by name, URL or job ID…" value={search} onChange={(event) => setSearch(event.target.value)} />
      <select aria-label="Filter job status" value={status} onChange={(event) => setStatus(event.target.value)}>{["all", "active", "completed", "failed", "cancelled"].map((value) => <option key={value} value={value}>{value === "all" ? "All statuses" : value}</option>)}</select>
      <button type="button" className="chip" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={13} /> Refresh</button><button type="button" className="chip" disabled={Boolean(pending)} onClick={cleanup}><Trash2 size={13} /> Prune old jobs</button>
    </div>
    {error && <p className="error" role="alert">{error}</p>}{message && <p className="note" role="status">{message}</p>}
    {loading && <p className="hint"><Loader2 className="spin" size={14} /> Syncing worker jobs…</p>}
    {!loading && !error && !filtered.length && <div className="emptyState"><h3>{jobs.length ? "No matching jobs" : "Your queue is clear."}</h3><p>{jobs.length ? "Try another search or status filter." : "Analyze a video in the studio to get started."}</p><Link href="/" className="dl">Open studio</Link></div>}
    <div className="jobCards">{filtered.map((job) => <article className="jobCard" key={job.id}>
      <div className="jobCardHead"><div><span className="eyebrow">{job.kind}</span><h3>{job.label || `${job.kind} ${job.id.slice(0, 8)}`}</h3><small>{job.id} · {job.created_at ? new Date(job.created_at * 1000).toLocaleString() : ""}</small></div><span className={`jobBadge ${job.status}`}>{job.status}</span></div>
      <div className="jobStage"><span>{job.stage || job.status}</span><b>{job.progress || 0}%</b></div><div className="miniProgress"><i style={{ width: `${job.progress || 0}%` }} /></div>
      {job.error && <p className="jobError">{job.error}</p>}
      <div className="jobCardActions"><Link href={`/?job=${job.id}`} className="chip"><ExternalLink size={12} /> Open in studio</Link>
        {["queued", "processing"].includes(job.status) && <button type="button" className="chip danger" disabled={Boolean(pending)} onClick={() => action(job.id, "cancel")}><Square size={11} /> Cancel</button>}
        {["failed", "cancelled"].includes(job.status) && <button type="button" className="chip" disabled={Boolean(pending)} onClick={() => action(job.id, "retry")}><RotateCcw size={12} /> Retry</button>}
        {!active(job) && <button type="button" className="chip" disabled={Boolean(pending)} onClick={() => action(job.id, "delete")}><Trash2 size={12} /> Delete</button>}
        <small>{job.attempts || 0}/{job.max_attempts || 3} attempts{pending === job.id ? " · updating…" : ""}</small>
      </div>
    </article>)}</div>
    <p className="inputHelp">Refreshes automatically every 8 seconds · up to 200 recent jobs · cancelling Whisper may wait for its current inference stage.</p>
  </section>;
}
